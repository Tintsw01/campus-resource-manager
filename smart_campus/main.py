"""Entry point: python main.py"""
from tkinter import messagebox
import tkinter as tk

from campus_booking.database import DatabaseError
from campus_booking.gui import App


def main():
    try:
        App().mainloop()
    except DatabaseError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Startup error", str(exc))


if __name__ == "__main__":
    main()
