"""Tkinter GUI: login, registration, campus selection, dashboard and role-based screens."""
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

from .database import DatabaseError, DatabaseManager
from .models import Booking, RESOURCE_TYPES, fmt_duration
from .services import (AuthService, BookingService, CampusService, ReportService, ResourceService,
                       ServiceError)

NAVY, BLUE, LIGHT = "#12336e", "#0056b3", "#eef3fa"
TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(6, 22) for m in (0, 30)]
DURATIONS = ["30", "60", "90", "120", "180", "240", "300", "480"]


def run_safely(parent, func, *args):
    """Run func; show friendly message boxes for expected and unexpected errors."""
    try:
        return func(*args)
    except ServiceError as exc:
        messagebox.showwarning("Cannot complete request", str(exc), parent=parent)
    except DatabaseError as exc:
        messagebox.showerror("Database error", f"A database problem occurred:\n{exc}", parent=parent)
    except Exception as exc:  # last line of defence so the app never crashes silently
        messagebox.showerror("Unexpected error", str(exc), parent=parent)
    return None


def make_tree(parent, columns, widths=None, height=10):
    """Create a Treeview with a vertical scrollbar; returns the tree."""
    box = ttk.Frame(parent)
    box.pack(fill="both", expand=True)
    tree = ttk.Treeview(box, columns=columns, show="headings", height=height, selectmode="browse")
    for i, col in enumerate(columns):
        tree.heading(col, text=col)
        tree.column(col, width=(widths[i] if widths else 110), anchor="w")
    bar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return tree


def fill_tree(tree, rows, tags=None):
    tree.delete(*tree.get_children())
    for i, row in enumerate(rows):
        tree.insert("", "end", values=row, tags=((tags[i],) if tags else ()))


class App(tk.Tk):
    """Root window. Owns the services and switches between screens."""

    def __init__(self):
        super().__init__()
        self.title("Smart Campus Resource Booking System")
        self.geometry("1100x700")
        self.minsize(950, 620)
        self.db = DatabaseManager()
        self.auth = AuthService(self.db)
        self.campuses = CampusService(self.db)
        self.resources = ResourceService(self.db)
        self.bookings = BookingService(self.db, self.campuses, self.resources)
        self.reports = ReportService(self.db)
        self.user = None
        self.campus = None            # active Campus (None = system-wide for operators)
        self._style()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.show_login()

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=LIGHT)
        s.configure("TLabel", background=LIGHT, font=("Segoe UI", 10))
        s.configure("TLabelframe", background=LIGHT)
        s.configure("TLabelframe.Label", background=LIGHT, foreground=NAVY, font=("Segoe UI", 10, "bold"))
        s.configure("Header.TLabel", background=NAVY, foreground="white", font=("Segoe UI", 11))
        s.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground=NAVY)
        s.configure("TButton", font=("Segoe UI", 10), padding=6)
        s.configure("Accent.TButton", background=BLUE, foreground="white", font=("Segoe UI", 10, "bold"))
        s.map("Accent.TButton", background=[("active", NAVY)])
        s.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background=BLUE, foreground="white")
        self.configure(background=LIGHT)

    def clear(self):
        for child in self.winfo_children():
            child.destroy()

    def show_login(self):
        self.user = self.campus = None
        self.clear()
        LoginFrame(self).pack(fill="both", expand=True)

    def show_campus_select(self):
        self.clear()
        CampusSelectFrame(self).pack(fill="both", expand=True)

    def show_dashboard(self):
        self.clear()
        Dashboard(self).pack(fill="both", expand=True)

    def _close(self):
        self.db.close()
        self.destroy()


