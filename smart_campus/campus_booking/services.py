"""Business logic. Services use DatabaseManager and BookingPolicy objects; no GUI code here."""
import re
import sqlite3
from datetime import datetime

from .database import DatabaseManager, hash_password, verify_password
from .models import (Booking, Campus, RESOURCE_TYPES, Resource, ROLE_CLASSES, fmt_duration,
                     user_from_row)
from .policies import get_policy


class ServiceError(Exception):
    """User-facing error (validation or rule failure). Message is safe to display."""


class AuthService:
    def __init__(self, db: DatabaseManager):
        self._db = db

    def register_lecturer(self, username, password, confirm):
        username = (username or "").strip()
        if not username or not password or not confirm:
            raise ServiceError("All fields are required.")
        if not re.fullmatch(r"[A-Za-z0-9_.]{3,30}", username):
            raise ServiceError("Username must be 3-30 letters, digits, '_' or '.'.")
        if len(password) < 6:
            raise ServiceError("Password must be at least 6 characters.")
        if password != confirm:
            raise ServiceError("Passwords do not match.")
        try:
            self._db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'lecturer')",
                             (username, hash_password(password)))
        except sqlite3.IntegrityError:
            raise ServiceError("That username is already taken.")
        return True

    def login(self, username, password):
        username = (username or "").strip()
        if not username or not password:
            raise ServiceError("Please enter both username and password.")
        rows = self._db.query("SELECT * FROM users WHERE username = ?", (username,))
        if not rows:
            raise ServiceError("Invalid username or password.")
        user = user_from_row(rows[0])
        if not user.check_password(lambda stored: verify_password(password, stored)):
            raise ServiceError("Invalid username or password.")
        return user


class CampusService:
    def __init__(self, db):
        self._db = db

    @staticmethod
    def _build(row):
        return Campus(row["campus_id"], row["campus_name"], row["booking_policy"],
                      get_policy(row["booking_policy"]))

    def list_campuses(self):
        return [self._build(r) for r in self._db.query("SELECT * FROM campuses ORDER BY campus_name")]

    def get(self, campus_id):
        rows = self._db.query("SELECT * FROM campuses WHERE campus_id=?", (campus_id,))
        if not rows:
            raise ServiceError("Campus not found.")
        return self._build(rows[0])

    def add_campus(self, name, policy_key):
        """Future expansion: add a campus (policy class must be registered in policies.py)."""
        if not name.strip():
            raise ServiceError("Campus name is required.")
        try:
            self._db.execute("INSERT INTO campuses(campus_name,booking_policy) VALUES (?,?)",
                             (name.strip(), policy_key))
        except sqlite3.IntegrityError:
            raise ServiceError("A campus with that name already exists.")


