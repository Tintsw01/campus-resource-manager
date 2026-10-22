"""DatabaseManager: the only module that talks to SQLite."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "campus_booking.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


class DatabaseError(Exception):
    """Raised for any low-level database failure (wraps sqlite3.Error)."""


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), stored)


class DatabaseManager:
    def __init__(self, path=DB_PATH):
        try:
            self._conn = sqlite3.connect(path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            with open(SCHEMA_PATH, encoding="utf-8") as f:
                self._conn.executescript(f.read())
            self._seed()
        except (sqlite3.Error, OSError) as exc:
            raise DatabaseError(f"Could not initialise database: {exc}") from exc

    def query(self, sql, params=()):
        try:
            return self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def execute(self, sql, params=()):
        """Run a write statement inside a transaction; returns the cursor."""
        try:
            with self._conn:
                return self._conn.execute(sql, params)
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def close(self):
        self._conn.close()

    # ---------------------------------------------------------------- seed data
    def _seed(self):
        """Insert campuses, sample resources, demo accounts and bookings on first run."""
        if self._conn.execute("SELECT COUNT(*) FROM campuses").fetchone()[0]:
            return
        with self._conn:
            c = self._conn
            for name, policy in [("Johannesburg Campus", "JohannesburgPolicy"),
                                 ("Pretoria Campus", "PretoriaPolicy"),
                                 ("Durban Campus", "DurbanPolicy")]:
                c.execute("INSERT INTO campuses(campus_name, booking_policy) VALUES (?,?)",
                          (name, policy))
            resources = [
                ("JHB-LAB-01", 1, "Computer Lab A", "Computer Lab"),
                ("JHB-PRJ-01", 1, "Projector P1", "Multimedia Projector"),
                ("JHB-SEM-01", 1, "Seminar Room 1", "Seminar Room"),
                ("PTA-LAB-01", 2, "Computer Lab B", "Computer Lab"),
                ("PTA-SMT-01", 2, "Smart Classroom 1", "Smart Classroom"),
                ("PTA-PRJ-01", 2, "Projector P2", "Multimedia Projector"),
                ("DBN-LAB-01", 3, "Computer Lab C", "Computer Lab"),
                ("DBN-PRJ-01", 3, "Projector P3", "Multimedia Projector"),
                ("DBN-PRS-01", 3, "Presentation Kit 1", "Presentation Equipment"),
            ]
            c.executemany("INSERT INTO resources VALUES (?,?,?,?)", resources)
            users = [("operator", "Operator@123", "system_operator", None),
                     ("admin_jhb", "Admin@123", "campus_admin", 1),
                     ("admin_pta", "Admin@123", "campus_admin", 2),
                     ("admin_dbn", "Admin@123", "campus_admin", 3),
                     ("lecturer1", "Lecturer@123", "lecturer", None)]
            for u, p, role, campus in users:
                c.execute("INSERT INTO users(username,password,role,campus_id) VALUES (?,?,?,?)",
                          (u, hash_password(p), role, campus))
            today = date.today()
            sample = [(5, "JHB-LAB-01", 1, -10, "09:00", 120), (5, "JHB-PRJ-01", 1, -3, "10:00", 60),
                      (5, "PTA-LAB-01", 2, -5, "08:00", 180), (5, "DBN-PRJ-01", 3, -2, "13:00", 90),
                      (5, "JHB-SEM-01", 1, 3, "11:00", 120), (5, "PTA-SMT-01", 2, 4, "14:00", 60)]
            for uid, rid, cid, off, st, dur in sample:
                c.execute("INSERT INTO bookings(user_id,resource_id,campus_id,booking_date,"
                          "start_time,duration) VALUES (?,?,?,?,?,?)",
                          (uid, rid, cid, (today + timedelta(days=off)).isoformat(), st, dur))