# ------------------------------------------------------------------ 1. Login
class LoginFrame(ttk.Frame):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.username, self.password = tk.StringVar(), tk.StringVar()
        card = ttk.Frame(self, padding=30)
        card.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(card, text="Smart Campus Resource Booking", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(0, 5))
        ttk.Label(card, text="Please sign in to continue").grid(row=1, column=0, columnspan=2, pady=(0, 20))
        ttk.Label(card, text="Username:").grid(row=2, column=0, sticky="e", pady=5)
        self.user_entry = ttk.Entry(card, textvariable=self.username, width=30)
        self.user_entry.grid(row=2, column=1, pady=5)
        ttk.Label(card, text="Password:").grid(row=3, column=0, sticky="e", pady=5)
        pw = ttk.Entry(card, textvariable=self.password, show="*", width=30)
        pw.grid(row=3, column=1, pady=5)
        pw.bind("<Return>", lambda e: self.login())
        ttk.Button(card, text="Login", style="Accent.TButton", command=self.login).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(15, 5))
        ttk.Button(card, text="Register as Lecturer", command=lambda: RegisterWindow(app)).grid(
            row=5, column=0, columnspan=2, sticky="ew")
        ttk.Label(card, foreground="#555", justify="center", text=(
            "Demo accounts:  lecturer1 / Lecturer@123   admin_jhb / Admin@123\n"
            "admin_pta, admin_dbn / Admin@123   operator / Operator@123")).grid(
            row=6, column=0, columnspan=2, pady=(20, 0))
        self.user_entry.focus_set()

    def login(self):
        user = run_safely(self, self.app.auth.login, self.username.get(), self.password.get())
        if user is None:
            return
        self.app.user = user
        if user.can("view_campus_bookings"):        # campus admin: fixed campus
            self.app.campus = run_safely(self, self.app.campuses.get, user.campus_id)
            self.app.show_dashboard()
        else:
            self.app.show_campus_select()


# ------------------------------------------------------------ 2. Registration
class RegisterWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Register Lecturer Account")
        self.configure(background=LIGHT)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        self.vars = [tk.StringVar() for _ in range(3)]
        frame = ttk.Frame(self, padding=25)
        frame.pack()
        ttk.Label(frame, text="Create Lecturer Account", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(0, 15))
        for i, (label, show) in enumerate([("Username:", ""), ("Password:", "*"), ("Confirm password:", "*")]):
            ttk.Label(frame, text=label).grid(row=i + 1, column=0, sticky="e", pady=5, padx=5)
            ttk.Entry(frame, textvariable=self.vars[i], show=show, width=28).grid(row=i + 1, column=1, pady=5)
        ttk.Label(frame, text="Username: 3-30 letters/digits/_/.   Password: 6+ characters",
                  foreground="#555").grid(row=4, column=0, columnspan=2, pady=5)
        ttk.Button(frame, text="Register", style="Accent.TButton", command=self.register).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def register(self):
        u, p, c = (v.get() for v in self.vars)
        if run_safely(self, self.app.auth.register_lecturer, u, p, c):
            messagebox.showinfo("Success", "Account created. You can now log in.", parent=self)
            self.destroy()


# ---------------------------------------------------------- 4. Campus selection
class CampusSelectFrame(ttk.Frame):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.campuses = run_safely(self, app.campuses.list_campuses) or []
        self.choice, self.policy_text = tk.StringVar(), tk.StringVar()
        card = ttk.Frame(self, padding=30)
        card.place(relx=0.5, rely=0.4, anchor="center")
        ttk.Label(card, text=f"Welcome, {app.user.username}", style="Title.TLabel").pack()
        ttk.Label(card, text=f"Role: {app.user.ROLE_LABEL}").pack(pady=(0, 20))
        ttk.Label(card, text="Select a campus to work with:").pack(anchor="w")
        self.combo = ttk.Combobox(card, textvariable=self.choice, state="readonly", width=40,
                                  values=[c.name for c in self.campuses])
        self.combo.pack(pady=5)
        self.combo.bind("<<ComboboxSelected>>", self.on_select)
        ttk.Label(card, textvariable=self.policy_text, wraplength=420, foreground=NAVY).pack(pady=10)
        ttk.Button(card, text="Continue", style="Accent.TButton", command=self.proceed).pack(fill="x")
        if app.user.can("view_all"):
            ttk.Button(card, text="All campuses (system-wide view)", command=self.all_campuses).pack(
                fill="x", pady=5)
        ttk.Button(card, text="Logout", command=app.show_login).pack(fill="x")

    def on_select(self, _event=None):
        campus = self.selected()
        self.policy_text.set(campus.policy.describe() if campus else "")

    def selected(self):
        return next((c for c in self.campuses if c.name == self.choice.get()), None)

    def proceed(self):
        campus = self.selected()
        if campus is None:
            messagebox.showwarning("Select campus", "Please select a campus first.", parent=self)
            return
        self.app.campus = campus
        self.app.show_dashboard()

    def all_campuses(self):
        self.app.campus = None
        self.app.show_dashboard()


