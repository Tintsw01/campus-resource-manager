"""Domain classes: users (inheritance/polymorphism), Campus, Resource, Booking."""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

RESOURCE_TYPES = ["Computer Lab", "Multimedia Projector", "Seminar Room",
                  "Presentation Equipment", "Smart Classroom"]


class User(ABC):
    """Base user. The password hash is private (name-mangled) and never exposed."""

    ROLE = ""
    ROLE_LABEL = ""

    def __init__(self, user_id, username, password_hash, campus_id=None):
        self._user_id = user_id
        self._username = username
        self.__password_hash = password_hash      # encapsulated sensitive data
        self._campus_id = campus_id

    @property
    def user_id(self): return self._user_id

    @property
    def username(self): return self._username

    @property
    def campus_id(self): return self._campus_id

    def check_password(self, verifier):
        """verifier is a callable(stored_hash) -> bool, so the hash never leaves the class."""
        return verifier(self.__password_hash)

    @property
    @abstractmethod
    def permissions(self):
        """Set of permission strings granted to this role (polymorphic)."""

    @abstractmethod
    def dashboard_tabs(self):
        """Ordered list of dashboard tab keys for this role (polymorphic)."""

    def can(self, permission):
        return permission in self.permissions

    def can_manage_campus(self, campus_id):
        return False

    def __str__(self):
        return f"{self._username} ({self.ROLE_LABEL})"


class Lecturer(User):
    ROLE, ROLE_LABEL = "lecturer", "Lecturer"
    permissions = frozenset({"book", "view_own_bookings", "cancel_own"})

    def dashboard_tabs(self):
        return ["book", "my_bookings"]


class CampusAdministrator(User):
    ROLE, ROLE_LABEL = "campus_admin", "Campus Administrator"
    permissions = frozenset({"manage_resources", "view_campus_bookings", "campus_reports"})

    def dashboard_tabs(self):
        return ["resources", "campus_bookings", "reports"]

    def can_manage_campus(self, campus_id):
        return campus_id == self._campus_id


class SystemOperator(User):
    ROLE, ROLE_LABEL = "system_operator", "System Operator"
    permissions = frozenset({"view_all", "campus_reports", "cross_reports"})

    def dashboard_tabs(self):
        return ["campuses", "all_resources", "all_bookings", "reports"]


ROLE_CLASSES = {c.ROLE: c for c in (Lecturer, CampusAdministrator, SystemOperator)}


def user_from_row(row):
    """Factory: build the correct User subclass from a database row."""
    return ROLE_CLASSES[row["role"]](row["user_id"], row["username"], row["password"],
                                     row["campus_id"])


class Campus:
    def __init__(self, campus_id, name, policy_key, policy):
        self.campus_id, self.name, self.policy_key, self.policy = campus_id, name, policy_key, policy

    def __str__(self):
        return self.name


class Resource:
    def __init__(self, resource_id, campus_id, name, resource_type):
        self.resource_id, self.campus_id = resource_id, campus_id
        self.name, self.resource_type = name, resource_type


def fmt_duration(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h and m else (f"{h}h" if h else f"{m}m")


class Booking:
    def __init__(self, row):
        self.booking_id, self.user_id = row["booking_id"], row["user_id"]
        self.resource_id, self.campus_id = row["resource_id"], row["campus_id"]
        self.booking_date, self.start_time = row["booking_date"], row["start_time"]
        self.duration, self.status = row["duration"], row["status"]
        self.lecturer, self.resource_name = row["username"], row["resource_name"]
        self.campus_name = row["campus_name"]

    @property
    def start_dt(self):
        return datetime.strptime(f"{self.booking_date} {self.start_time}", "%Y-%m-%d %H:%M")

    @property
    def end_dt(self):
        return self.start_dt + timedelta(minutes=self.duration)

    def is_future(self, now=None):
        return self.status == "active" and self.start_dt > (now or datetime.now())

    def is_active(self, now=None):
        """Active = not cancelled and not yet finished."""
        return self.status == "active" and self.end_dt > (now or datetime.now())

    def state(self, now=None):
        if self.status == "cancelled":
            return "Cancelled"
        return "Active" if self.is_active(now) else "Completed"

    def as_row(self):
        return (self.booking_id, self.lecturer, self.resource_name, self.campus_name,
                self.booking_date, self.start_time, self.end_dt.strftime("%H:%M"),
                fmt_duration(self.duration), self.state())

    ROW_COLUMNS = ("ID", "Lecturer", "Resource", "Campus", "Date", "Start", "End",
                   "Duration", "Status")
