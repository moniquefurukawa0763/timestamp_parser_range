# timestamp-parser-range

Parses ISO 8601 timestamps (calendar date plus optional time, fractional seconds, and UTC offset) and raises `ValueError` on anything ambiguous or non-compliant. Also provides a `TimestampRange` for half-open `[start, stop)` iteration and membership.

## Usage

```python
from timestamp_parser_range import parse_timestamp, TimestampRange, TimestampParseError

try:
    a = parse_timestamp("2023-01-15T12:30:45.123Z")
    b = parse_timestamp("2023-01-15T12:31:00Z")
    rng = TimestampRange(a, b)
    for ts in rng:
        print(ts.dt.isoformat())
    print(parse_timestamp("2023-01-15T12:30:50Z") in rng)
except TimestampParseError as e:
    print(e)
```

## Why

`datetime.fromisoformat` drifts between Python versions: 3.7 rejected `Z`, 3.11 accepted it, fractional-minute handling changed, and ordinal/week-date support came and went. This library pins one grammar and rejects everything outside it, so a string that parses today parses the same way on every interpreter.

The trade-off is strictness. We reject week dates (`2023-W01-1`), ordinal dates (`2023-001`), leap seconds (`23:59:60`), fractional minutes, and `±HH:MM:SS` offsets. If you need those, this is the wrong library.

## The awkward edge

A timestamp without an offset and a timestamp with `+00:00` are **not comparable**. `TimestampRange` raises if you mix them, and membership tests raise too. This is deliberate: there is no correct way to compare an offset-unspecified time with an offset-specified one, and guessing would defeat the point of the library.

## Exports

- `parse_timestamp(s: str) -> ParsedTimestamp` — parse one timestamp.
- `TimestampRange(start, stop)` — half-open range; iterable, supports `in`.
- `TimestampParseError` — subclass of `ValueError`, raised on every rejection.
- `ParsedTimestamp` — returned by `parse_timestamp`; carries `.dt` (a `datetime`), `.offset` (a `timedelta` or `None`), `.has_offset`, and `.is_utc`.