# ------------------------------------------------------------------ 3. Dashboard
class Dashboard(ttk.Frame):
    TAB_TITLES = {"book": "Book a Resource", "my_bookings": "My Bookings",
                  "resources": "Resource Management", "campus_bookings": "Campus Bookings",
                  "campuses": "All Campuses", "all_resources": "All Resources",
                  "all_bookings": "All Bookings", "reports": "Reports"}

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        header = tk.Frame(self, bg=NAVY)
        header.pack(fill="x")
        campus = app.campus
        ttk.Label(header, style="Header.TLabel", text=f"  User: {app.user}", padding=8).pack(side="left")
        ttk.Label(header, style="Header.TLabel", padding=8, text=(
            f"Active Campus: {campus.name}" if campus else "Active Campus: ALL (system-wide)")
                  ).pack(side="left", padx=30)
        ttk.Button(header, text="Logout", command=app.show_login).pack(side="right", padx=8, pady=4)
        if not app.user.can("view_campus_bookings"):
            ttk.Button(header, text="Change Campus", command=app.show_campus_select).pack(
                side="right", pady=4)
        policy = campus.policy.describe() if campus else "Each campus applies its own booking policy."
        ttk.Label(self, text=f"Current booking policy: {policy}", foreground="white", background=BLUE,
                  padding=6, wraplength=1050).pack(fill="x")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        for key in app.user.dashboard_tabs():          # polymorphic: depends on role class
            tab = self.build_tab(key)
            self.notebook.add(tab, text=self.TAB_TITLES[key])
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

    def build_tab(self, key):
        app, nb = self.app, self.notebook
        cid = app.campus.campus_id if app.campus else None
        if key == "book":
            return BookingFrame(nb, app)
        if key == "my_bookings":
            return HistoryFrame(nb, app)
        if key == "resources":
            return ResourceFrame(nb, app)
        if key == "reports":
            return ReportsFrame(nb, app)
        if key == "campus_bookings":
            return TableFrame(nb, Booking.ROW_COLUMNS, lambda: [b.as_row() for b in app.bookings.for_campus(cid)],
                              (50, 110, 150, 140, 90, 60, 60, 80, 90))
        if key == "all_bookings":
            return TableFrame(nb, Booking.ROW_COLUMNS, lambda: [b.as_row() for b in app.bookings.for_campus(None)],
                              (50, 110, 150, 140, 90, 60, 60, 80, 90))
        if key == "all_resources":
            return TableFrame(nb, ("Resource ID", "Campus", "Name", "Type"), self.all_resources, (120, 180, 200, 180))
        if key == "campuses":
            return TableFrame(nb, ("ID", "Campus", "Resources", "Booking Policy"), self.campus_rows, (40, 180, 80, 650))
        raise ValueError(key)

    def all_resources(self):
        names = {c.campus_id: c.name for c in self.app.campuses.list_campuses()}
        return [(r.resource_id, names.get(r.campus_id), r.name, r.resource_type)
                for r in self.app.resources.list_resources()]

    def campus_rows(self):
        return [(c.campus_id, c.name, len(self.app.resources.list_resources(c.campus_id)), c.policy.describe())
                for c in self.app.campuses.list_campuses()]

    def on_tab_change(self, _e=None):
        tab = self.nametowidget(self.notebook.select())
        if hasattr(tab, "refresh"):
            tab.refresh()


