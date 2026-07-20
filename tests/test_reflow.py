from subsgen.domain import SubtitleLayoutSettings, SubtitleSegment, TimedWord
from subsgen.reflow import fallback_words, reflow_subtitles


def _words(text, start=0, step=250):
    return [TimedWord(token, start + index * step, start + (index + 1) * step)
            for index, token in enumerate(text.split())]


def test_reflow_preserves_every_word_exactly_once_and_is_structural():
    source = _words("This is a naturally flowing sentence with enough words to create more than one readable movie caption.")
    cues = reflow_subtitles(source, SubtitleLayoutSettings(max_chars_per_line=24))
    assert " ".join(cue.text.replace("\n", " ") for cue in cues).split() == [word.text for word in source]
    assert all(cue.end_ms - cue.start_ms >= 50 for cue in cues)
    assert all(left.end_ms <= right.start_ms for left, right in zip(cues, cues[1:]))


def test_reflow_prefers_silence_and_supports_hebrew():
    source = _words("שלום עולם זה משפט") + _words("אחרי הפסקה ארוכה", start=3000)
    cues = reflow_subtitles(source, SubtitleLayoutSettings(pause_break_ms=500))
    assert len(cues) >= 2
    assert cues[0].end_ms <= cues[1].start_ms


def test_missing_word_timing_fallback_is_deterministic():
    segments = [SubtitleSegment("a", 100, 1100, "one two three")]
    assert fallback_words(segments) == fallback_words(segments)
    assert [word.text for word in fallback_words(segments)] == ["one", "two", "three"]


def test_long_word_is_retained_even_when_limit_cannot_be_met():
    word = TimedWord("supercalifragilisticexpialidocious", 0, 100)
    cues = reflow_subtitles([word], SubtitleLayoutSettings(max_chars_per_line=10))
    assert cues[0].text == word.text


def test_reflow_honors_three_and_four_line_settings():
    source = _words("one two three four five six seven eight nine ten eleven twelve", step=300)
    for maximum_lines in (3, 4):
        settings = SubtitleLayoutSettings(max_chars_per_line=12, max_lines=maximum_lines, max_duration_ms=20_000)
        cues = reflow_subtitles(source, settings)
        assert all(len(cue.text.splitlines()) <= maximum_lines for cue in cues)
        assert all(len(line) <= 12 for cue in cues for line in cue.text.splitlines())
