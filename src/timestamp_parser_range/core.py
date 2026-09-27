"""Strict ISO 8601 timestamp parser.

Scope decisions (stated plainly so the tests can hold us to them):

1. Calendar dates only: ``YYYY-MM-DD``. Week dates (``YYYY-Www-d``) and ordinal
   dates (``YYYY-DDD``) are rejected. Supporting them would introduce ambiguity
   in how a "range" between two timestamps advances day-by-day, and the brief
   asks us to reject ambiguity rather than paper over it.

2. Time is optional, but when present must include hours and minutes. Seconds
   are optional. Fractional seconds are allowed on the *seconds* field only —
   not on minutes or hours. This matches the most common reading of ISO 8601
   and keeps the grammar unambiguous.

3. The offset is optional. If absent the string is treated as *offset-unspecified*
   (not UTC). A timestamp without an offset and a timestamp with ``+00:00`` are
   therefore NOT comparable, and ``TimestampRange`` will raise if you mix them.
   This is the awkward edge; see README.

4. ``Z`` is accepted as a synonym for ``+00:00``.

5. Offsets must be ``±HH:MM`` or ``±HHMM`` or ``±HH``. We do not accept the
   (non-standard) ``±HH:MM:SS`` form.

6. No leap seconds. ``23:59:60`` is rejected. Python's ``datetime`` cannot
   represent it, and silently coercing it to ``00:00:00`` of the next day would
   be exactly the kind of quiet rewrite the brief tells us to avoid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Iterator, Optional


class TimestampParseError(ValueError):
    """Raised when a string is not a compliant, unambiguous ISO 8601 timestamp.

    Subclassing ValueError keeps the contract documented in the README
    ("raises a ValueError") honest while still letting callers catch the
    specific error if they want.
    """


# One regex, one grammar. We deliberately do NOT fall back to
# datetime.fromisoformat because its behaviour drifts between Python versions
# (3.11 accepted 'Z', 3.7 did not; fractional-minute handling changed too).
# Pinning our own grammar makes the tests deterministic across versions.
_DATE = r"(\d{4})-(\d{2})-(\d{2})"
_TIME = r"(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?"
_OFFSET = r"([Zz]|[+-]\d{2}(?::?\d{2})?|[+-]\d{2}:\d{2})"
_FULL = re.compile(rf"^{_DATE}(?:[Tt ]{_TIME})?{_OFFSET}?$")


@dataclass(frozen=True)
class ParsedTimestamp:
    """A parsed timestamp with its offset status made explicit.

    Carrying ``offset`` separately from the ``datetime`` lets us distinguish
    "no offset was given" from "offset was +00:00" — a distinction that matters
    for range arithmetic and that a bare ``datetime`` cannot express on its own
    (a naive datetime and an aware UTC datetime are different types, but two
    aware UTC datetimes are indistinguishable regardless of whether the source
    string carried an offset).
    """

    dt: datetime
    offset: Optional[timedelta]

    @property
    def is_utc(self) -> bool:
        return self.offset == timedelta(0)

    @property
    def has_offset(self) -> bool:
        return self.offset is not None


def _parse_offset(raw: str) -> Optional[timedelta]:
    if raw == "":
        return None
    if raw in ("Z", "z"):
        return timedelta(0)
    sign = 1 if raw[0] == "+" else -1
    body = raw[1:].replace(":", "")
    if len(body) == 2:
        hours = int(body)
        minutes = 0
    elif len(body) == 4:
        hours = int(body[:2])
        minutes = int(body[2:])
    else:
        raise TimestampParseError(f"unrecognized offset: {raw!r}")
    if hours > 23 or minutes > 59:
        raise TimestampParseError(f"offset out of range: {raw!r}")
    return sign * timedelta(hours=hours, minutes=minutes)


def _to_tz(offset: timedelta) -> tzinfo:
    return timezone(offset)


def parse_timestamp(s: str) -> ParsedTimestamp:
    """Parse a single ISO 8601 timestamp.

    Raises TimestampParseError (a ValueError subclass) on anything ambiguous
    or non-compliant.
    """
    if not isinstance(s, str):
        raise TimestampParseError(f"expected str, got {type(s).__name__}")
    m = _FULL.match(s)
    if m is None:
        raise TimestampParseError(f"not ISO 8601: {s!r}")
    year, month, day, hour, minute, second, frac, offset_raw = m.groups()
    try:
        if hour is None:
            dt = datetime(int(year), int(month), int(day))
        else:
            second_int = int(second) if second is not None else 0
            micros = 0
            if frac is not None:
                # Pad/truncate to 6 digits for microseconds. We truncate rather
                # than round: rounding 999999 up to 1000000 would roll the
                # second forward, which is a silent data change.
                micros = int((frac + "000000")[:6])
            dt = datetime(
                int(year), int(month), int(day),
                int(hour), int(minute), second_int, micros,
            )
    except ValueError as e:
        raise TimestampParseError(f"out-of-range field in {s!r}: {e}") from e

    offset = _parse_offset(offset_raw or "")
    if offset is not None:
        dt = dt.replace(tzinfo=_to_tz(offset))
    return ParsedTimestamp(dt=dt, offset=offset)


@dataclass(frozen=True)
class TimestampRange:
    """A half-open range ``[start, stop)`` over parsed timestamps.

    Both endpoints must carry an offset, or both must omit one. Mixing the two
    is rejected because there is no well-defined way to compare an
    offset-unspecified time with an offset-specified one; guessing would
    violate the brief's "no ambiguity" rule.
    """

    start: ParsedTimestamp
    stop: ParsedTimestamp

    def __post_init__(self) -> None:
        if self.start.has_offset != self.stop.has_offset:
            raise TimestampParseError(
                "cannot form a range mixing offset-specified and "
                "offset-unspecified timestamps"
            )
        if self.start.dt > self.stop.dt:
            raise TimestampParseError(
                f"range start {self.start.dt!r} is after stop {self.stop.dt!r}"
            )
        if self.start.dt == self.stop.dt:
            # Half-open empty range is allowed; iteration yields nothing.
            return

    def __contains__(self, ts: ParsedTimestamp) -> bool:
        self._check_comparable(ts)
        return self.start.dt <= ts.dt < self.stop.dt

    def __iter__(self) -> Iterator[ParsedTimestamp]:
        # Iterate by whole seconds. Sub-second endpoints are respected for
        # membership but not for iteration granularity; iterating at microsecond
        # resolution would explode memory for a one-day range.
        cur = self.start.dt.replace(microsecond=0)
        stop = self.stop.dt
        # If start had fractional seconds, the first yielded value is the
        # floor; this keeps iteration stable and predictable.
        while cur < stop:
            yield ParsedTimestamp(dt=cur, offset=self.start.offset)
            cur = cur + timedelta(seconds=1)

    def _check_comparable(self, ts: ParsedTimestamp) -> None:
        if ts.has_offset != self.start.has_offset:
            raise TimestampParseError(
                "timestamp offset status does not match range"
            )
