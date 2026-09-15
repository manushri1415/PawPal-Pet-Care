"""The visitor's own clock, for every user-facing notion of "today".

The server's clock is the wrong one to ask. In production the API runs on AWS
Lambda, whose clock is UTC, while a visitor's day is local: at 8 pm in Chicago
it is already tomorrow in UTC, so a server-side ``datetime.now()`` would plan
tomorrow's schedule, date a new task tomorrow and call a vaccine due today
"due tomorrow". The browser is the only party that knows the visitor's day, so
the frontend sends its local wall-clock time with every request
(``X-PawPal-Client-Now``, a timezone-less ISO datetime) and everything
date-sensitive reads it from here.

Everything the scheduler stores is local wall-clock time without a timezone --
a task's ``scheduled_time`` is "08:30" in the owner's day, not in UTC -- so the
datetimes this module hands out are naive local datetimes too.

A missing or implausible header falls back to the server's UTC clock and is
logged: API clients that aren't the SPA (curl, tests) still work, but that
fallback is never silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import Header

CLIENT_NOW_HEADER = "X-PawPal-Client-Now"

# Real UTC offsets run from -12:00 to +14:00. Anything further from the
# server's clock than that plus a little clock skew is not a timezone -- it is
# a wrong or forged clock, and trusting it would let a request pick an
# arbitrary "today".
_MAX_SKEW = timedelta(hours=14, minutes=30)

_log = logging.getLogger("pawpal.clock")


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class ClientClock:
    """The visitor's local wall-clock time as of this request."""

    now: datetime  # naive, local to the visitor
    # Local minus UTC, rounded to the quarter hour every real offset is a
    # multiple of; None when the time came from the server's own clock.
    utc_offset: Optional[timedelta]

    @property
    def today(self) -> date:
        return self.now.date()

    def to_local(self, value: Optional[datetime]) -> Optional[datetime]:
        """Normalize an incoming datetime to naive local wall-clock time.

        Naive values are already local and pass through. An aware value -- an
        API client sending "...Z" -- is converted with this visitor's offset
        when it is known, else to UTC, and then stripped of its timezone, so
        naive and aware datetimes never meet in a comparison (``Task.has_ended``
        raises TypeError on that).
        """
        if value is None or value.tzinfo is None:
            return value
        utc = value.astimezone(timezone.utc).replace(tzinfo=None)
        return utc + self.utc_offset if self.utc_offset is not None else utc

    @classmethod
    def from_header(cls, raw: Optional[str], server_utc_now: Optional[datetime] = None) -> "ClientClock":
        server_now = server_utc_now or _utcnow_naive()
        if raw:
            try:
                parsed = datetime.fromisoformat(raw.strip())
            except ValueError:
                parsed = None
            if parsed is not None and parsed.tzinfo is None:
                skew = parsed - server_now
                if abs(skew) <= _MAX_SKEW:
                    quarter_hours = round(skew / timedelta(minutes=15))
                    return cls(now=parsed, utc_offset=timedelta(minutes=15 * quarter_hours))
            _log.warning("Ignoring an invalid %s header; using the server clock (UTC).", CLIENT_NOW_HEADER)
        return cls(now=server_now, utc_offset=None)


def get_client_clock(
    x_pawpal_client_now: Optional[str] = Header(default=None, alias=CLIENT_NOW_HEADER),
) -> ClientClock:
    """FastAPI dependency: this request's :class:`ClientClock`."""
    return ClientClock.from_header(x_pawpal_client_now)
