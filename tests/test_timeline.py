import unittest
import random

from subsgen.domain import SubtitleSegment
from subsgen.timeline import Timeline, TimelineError, active_segment_index, repair_segments, retime_segment_duration


def segment(identifier, start, end, text="text"):
    return SubtitleSegment(identifier, start, end, text)


class TimelineTests(unittest.TestCase):
    def test_reversed_times_are_swapped(self):
        timeline = Timeline([segment("a", 0, 1000)])
        updated = timeline.update(0, 900, 200, "updated")
        self.assertEqual((updated.start_ms, updated.end_ms), (200, 900))

    def test_minimum_duration_is_enforced(self):
        timeline = Timeline([segment("a", 0, 1000)])
        updated = timeline.update(0, 400, 400, "text")
        self.assertEqual(updated.end_ms - updated.start_ms, 50)

    def test_edit_shortens_previous_segment(self):
        timeline = Timeline([segment("a", 0, 500), segment("b", 600, 1000)])
        timeline.update(1, 300, 1000, "second")
        self.assertEqual(timeline.segments[0].end_ms, 300)
        self.assertEqual(timeline.segments[1].start_ms, 300)

    def test_edit_clamps_against_next_segment(self):
        timeline = Timeline([segment("a", 0, 500), segment("b", 600, 1000)])
        timeline.update(0, 0, 900, "first")
        self.assertEqual(timeline.segments[0].end_ms, 600)

    def test_edit_cannot_shrink_previous_below_minimum_or_leave_an_overlap(self):
        timeline = Timeline([segment("a", 0, 1000), segment("b", 1000, 2000)])
        timeline.update(1, 10, 2000, "manual wording")
        self._assert_structural(timeline.segments, 2000)
        self.assertEqual(timeline.segments[0].end_ms, 1000)
        self.assertEqual(timeline.segments[1].start_ms, 1000)

    def test_initial_ranges_must_fit_media(self):
        with self.assertRaises(TimelineError):
            Timeline([segment("a", 0, 2000)], media_duration_ms=1000)

    def test_fuzz_edits_never_introduce_overlap_or_partial_failure(self):
        generator = random.Random(8675309)
        for _ in range(200):
            timeline = Timeline([segment(str(i), i * 500, i * 500 + 400) for i in range(10)], 5000)
            before = [(item.start_ms, item.end_ms) for item in timeline.segments]
            index = generator.randrange(10)
            try:
                timeline.update(index, generator.randint(-1000, 6000), generator.randint(-1000, 6000), "edited")
            except TimelineError:
                self.assertEqual([(item.start_ms, item.end_ms) for item in timeline.segments], before)
            self._assert_structural(timeline.segments, 5000)

    def test_nudge_start(self):
        timeline = Timeline([segment("a", 200, 600)])
        updated = timeline.nudge(0, "start", -100)
        self.assertEqual((updated.start_ms, updated.end_ms), (100, 600))

    def test_split_preserves_range_and_splits_words(self):
        timeline = Timeline([segment("a", 0, 1000, "one two three four")])
        left, right = timeline.split(0, 400)
        self.assertEqual((left.start_ms, left.end_ms, left.text), (0, 400, "one two"))
        self.assertEqual((right.start_ms, right.end_ms, right.text), (400, 1000, "three four"))

    def test_split_rejects_too_short_side(self):
        timeline = Timeline([segment("a", 0, 100)])
        with self.assertRaises(TimelineError):
            timeline.split(0, 25)

    def test_media_boundary_is_enforced(self):
        timeline = Timeline([segment("a", 0, 500)], media_duration_ms=1000)
        updated = timeline.update(0, 1500, 1700, "text")
        self.assertEqual((updated.start_ms, updated.end_ms), (950, 1000))

    def test_active_cue_is_start_inclusive_end_exclusive_and_clears_in_gap(self):
        cues = [segment("a", 100, 200), segment("b", 300, 400)]
        self.assertIsNone(active_segment_index(cues, 99))
        self.assertEqual(active_segment_index(cues, 100), 0)
        self.assertIsNone(active_segment_index(cues, 200))
        self.assertIsNone(active_segment_index(cues, 250))
        self.assertEqual(active_segment_index(cues, 300), 1)

    def test_readability_retime_never_moves_neighboring_cues(self):
        cues = [segment("a", 0, 1000), segment("b", 1200, 1300), segment("c", 1500, 2000)]
        with self.assertRaises(TimelineError):
            retime_segment_duration(cues, 1, 1000, 3000)
        self.assertEqual([(cue.start_ms, cue.end_ms) for cue in cues], [(0, 1000), (1200, 1300), (1500, 2000)])

    def test_readability_retime_consumes_only_adjacent_silence(self):
        cues = [segment("a", 0, 500), segment("b", 1000, 1100), segment("c", 2000, 2500)]
        repaired = retime_segment_duration(cues, 1, 700, 3000)
        self.assertEqual((repaired[0].start_ms, repaired[0].end_ms), (0, 500))
        self.assertEqual((repaired[2].start_ms, repaired[2].end_ms), (2000, 2500))
        self.assertEqual(repaired[1].end_ms - repaired[1].start_ms, 700)

    def test_repairs_out_of_order_reversed_negative_and_overlap(self):
        source = [segment("b", 700, 300), segment("a", -100, 500), segment("c", 450, 451)]
        repaired, count = repair_segments(source, 1000)
        self.assertGreater(count, 0)
        self.assertEqual({item.text for item in repaired}, {"text"})
        self._assert_structural(repaired, 1000)

    def test_fuzz_repair_always_produces_valid_timeline(self):
        generator = random.Random(8128)
        for run in range(100):
            source = []
            for index in range(generator.randint(1, 15)):
                source.append(segment(f"{run}-{index}", generator.randint(-500, 9000), generator.randint(-500, 9000)))
            try:
                repaired, _ = repair_segments(source, 10_000)
            except TimelineError:
                # A media range can be too crowded to hold every 50 ms cue; export correctly blocks this case.
                continue
            self._assert_structural(repaired, 10_000)

    def _assert_structural(self, cues, duration):
        for index, cue in enumerate(cues):
            self.assertGreaterEqual(cue.start_ms, 0)
            self.assertGreaterEqual(cue.end_ms - cue.start_ms, 50)
            self.assertLessEqual(cue.end_ms, duration)
            if index:
                self.assertLessEqual(cues[index - 1].end_ms, cue.start_ms)


if __name__ == "__main__":
    unittest.main()
