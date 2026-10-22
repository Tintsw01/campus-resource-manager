"""Booking policies (Strategy pattern).

Each campus has one BookingPolicy subclass. Rules live ONLY here, so the booking
service never contains campus-specific ``if`` statements. To add a campus rule set:
subclass BookingPolicy, decorate with @register_policy, and store the class name
in campuses.booking_policy. No other code changes are needed.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

POLICY_REGISTRY = {}


def register_policy(cls):
    """Class decorator that makes a policy discoverable by its class name."""
    POLICY_REGISTRY[cls.__name__] = cls
    return cls


def get_policy(key):
    """Return a policy instance for the stored key (falls back to the default policy)."""
    return POLICY_REGISTRY.get(key, DefaultPolicy)()


class BookingPolicy(ABC):
    """Abstract base class: common rules + campus-specific rules."""

    ABSOLUTE_MAX_MINUTES = 480  # no booking may ever exceed 8 hours

    def validate(self, resource_type, start, duration, now=None):
        """Return a list of human-readable rule violations (empty list = valid)."""
        now = now or datetime.now()
        errors = []
        end = start + timedelta(minutes=duration)
        if duration <= 0:
            errors.append("Duration must be greater than zero.")
        if duration > self.ABSOLUTE_MAX_MINUTES:
            errors.append("No booking may exceed 8 hours.")
        if start < now:
            errors.append("Bookings cannot start in the past.")
        if end.date() != start.date():
            errors.append("A booking must finish on the same day it starts.")
        errors.extend(self.check_rules(resource_type, start, end, duration, now))
        return errors

    @abstractmethod
    def check_rules(self, resource_type, start, end, duration, now):
        """Campus-specific rules; return a list of violation messages."""

    @abstractmethod
    def describe(self):
        """Short text shown in the GUI so users know which policy applies."""


@register_policy
class DefaultPolicy(BookingPolicy):
    """Fallback used for campuses added without a custom policy."""

    def check_rules(self, resource_type, start, end, duration, now):
        return []

    def describe(self):
        return "Standard policy: maximum 8 hours per booking."


@register_policy
class JohannesburgPolicy(BookingPolicy):
    MAX_MINUTES = 240

    def check_rules(self, resource_type, start, end, duration, now):
        if duration > self.MAX_MINUTES:
            return ["Johannesburg: maximum booking duration is 4 hours."]
        return []

    def describe(self):
        return "Johannesburg policy: maximum booking duration 4 hours per session."


@register_policy
class PretoriaPolicy(BookingPolicy):
    OPEN, CLOSE = (8, 0), (17, 0)

    def check_rules(self, resource_type, start, end, duration, now):
        open_t = start.replace(hour=self.OPEN[0], minute=self.OPEN[1])
        close_t = start.replace(hour=self.CLOSE[0], minute=self.CLOSE[1])
        if start < open_t or end > close_t:
            return ["Pretoria: bookings must fall between 08:00 and 17:00."]
        return []

    def describe(self):
        return "Pretoria policy: bookings allowed 08:00 to 17:00 only."


@register_policy
class DurbanPolicy(BookingPolicy):
    """Max 2 hours. Projectors have priority access: they can be booked up to
    30 days ahead, while all other resources can only be booked 7 days ahead."""
    MAX_MINUTES = 120
    PRIORITY_TYPES = {"Multimedia Projector"}
    PRIORITY_WINDOW_DAYS, STANDARD_WINDOW_DAYS = 30, 7

    def check_rules(self, resource_type, start, end, duration, now):
        errors = []
        if duration > self.MAX_MINUTES:
            errors.append("Durban: maximum booking duration is 2 hours.")
        days = self.PRIORITY_WINDOW_DAYS if resource_type in self.PRIORITY_TYPES \
            else self.STANDARD_WINDOW_DAYS
        if start > now + timedelta(days=days):
            errors.append(f"Durban: this resource type can only be booked {days} days ahead.")
        return errors

    def describe(self):
        return ("Durban policy: maximum 2 hours per session. Projectors have priority access "
                "(bookable 30 days ahead; other resources 7 days ahead).")