class TableFrame(ttk.Frame):
    """Generic read-only table with a Refresh button (used for operator/admin views)."""

    def __init__(self, parent, columns, loader, widths=None):
        super().__init__(parent, padding=10)
        self.loader = loader
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")
        self.count = ttk.Label(bar, text="")
        self.count.pack(side="left", padx=15)
        self.tree = make_tree(self, columns, widths, height=18)
        self.refresh()

    def refresh(self):
        rows = run_safely(self, self.loader) or []
        fill_tree(self.tree, rows)
        self.count.config(text=f"{len(rows)} record(s)")


# ---------------------------------------------------------- 6. Booking screen
class BookingFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.date = tk.StringVar(value=date.today().isoformat())
        self.start, self.duration = tk.StringVar(value="09:00"), tk.StringVar(value="60")
        form = ttk.LabelFrame(self, text="Booking details", padding=10)
        form.pack(fill="x")
        ttk.Label(form, text="Date (YYYY-MM-DD):").grid(row=0, column=0, padx=5)
        ttk.Entry(form, textvariable=self.date, width=14).grid(row=0, column=1, padx=5)
        ttk.Label(form, text="Start time:").grid(row=0, column=2, padx=5)
        self.start_cb = ttk.Combobox(form, textvariable=self.start, values=TIME_SLOTS, width=8)
        self.start_cb.grid(row=0, column=3, padx=5)
        ttk.Label(form, text="Duration (minutes):").grid(row=0, column=4, padx=5)
        self.dur_cb = ttk.Combobox(form, textvariable=self.duration, values=DURATIONS, width=8)
        self.dur_cb.grid(row=0, column=5, padx=5)
        ttk.Button(form, text="Check availability", command=self.refresh).grid(row=0, column=6, padx=10)
        for cb in (self.start_cb, self.dur_cb):
            cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(self, text="Resources on this campus (status reflects the date/time/duration above):"
                  ).pack(anchor="w", pady=(10, 3))
        self.tree = make_tree(self, ("Resource ID", "Name", "Type", "Availability"), (120, 200, 190, 450), 12)
        self.tree.tag_configure("ok", foreground="#1b7a2b")
        self.tree.tag_configure("bad", foreground="#b00020")
        ttk.Button(self, text="Book Selected Resource", style="Accent.TButton", command=self.book).pack(
            anchor="e", pady=10)
        self.refresh()
        self._auto_refresh()

    def _auto_refresh(self):
        """Poll every 30 s so availability stays current while the screen is open."""
        try:
            if self.winfo_exists():
                self.refresh()
                self.after(30000, self._auto_refresh)
        except tk.TclError:
            pass  # window was destroyed

    def refresh(self):
        campus = self.app.campus
        resources = run_safely(self, self.app.resources.list_resources, campus.campus_id) or []
        try:
            start, duration = self.app.bookings.parse(self.date.get(), self.start.get(), self.duration.get())
        except ServiceError as exc:
            fill_tree(self.tree, [(r.resource_id, r.name, r.resource_type, f"Check input: {exc}") for r in resources])
            return
        rows, tags = [], []
        for r in resources:
            status = run_safely(self, self.app.bookings.availability, r, start, duration) or "Unknown"
            rows.append((r.resource_id, r.name, r.resource_type, status))
            tags.append("ok" if status == "Available" else "bad")
        fill_tree(self.tree, rows, tags)

    def book(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select resource", "Please select a resource to book.", parent=self)
            return
        rid, name, _, status = self.tree.item(sel[0], "values")
        if status != "Available" and not status.startswith("Check input"):
            messagebox.showwarning("Unavailable", f"{name} cannot be booked: {status}", parent=self)
            return
        ok = run_safely(self, lambda: (self.app.bookings.create(
            self.app.user, rid, self.date.get(), self.start.get(), self.duration.get()), True)[1])
        if ok:
            messagebox.showinfo("Booked", f"{name} booked on {self.date.get()} at {self.start.get()} "
                                f"for {fmt_duration(int(self.duration.get()))}.", parent=self)
            self.refresh()


# ------------------------------------------------ 7. Booking history / active
class HistoryFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        active = ttk.LabelFrame(self, text="Active bookings", padding=8)
        active.pack(fill="both", expand=True)
        self.active_tree = make_tree(active, Booking.ROW_COLUMNS, (50, 110, 150, 140, 90, 60, 60, 80, 90), 6)
        bar = ttk.Frame(active)
        bar.pack(fill="x", pady=5)
        ttk.Button(bar, text="Cancel Selected Booking", command=self.cancel).pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=8)
        hist = ttk.LabelFrame(self, text="Booking history (completed and cancelled)", padding=8)
        hist.pack(fill="both", expand=True, pady=(10, 0))
        self.hist_tree = make_tree(hist, Booking.ROW_COLUMNS, (50, 110, 150, 140, 90, 60, 60, 80, 90), 6)
        self.refresh()

    def refresh(self):
        bookings = run_safely(self, self.app.bookings.for_user, self.app.user.user_id) or []
        fill_tree(self.active_tree, [b.as_row() for b in bookings if b.is_active()])
        fill_tree(self.hist_tree, [b.as_row() for b in bookings if not b.is_active()])

    def cancel(self):
        sel = self.active_tree.selection()
        if not sel:
            messagebox.showwarning("Select booking", "Select an active booking to cancel.", parent=self)
            return
        values = self.active_tree.item(sel[0], "values")
        if not messagebox.askyesno("Confirm", f"Cancel booking #{values[0]} ({values[2]}, {values[4]} {values[5]})?",
                                   parent=self):
            return
        run_safely(self, self.app.bookings.cancel, self.app.user, int(values[0]))
        self.refresh()


