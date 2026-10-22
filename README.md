# Smart Campus Resource Booking System

https://github.com/Tintsw01/smart-campus-resource-booking-system
[link Text](https://github.com/Tintsw01/smart-campus-resource-booking-system)

Python 3 + Tkinter + SQLite desktop application (standard library only, no pip installs).

## 1. Folder structure
```
smart_campus/
├── main.py                  # entry point
├── README.md
├── campus_booking.db        # created automatically on first run
└── campus_booking/
    ├── __init__.py
    ├── schema.sql           # SQL creation script
    ├── database.py          # DatabaseManager, password hashing, seed data
    ├── models.py            # User hierarchy, Campus, Resource, Booking
    ├── policies.py          # BookingPolicy hierarchy + registry
    ├── services.py          # Auth, Campus, Resource, Booking, Report services
    └── gui.py               # all Tkinter screens
```

## 2. Setup
1. Install Python 3.9+ (on Linux also `sudo apt install python3-tk`; Windows/macOS installers include Tkinter).
2. Unzip the project and open a terminal in the `smart_campus` folder.
3. Run `python main.py` (or `python3 main.py`).
4. The database and seed data are created automatically. Delete `campus_booking.db` to reset.

Demo accounts: `lecturer1 / Lecturer@123`, `admin_jhb`, `admin_pta`, `admin_dbn` / `Admin@123`, `operator / Operator@123`. New lecturers can register on the login screen.

## 3. Database schema (see `campus_booking/schema.sql`)
| Table | Columns |
|---|---|
| campuses | campus_id PK, campus_name UNIQUE, booking_policy |
| users | user_id PK, username UNIQUE, password (salted PBKDF2 hash), role, campus_id (admins only) |
| resources | resource_id PK (text), campus_id FK, resource_name, resource_type, UNIQUE(campus_id, resource_name) |
| bookings | booking_id PK, user_id FK, resource_id FK (ON DELETE CASCADE), campus_id FK, booking_date, start_time, duration (minutes), status (active/cancelled) |

Additions beyond the brief: `users.campus_id` (links an admin to a campus) and `bookings.status` (cancellation keeps the record for history and reports).

## 4. Campus policies
- Johannesburg: maximum 4 hours per booking.
- Pretoria: bookings must fall within 08:00-17:00.
- Durban: maximum 2 hours; projectors have priority access, interpreted as bookable 30 days ahead while other resources are bookable 7 days ahead.
- All campuses: no past bookings, no bookings over midnight, never more than 8 hours.

## 5. UML class diagram (text)
```
            +------------------+                      +---------------------+
            |  User (abstract) |                      | BookingPolicy (ABC) |
            |------------------|                      |---------------------|
            | -_user_id        |                      | +validate()         |
            | -_username       |                      | #check_rules()*     |
            | -__password_hash |                      | +describe()*        |
            | -_campus_id      |                      +----------^----------+
            |------------------|                  ______________|_____________________
            | +permissions*    |                 |            |           |           |
            | +dashboard_tabs()*                 |DefaultPolicy|Johannesburg|Pretoria |Durban
            | +can(perm)       |                 |            |Policy      |Policy    |Policy
            | +can_manage_campus()|
            +--------^---------+
        _____________|______________
       |             |              |
 +-----------+ +--------------------+ +----------------+
 | Lecturer  | | CampusAdministrator| | SystemOperator |
 +-----------+ +--------------------+ +----------------+

 Campus(campus_id, name, policy_key, policy: BookingPolicy)  --has-->  BookingPolicy
 Campus 1 --- * Resource(resource_id, campus_id, name, resource_type)
 Resource 1 --- * Booking(booking_id, user_id, resource_id, campus_id, date, start, duration, status)
 Lecturer 1 --- * Booking

 DatabaseManager <-- uses -- AuthService, CampusService, ResourceService, BookingService, ReportService
 BookingService --uses--> CampusService --creates--> Campus --> BookingPolicy
 App(tk.Tk) --owns--> services; Dashboard, LoginFrame, BookingFrame, HistoryFrame,
                      ResourceFrame, ReportsFrame, TableFrame (ttk.Frame subclasses)
 (* = abstract member)
```

## 6. How OOP is used
- **Inheritance:** `Lecturer`, `CampusAdministrator`, `SystemOperator` extend `User`; `JohannesburgPolicy`, `PretoriaPolicy`, `DurbanPolicy`, `DefaultPolicy` extend `BookingPolicy`; every screen extends a Tk/ttk class.
- **Encapsulation:** the password hash is a name-mangled private attribute (`__password_hash`) that is never exposed. Login uses `check_password(verifier)`, so the hash never leaves the object. Other fields are read through properties. `DatabaseManager` hides the SQLite connection.
- **Polymorphism:** `permissions` and `dashboard_tabs()` behave differently per role, so the dashboard builds role-specific tabs without `if role ==` chains. `BookingPolicy.validate()` calls each campus's own `check_rules()` and `describe()`.
- **Abstraction:** `User` and `BookingPolicy` are abstract base classes.
- **Separation of rules from logic:** `BookingService` only calls `policy.validate(...)`. To add a campus rule set, subclass `BookingPolicy`, decorate it with `@register_policy`, then call `CampusService.add_campus(name, "YourPolicy")`. Nothing else changes.
- **Data structures:** lists of `Campus`/`Resource` objects, `POLICY_REGISTRY` and `ROLE_CLASSES` dictionaries, and `PRIORITY_TYPES` / `permissions` sets.

## 7. How SQLite is integrated
- `DatabaseManager` opens the connection with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`, runs `schema.sql` (`CREATE TABLE IF NOT EXISTS`), then seeds three campuses, sample resources, demo users and sample bookings on first run only.
- All SQL uses parameterised queries (no string concatenation of user input), which prevents SQL injection.
- Writes run inside `with connection:` so each change is committed, or rolled back on error.
- `sqlite3.Error` is wrapped in `DatabaseError`; `IntegrityError` is turned into friendly duplicate messages. The GUI shows these through message boxes.
- Everything persists in `campus_booking.db` between runs.

## 8. Behaviour notes
- Overlap check: two active bookings for the same resource and date overlap when `start1 < end2 and start2 < end1`.
- Cancelling sets `status='cancelled'` (only future, own, active bookings). Cancelled bookings free the slot and show in history.
- Deleting a resource is blocked while future active bookings exist; otherwise its old booking records are deleted with it.
- Campus administrators are locked to their own campus; system operators can view every campus and run cross-campus reports.
