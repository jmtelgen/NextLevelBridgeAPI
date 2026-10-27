"""Validated, persisted deadlines; clocks are injected by the runtime in tests."""
import os
import time
from dataclasses import dataclass
from decimal import Decimal


def now_ms():
    return int(time.time() * 1000)


def _milliseconds(name, default, minimum):
    value = os.environ.get(name, str(default))
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{name} must be an integer from {minimum} to 10000")
    result = int(value)
    if not minimum <= result <= 10000:
        raise ValueError(f"{name} must be an integer from {minimum} to 10000")
    return result


@dataclass(frozen=True)
class Pacing:
    robot_card_delay_ms: int = 700
    trick_hold_ms: int = 1200

    @classmethod
    def from_environment(cls):
        return cls(
            _milliseconds("ROBOT_CARD_DELAY_MS", 700, 100),
            _milliseconds("TRICK_HOLD_MS", 1200, 1000),
        )

    @classmethod
    def for_room(cls, room):
        settings = room.get("practiceSettings")
        from lambdas.core.game.runtime import solo_room
        if not settings or not solo_room(room):
            return cls.from_environment()
        return cls.validated(settings)

    @classmethod
    def validated(cls, settings):
        values = []
        for key, minimum in (("robotCardDelayMs", 100), ("trickHoldMs", 1000)):
            value = settings.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, Decimal)) \
                    or value != int(value) or not minimum <= value <= 10000:
                raise ValueError(f"{key} must be an integer from {minimum} to 10000")
            values.append(int(value))
        return cls(*values)

    def public(self):
        return {"robotCardDelayMs": self.robot_card_delay_ms,
                "trickHoldMs": self.trick_hold_ms}