# --------------------------------------------------- 5. Resource management
class ResourceFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.rid, self.name, self.rtype = tk.StringVar(), tk.StringVar(), tk.StringVar()
        form = ttk.LabelFrame(self, text="Resource details", padding=10)
        form.pack(fill="x")
        ttk.Label(form, text="Resource ID:").grid(row=0, column=0, padx=5)
        self.id_entry = ttk.Entry(form, textvariable=self.rid, width=16)
        self.id_entry.grid(row=0, column=1, padx=5)
        ttk.Label(form, text="Name:").grid(row=0, column=2, padx=5)
        ttk.Entry(form, textvariable=self.name, width=24).grid(row=0, column=3, padx=5)
        ttk.Label(form, text="Type:").grid(row=0, column=4, padx=5)
        ttk.Combobox(form, textvariable=self.rtype, values=RESOURCE_TYPES, state="readonly", width=24
                     ).grid(row=0, column=5, padx=5)
        bar = ttk.Frame(form)
        bar.grid(row=1, column=0, columnspan=6, pady=(10, 0), sticky="w")
        for text, cmd in [("Add", self.add), ("Update", self.update), ("Delete", self.delete), ("Clear", self.clear)]:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=4)
        ttk.Label(self, text="Select a row to edit or delete it. The Resource ID cannot be changed."
                  ).pack(anchor="w", pady=(8, 3))
        self.tree = make_tree(self, ("Resource ID", "Name", "Type"), (150, 280, 220), 14)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.refresh()

    def refresh(self):
        rows = run_safely(self, self.app.resources.list_resources, self.app.campus.campus_id) or []
        fill_tree(self.tree, [(r.resource_id, r.name, r.resource_type) for r in rows])

    def on_select(self, _e=None):
        sel = self.tree.selection()
        if sel:
            rid, name, rtype = self.tree.item(sel[0], "values")
            self.rid.set(rid)
            self.name.set(name)
            self.rtype.set(rtype)
            self.id_entry.state(["disabled"])

    def clear(self):
        self.rid.set("")
        self.name.set("")
        self.rtype.set("")
        self.id_entry.state(["!disabled"])
        self.tree.selection_remove(self.tree.selection())

    def add(self):
        u, c = self.app.user, self.app.campus.campus_id
        before = len(self.tree.get_children())
        run_safely(self, self.app.resources.add, u, c, self.rid.get(), self.name.get(), self.rtype.get())
        self.refresh()
        if len(self.tree.get_children()) > before:
            messagebox.showinfo("Added", "Resource added.", parent=self)
            self.clear()

    def update(self):
        if not self.tree.selection():
            messagebox.showwarning("Select resource", "Select a resource to update.", parent=self)
            return
        run_safely(self, self.app.resources.update, self.app.user, self.rid.get(), self.name.get(), self.rtype.get())
        self.refresh()

    def delete(self):
        if not self.tree.selection():
            messagebox.showwarning("Select resource", "Select a resource to delete.", parent=self)
            return
        if messagebox.askyesno("Confirm delete", f"Delete resource {self.rid.get()} permanently?", parent=self):
            run_safely(self, self.app.resources.delete, self.app.user, self.rid.get())
            self.refresh()
            self.clear()