class ResourceService:
    def __init__(self, db):
        self._db = db

    @staticmethod
    def _row(r):
        return Resource(r["resource_id"], r["campus_id"], r["resource_name"], r["resource_type"])

    def list_resources(self, campus_id=None):
        if campus_id is None:
            rows = self._db.query("SELECT * FROM resources ORDER BY campus_id, resource_id")
        else:
            rows = self._db.query("SELECT * FROM resources WHERE campus_id=? ORDER BY resource_id",
                                  (campus_id,))
        return [self._row(r) for r in rows]

    def get(self, resource_id):
        rows = self._db.query("SELECT * FROM resources WHERE resource_id=?", (resource_id,))
        if not rows:
            raise ServiceError("Resource not found.")
        return self._row(rows[0])

    def _check_access(self, user, campus_id):
        if not (user.can("manage_resources") and user.can_manage_campus(campus_id)):
            raise ServiceError("You may only manage resources of your own campus.")

    @staticmethod
    def _clean(resource_id, name, rtype):
        resource_id, name = (resource_id or "").strip().upper(), (name or "").strip()
        if not resource_id or not name or not rtype:
            raise ServiceError("Resource ID, name and type are all required.")
        if not re.fullmatch(r"[A-Z0-9_-]{3,20}", resource_id):
            raise ServiceError("Resource ID must be 3-20 characters: letters, digits, '-' or '_'.")
        if rtype not in RESOURCE_TYPES:
            raise ServiceError("Please choose a valid resource type.")
        return resource_id, name

    def add(self, user, campus_id, resource_id, name, rtype):
        self._check_access(user, campus_id)
        resource_id, name = self._clean(resource_id, name, rtype)
        if self._db.query("SELECT 1 FROM resources WHERE resource_id=?", (resource_id,)):
            raise ServiceError(f"Duplicate: resource ID '{resource_id}' already exists.")
        if self._db.query("SELECT 1 FROM resources WHERE campus_id=? AND LOWER(resource_name)=?",
                          (campus_id, name.lower())):
            raise ServiceError(f"Duplicate: '{name}' already exists on this campus.")
        try:
            self._db.execute("INSERT INTO resources VALUES (?,?,?,?)",
                             (resource_id, campus_id, name, rtype))
        except sqlite3.IntegrityError:
            raise ServiceError("Duplicate resource detected.")

    def update(self, user, resource_id, name, rtype):
        res = self.get(resource_id)
        self._check_access(user, res.campus_id)
        _, name = self._clean(resource_id, name, rtype)
        if self._db.query("SELECT 1 FROM resources WHERE campus_id=? AND LOWER(resource_name)=? "
                          "AND resource_id<>?", (res.campus_id, name.lower(), resource_id)):
            raise ServiceError(f"Duplicate: '{name}' already exists on this campus.")
        self._db.execute("UPDATE resources SET resource_name=?, resource_type=? WHERE resource_id=?",
                         (name, rtype, resource_id))

    def delete(self, user, resource_id):
        res = self.get(resource_id)
        self._check_access(user, res.campus_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        pending = self._db.query(
            "SELECT COUNT(*) AS n FROM bookings WHERE resource_id=? AND status='active' "
            "AND booking_date || ' ' || start_time > ?", (resource_id, now))[0]["n"]
        if pending:
            raise ServiceError(f"Cannot delete: {pending} future active booking(s) exist. "
                               "Ask lecturers to cancel them first.")
        self._db.execute("DELETE FROM resources WHERE resource_id=?", (resource_id,))


BOOKING_SELECT = (
    "SELECT b.booking_id,b.user_id,b.resource_id,b.campus_id,b.booking_date,b.start_time,"
    "b.duration,b.status,u.username,r.resource_name,c.campus_name FROM bookings b "
    "JOIN users u ON u.user_id=b.user_id JOIN resources r ON r.resource_id=b.resource_id "
    "JOIN campuses c ON c.campus_id=b.campus_id ")


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class BookingService:
    def __init__(self, db, campuses: CampusService, resources: ResourceService):
        self._db, self._campuses, self._resources = db, campuses, resources

    @staticmethod
    def parse(date_s, time_s, duration):
        """Validate raw GUI input and return (start datetime, duration int)."""
        if not (date_s or "").strip() or not (time_s or "").strip() or not str(duration).strip():
            raise ServiceError("Date, start time and duration are required.")
        try:
            start = datetime.strptime(f"{date_s.strip()} {time_s.strip()}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise ServiceError("Date must be YYYY-MM-DD and start time HH:MM (24-hour).")
        try:
            duration = int(duration)
        except ValueError:
            raise ServiceError("Duration must be a whole number of minutes.")
        if duration <= 0:
            raise ServiceError("Duration must be greater than zero.")
        return start, duration

    def has_conflict(self, resource_id, start, duration):
        rows = self._db.query("SELECT start_time, duration FROM bookings WHERE resource_id=? "
                              "AND booking_date=? AND status='active'",
                              (resource_id, start.strftime("%Y-%m-%d")))
        s = start.hour * 60 + start.minute
        return any(s < _minutes(r["start_time"]) + r["duration"] and _minutes(r["start_time"]) < s + duration
                   for r in rows)

    def rule_errors(self, resource, start, duration):
        policy = self._campuses.get(resource.campus_id).policy
        return policy.validate(resource.resource_type, start, duration)

    def availability(self, resource, start, duration):
        """Return 'Available', 'Booked' or 'Not allowed: <reason>' for the GUI."""
        if self.has_conflict(resource.resource_id, start, duration):
            return "Booked"
        errors = self.rule_errors(resource, start, duration)
        return f"Not allowed: {errors[0]}" if errors else "Available"

    def create(self, user, resource_id, date_s, time_s, duration):
        if not user.can("book"):
            raise ServiceError("Only lecturers can create bookings.")
        if not resource_id:
            raise ServiceError("Please select a resource.")
        start, duration = self.parse(date_s, time_s, duration)
        resource = self._resources.get(resource_id)
        errors = self.rule_errors(resource, start, duration)
        if errors:
            raise ServiceError("Booking rejected:\n- " + "\n- ".join(errors))
        if self.has_conflict(resource_id, start, duration):
            raise ServiceError("This resource is already booked for an overlapping time.")
        self._db.execute(
            "INSERT INTO bookings(user_id,resource_id,campus_id,booking_date,start_time,duration) "
            "VALUES (?,?,?,?,?,?)", (user.user_id, resource_id, resource.campus_id,
                                     start.strftime("%Y-%m-%d"), start.strftime("%H:%M"), duration))

    def cancel(self, user, booking_id):
        rows = self._db.query(BOOKING_SELECT + "WHERE b.booking_id=?", (booking_id,))
        if not rows:
            raise ServiceError("Booking not found.")
        b = Booking(rows[0])
        if b.user_id != user.user_id:
            raise ServiceError("You can only cancel your own bookings.")
        if not b.is_future():
            raise ServiceError("Only future active bookings can be cancelled.")
        self._db.execute("UPDATE bookings SET status='cancelled' WHERE booking_id=?", (booking_id,))

    def _fetch(self, where="", params=()):
        rows = self._db.query(BOOKING_SELECT + where + " ORDER BY b.booking_date DESC, b.start_time DESC",
                              params)
        return [Booking(r) for r in rows]

    def for_user(self, user_id):
        return self._fetch("WHERE b.user_id=?", (user_id,))

    def for_campus(self, campus_id=None):
        return self._fetch() if campus_id is None else self._fetch("WHERE b.campus_id=?", (campus_id,))


class ReportService:
    def __init__(self, db):
        self._db = db

    def campus_report(self, campus_id):
        """Total bookings, most used resources, average duration for one campus."""
        s = self._db.query("SELECT COUNT(*) AS n, AVG(duration) AS avg_d, "
                           "COALESCE(SUM(duration),0) AS mins FROM bookings "
                           "WHERE campus_id=? AND status='active'", (campus_id,))[0]
        cancelled = self._db.query("SELECT COUNT(*) AS n FROM bookings WHERE campus_id=? "
                                   "AND status='cancelled'", (campus_id,))[0]["n"]
        top = self._db.query(
            "SELECT r.resource_name, r.resource_type, COUNT(b.booking_id) AS n, "
            "COALESCE(SUM(b.duration),0) AS mins FROM resources r LEFT JOIN bookings b "
            "ON b.resource_id=r.resource_id AND b.status='active' WHERE r.campus_id=? "
            "GROUP BY r.resource_id ORDER BY n DESC, mins DESC", (campus_id,))
        trend = self._db.query(
            "SELECT strftime('%Y-%m', booking_date) AS month, COUNT(*) AS n FROM bookings "
            "WHERE campus_id=? AND status='active' GROUP BY month ORDER BY month", (campus_id,))
        return {"total": s["n"], "avg_minutes": s["avg_d"] or 0, "hours": s["mins"] / 60,
                "cancelled": cancelled, "top": [tuple(r) for r in top],
                "trend": [tuple(r) for r in trend]}

    def cross_campus(self):
        """Campus statistics, resource-type usage and monthly trends for every campus."""
        stats = []
        for c in self._db.query("SELECT * FROM campuses ORDER BY campus_name"):
            rep = self.campus_report(c["campus_id"])
            n_res = self._db.query("SELECT COUNT(*) AS n FROM resources WHERE campus_id=?",
                                   (c["campus_id"],))[0]["n"]
            top = rep["top"][0][0] if rep["top"] and rep["top"][0][2] else "-"
            stats.append({"campus": c["campus_name"], "resources": n_res, "bookings": rep["total"],
                          "avg_minutes": rep["avg_minutes"], "hours": rep["hours"],
                          "cancelled": rep["cancelled"], "top": top,
                          "policy": get_policy(c["booking_policy"]).describe()})
        by_type = self._db.query(
            "SELECT c.campus_name, r.resource_type, COUNT(b.booking_id) AS n FROM bookings b "
            "JOIN resources r ON r.resource_id=b.resource_id JOIN campuses c ON c.campus_id=b.campus_id "
            "WHERE b.status='active' GROUP BY c.campus_name, r.resource_type ORDER BY c.campus_name, n DESC")
        trend = self._db.query(
            "SELECT c.campus_name, strftime('%Y-%m', b.booking_date) AS month, COUNT(*) AS n "
            "FROM bookings b JOIN campuses c ON c.campus_id=b.campus_id WHERE b.status='active' "
            "GROUP BY c.campus_name, month ORDER BY month, c.campus_name")
        return {"stats": stats, "by_type": [tuple(r) for r in by_type],
                "trend": [tuple(r) for r in trend]}
