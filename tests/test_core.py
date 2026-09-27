import unittest
from datetime import datetime, timedelta, timezone

from timestamp_parser_range import (
    parse_timestamp,
    TimestampRange,
    TimestampParseError,
)


class TestParseTimestamp(unittest.TestCase):
    def test_date_only(self):
        p = parse_timestamp("2023-01-15")
        self.assertEqual(p.dt, datetime(2023, 1, 15))
        self.assertFalse(p.has_offset)

    def test_date_time_utc_z(self):
        p = parse_timestamp("2023-01-15T12:30:45Z")
        self.assertEqual(p.dt, datetime(2023, 1, 15, 12, 30, 45, tzinfo=timezone.utc))
        self.assertTrue(p.is_utc)

    def test_lowercase_z(self):
        p = parse_timestamp("2023-01-15t12:30:45z")
        self.assertTrue(p.is_utc)

    def test_fractional_seconds(self):
        p = parse_timestamp("2023-01-15T12:30:45.123456Z")
        self.assertEqual(p.dt.microsecond, 123456)

    def test_fractional_seconds_truncated_not_rounded(self):
        p = parse_timestamp("2023-01-15T12:30:45.9999999Z")
        # 7 nines -> truncated to 6, NOT rounded up to 1000000 (which would
        # roll the second forward).
        self.assertEqual(p.dt.microsecond, 999999)
        self.assertEqual(p.dt.second, 45)

    def test_offset_plus(self):
        p = parse_timestamp("2023-01-15T12:30:45+05:30")
        self.assertEqual(p.offset, timedelta(hours=5, minutes=30))
        self.assertEqual(p.dt.utcoffset(), timedelta(hours=5, minutes=30))

    def test_offset_no_colon(self):
        p = parse_timestamp("2023-01-15T12:30:45+0530")
        self.assertEqual(p.offset, timedelta(hours=5, minutes=30))

    def test_offset_hours_only(self):
        p = parse_timestamp("2023-01-15T12:30:45+05")
        self.assertEqual(p.offset, timedelta(hours=5))

    def test_offset_negative(self):
        p = parse_timestamp("2023-01-15T12:30:45-08:00")
        self.assertEqual(p.offset, timedelta(hours=-8))

    def test_space_separator(self):
        p = parse_timestamp("2023-01-15 12:30:45Z")
        self.assertTrue(p.is_utc)

    def test_seconds_optional(self):
        p = parse_timestamp("2023-01-15T12:30Z")
        self.assertEqual(p.dt.second, 0)

    def test_reject_leap_second(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2016-12-31T23:59:60Z")

    def test_reject_bad_month(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2023-13-01")

    def test_reject_bad_day(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2023-02-30")

    def test_reject_week_date(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2023-W01-1")

    def test_reject_ordinal_date(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2023-001")

    def test_reject_fractional_minutes(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2023-01-15T12:30.5Z")

    def test_reject_offset_seconds(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("2023-01-15T12:30:45+00:00:00")

    def test_reject_garbage(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp("not a timestamp")

    def test_reject_non_string(self):
        with self.assertRaises(TimestampParseError):
            parse_timestamp(12345)  # type: ignore[arg-type]


class TestTimestampRange(unittest.TestCase):
    def test_basic_range(self):
        a = parse_timestamp("2023-01-01T00:00:00Z")
        b = parse_timestamp("2023-01-01T00:00:10Z")
        r = TimestampRange(a, b)
        self.assertEqual(len(list(r)), 10)

    def test_membership_inclusive_start_exclusive_stop(self):
        a = parse_timestamp("2023-01-01T00:00:00Z")
        b = parse_timestamp("2023-01-01T00:00:03Z")
        r = TimestampRange(a, b)
        self.assertIn(parse_timestamp("2023-01-01T00:00:00Z"), r)
        self.assertIn(parse_timestamp("2023-01-01T00:00:02Z"), r)
        self.assertNotIn(parse_timestamp("2023-01-01T00:00:03Z"), r)

    def test_empty_range_iterates_zero(self):
        a = parse_timestamp("2023-01-01T00:00:00Z")
        r = TimestampRange(a, a)
        self.assertEqual(list(r), [])

    def test_reject_backwards_range(self):
        a = parse_timestamp("2023-01-01T00:00:10Z")
        b = parse_timestamp("2023-01-01T00:00:00Z")
        with self.assertRaises(TimestampParseError):
            TimestampRange(a, b)

    def test_reject_mixed_offsets(self):
        a = parse_timestamp("2023-01-01T00:00:00")
        b = parse_timestamp("2023-01-01T00:00:10Z")
        with self.assertRaises(TimestampParseError):
            TimestampRange(a, b)

    def test_membership_rejects_mismatched_offset(self):
        a = parse_timestamp("2023-01-01T00:00:00Z")
        b = parse_timestamp("2023-01-01T00:00:10Z")
        r = TimestampRange(a, b)
        with self.assertRaises(TimestampParseError):
            _ = parse_timestamp("2023-01-01T00:00:05") in r

    def test_iteration_floors_fractional_start(self):
        a = parse_timestamp("2023-01-01T00:00:00.5Z")
        b = parse_timestamp("2023-01-01T00:00:03Z")
        r = TimestampRange(a, b)
        # Floor of 00:00:00.5 is 00:00:00, so we get 3 values.
        self.assertEqual(len(list(r)), 3)

    def test_naive_range_works(self):
        a = parse_timestamp("2023-01-01T00:00:00")
        b = parse_timestamp("2023-01-01T00:00:03")
        r = TimestampRange(a, b)
        self.assertEqual(len(list(r)), 3)


if __name__ == "__main__":
    unittest.main()