# ------------------------------------------------------------ 8. Reports screen
class ReportsFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.summary = tk.StringVar()
        self.cross = app.user.can("cross_reports")
        inner = ttk.Notebook(self)
        inner.pack(fill="both", expand=True)
        if app.campus is not None:
            box = ttk.Frame(inner, padding=8)
            inner.add(box, text=f"Campus report: {app.campus.name}")
            ttk.Label(box, textvariable=self.summary, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(box, text="Resource usage (most used first):").pack(anchor="w", pady=(8, 2))
            self.top_tree = make_tree(box, ("Resource", "Type", "Bookings", "Hours booked"), (220, 200, 100, 120), 6)
            ttk.Label(box, text="Booking trend by month:").pack(anchor="w", pady=(8, 2))
            self.trend_tree = make_tree(box, ("Month", "Bookings"), (120, 100), 3)
        if self.cross:
            box = ttk.Frame(inner, padding=8)
            inner.add(box, text="Cross-campus comparison")
            self.stats_tree = make_tree(box, ("Campus", "Resources", "Bookings", "Avg duration", "Hours booked",
                                              "Cancelled", "Most used", "Policy"),
                                        (150, 70, 70, 90, 90, 70, 140, 400), 4)
            self.canvas = tk.Canvas(box, height=120, bg="white", highlightthickness=0)
            self.canvas.pack(fill="x", pady=5)
            self.type_tree = make_tree(box, ("Campus", "Resource type", "Bookings"), (180, 200, 80), 4)
            self.ctrend_tree = make_tree(box, ("Campus", "Month", "Bookings"), (180, 100, 80), 3)
        ttk.Button(self, text="Refresh reports", command=self.refresh).pack(anchor="e", pady=5)
        self.refresh()

    def refresh(self):
        if self.app.campus is not None:
            rep = run_safely(self, self.app.reports.campus_report, self.app.campus.campus_id)
            if rep:
                self.summary.set(f"Total bookings: {rep['total']}    Average duration: "
                                 f"{fmt_duration(round(rep['avg_minutes']))}    Cancelled: {rep['cancelled']}")
                fill_tree(self.top_tree, [(n, t, c, f"{m / 60:.1f}") for n, t, c, m in rep["top"]])
                fill_tree(self.trend_tree, rep["trend"])
        if self.cross:
            data = run_safely(self, self.app.reports.cross_campus)
            if data:
                fill_tree(self.stats_tree, [(s["campus"], s["resources"], s["bookings"],
                                             fmt_duration(round(s["avg_minutes"])), f"{s['hours']:.1f}",
                                             s["cancelled"], s["top"], s["policy"]) for s in data["stats"]])
                fill_tree(self.type_tree, data["by_type"])
                fill_tree(self.ctrend_tree, data["trend"])
                self.draw_chart(data["stats"])

    def draw_chart(self, stats):
        """Simple bar chart comparing total bookings per campus."""
        c = self.canvas
        c.delete("all")
        top = max([s["bookings"] for s in stats] + [1])
        for i, s in enumerate(stats):
            y = 12 + i * 34
            c.create_text(8, y + 10, text=s["campus"], anchor="w", font=("Segoe UI", 9))
            width = 40 + int(400 * s["bookings"] / top) if s["bookings"] else 4
            c.create_rectangle(180, y, 180 + width, y + 20, fill=BLUE, outline="")
            c.create_text(188 + width, y + 10, text=str(s["bookings"]), anchor="w", font=("Segoe UI", 9, "bold"))
