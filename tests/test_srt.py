import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from subsgen.domain import SubtitleSegment
from subsgen.srt import (
    PDF, RLE, RLM, SrtError, parse_srt, parse_timestamp, save_srt, serialize_ass, serialize_srt, serialize_vtt,
)
from subsgen.timeline import repair_segments


class SrtTests(unittest.TestCase):
    def test_round_trip_unicode_and_multiline_text(self):
        source = [
            SubtitleSegment("one", 1234, 5678, "Hello\nworld"),
            SubtitleSegment("two", 6000, 7000, "שלום עולם"),
        ]
        rendered = serialize_srt(source)
        parsed = parse_srt(rendered)
        self.assertEqual([(s.start_ms, s.end_ms, s.text) for s in parsed],
                         [(1234, 5678, "Hello\nworld"), (6000, 7000, "שלום עולם")])

    def test_hebrew_repair_is_idempotent(self):
        source = [SubtitleSegment("one", 0, 1000, f"{RLE}{RLM}שלום, OpenAI!{PDF}")]
        first = serialize_srt(source, repair_hebrew=True)
        parsed = parse_srt(first)
        second = serialize_srt(parsed, repair_hebrew=True)
        self.assertEqual(first, second)
        self.assertEqual(first.count(RLE), 1)
        self.assertEqual(first.count(PDF), 1)

    def test_accepts_bom_decimal_dot_and_missing_index(self):
        parsed = parse_srt("\ufeff00:00:00.000 --> 00:00:01.000\nText\n")
        self.assertEqual(parsed[0].text, "Text")

    def test_rejects_malformed_timestamp(self):
        with self.assertRaises(SrtError):
            parse_srt("1\nnot a timestamp\nText\n")

    def test_preserves_text_while_repairing_overlap(self):
        parsed = parse_srt("1\n00:00:00,000 --> 00:00:02,000\nA\n\n2\n00:00:01,000 --> 00:00:03,000\nB\n")
        repaired, count = repair_segments(parsed)
        self.assertGreater(count, 0)
        self.assertEqual([item.text for item in repaired], ["A", "B"])
        self.assertLessEqual(repaired[0].end_ms, repaired[1].start_ms)

    def test_timestamp_parser(self):
        self.assertEqual(parse_timestamp("01:02:03.004"), 3_723_004)
        with self.assertRaises(ValueError):
            parse_timestamp("00:70:00.000")

    def test_failed_atomic_overwrite_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "original.srt"
            destination.write_text("original", encoding="utf-8")
            with patch("subsgen.srt.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_srt(destination, [SubtitleSegment("one", 0, 1000, "replacement")])
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])

    def test_vtt_and_ass_exports_preserve_timing_and_multiline_text(self):
        segments = [SubtitleSegment("one", 1234, 5678, "First line\nSecond line")]
        vtt = serialize_vtt(segments)
        ass = serialize_ass(segments)
        self.assertTrue(vtt.startswith("WEBVTT\n"))
        self.assertIn("00:00:01.234 --> 00:00:05.678", vtt)
        self.assertIn("First line\nSecond line", vtt)
        self.assertIn("Dialogue: 0,0:00:01.23,0:00:05.67", ass)
        self.assertIn(r"First line\NSecond line", ass)


if __name__ == "__main__":
    unittest.main()
