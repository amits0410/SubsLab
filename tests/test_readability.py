from subsgen.domain import SubtitleLayoutSettings, SubtitleSegment
from subsgen.readability import analyze_readability


def _codes(segment, settings=SubtitleLayoutSettings()):
    return {issue.code for issue in analyze_readability([segment], settings).get(segment.id, [])}


def test_readability_thresholds_are_inclusive():
    settings = SubtitleLayoutSettings(max_cps=20, max_wpm=180, min_duration_ms=1000, max_duration_ms=7000)
    segment = SubtitleSegment("ok", 0, 1000, "12345678901234567890")
    assert "cps" not in _codes(segment, settings)
    assert "duration_short" not in _codes(segment, settings)


def test_all_warning_categories():
    settings = SubtitleLayoutSettings(max_chars_per_line=5, max_lines=2, max_cps=2, max_wpm=10)
    segment = SubtitleSegment("bad", 0, 500, "one two three\nfour five six\nseven")
    assert {"cps", "wpm", "line_length", "line_count", "duration_short"} <= _codes(segment, settings)


def test_warning_toggle_disables_category():
    settings = SubtitleLayoutSettings(warn_cps=False, warn_wpm=False, warn_line_length=False,
                                      warn_line_count=False, warn_duration=False)
    assert not _codes(SubtitleSegment("quiet", 0, 50, "x" * 100), settings)


def test_maximum_duration_warning_is_not_hidden_by_reading_speed_conflict():
    segment = SubtitleSegment("long", 0, 9000, "word " * 50)
    assert "duration_long" in _codes(segment)
