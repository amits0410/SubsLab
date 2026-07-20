from __future__ import annotations

import math
import re
from uuid import uuid4

from .domain import SubtitleLayoutSettings, SubtitleSegment, TimedWord
from .timeline import repair_segments

SENTENCE_END = re.compile(r"[.!?…。！？…][\"'”’)]*$")
CLAUSE_END = re.compile(r"[,;:،؛—–-][\"'”’)]*$")


def fallback_words(segments: list[SubtitleSegment]) -> list[TimedWord]:
    output: list[TimedWord] = []
    for segment in segments:
        tokens = segment.text.replace("\n", " ").split()
        if not tokens:
            continue
        duration = max(len(tokens), segment.end_ms - segment.start_ms)
        weights = [max(1, len(token)) for token in tokens]
        total = sum(weights)
        cursor = segment.start_ms
        consumed = 0
        for index, (token, weight) in enumerate(zip(tokens, weights)):
            consumed += weight
            end = segment.end_ms if index == len(tokens) - 1 else segment.start_ms + round(duration * consumed / total)
            end = max(cursor + 1, min(segment.end_ms, end))
            output.append(TimedWord(token, cursor, end))
            cursor = end
    return output


def reflow_subtitles(
    words: list[TimedWord],
    settings: SubtitleLayoutSettings,
    media_duration_ms: int | None = None,
) -> list[SubtitleSegment]:
    clean = [TimedWord(word.text.strip(), max(0, word.start_ms), max(word.start_ms + 1, word.end_ms)) for word in words if word.text.strip()]
    clean.sort(key=lambda word: (word.start_ms, word.end_ms))
    if not clean:
        return []

    groups: list[list[TimedWord]] = []
    current: list[TimedWord] = []
    capacity = settings.max_chars_per_line * settings.max_lines
    for word in clean:
        if current:
            gap = word.start_ms - current[-1].end_ms
            proposed = _joined(current + [word])
            duration = word.end_ms - current[0].start_ms
            if (
                gap >= settings.pause_break_ms
                or len(proposed) > capacity
                or not _fits_line_limits(current + [word], settings)
                or duration > settings.max_duration_ms
            ):
                groups.append(current)
                current = []
        current.append(word)
        text_length = len(_joined(current))
        elapsed = current[-1].end_ms - current[0].start_ms
        if SENTENCE_END.search(word.text) and (text_length >= settings.max_chars_per_line // 2 or elapsed >= 1_500):
            groups.append(current)
            current = []
        elif CLAUSE_END.search(word.text) and (text_length >= int(capacity * 0.65) or elapsed >= 4_000):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    raw = [
        SubtitleSegment(str(uuid4()), group[0].start_ms, group[-1].end_ms, _balanced_lines(group, settings))
        for group in groups
    ]
    _extend_short_cues(raw, settings, media_duration_ms)
    repaired, _ = repair_segments(raw, media_duration_ms)
    return repaired


def fit_readability_durations(
    segments: list[SubtitleSegment],
    settings: SubtitleLayoutSettings,
    left_limit_ms: int = 0,
    right_limit_ms: int | None = None,
) -> list[SubtitleSegment]:
    """Extend cues into free space to resolve enabled duration/CPS/WPM warnings where possible."""
    if not segments:
        return []
    output = [SubtitleSegment(item.id, item.start_ms, item.end_ms, item.text) for item in segments]
    raw = [(item.start_ms, item.end_ms) for item in output]
    outer_right = right_limit_ms if right_limit_ms is not None else raw[-1][1]
    for index, cue in enumerate(output):
        cell_left = left_limit_ms if index == 0 else (raw[index - 1][1] + raw[index][0]) // 2
        cell_right = outer_right if index == len(output) - 1 else (raw[index][1] + raw[index + 1][0]) // 2
        flat_text = cue.text.replace("\n", " ").strip()
        words = len(flat_text.split())
        target = 50
        if settings.warn_duration:
            target = max(target, settings.min_duration_ms)
        if settings.warn_cps and settings.max_cps > 0:
            target = max(target, math.ceil(len(flat_text) / settings.max_cps * 1000))
        if settings.warn_wpm and settings.max_wpm > 0:
            target = max(target, math.ceil(words / settings.max_wpm * 60_000))
        if settings.warn_duration:
            target = min(target, settings.max_duration_ms)
        target = min(target, max(50, cell_right - cell_left))
        missing = max(0, target - (cue.end_ms - cue.start_ms))
        take_left = min(cue.start_ms - cell_left, (missing + 1) // 2)
        cue.start_ms -= take_left
        missing -= take_left
        take_right = min(cell_right - cue.end_ms, missing)
        cue.end_ms += take_right
        missing -= take_right
        cue.start_ms -= min(cue.start_ms - cell_left, missing)
    repaired, _ = repair_segments(output, right_limit_ms)
    return repaired


def _joined(words: list[TimedWord]) -> str:
    return " ".join(word.text for word in words).strip()


def _fits_line_limits(words: list[TimedWord], settings: SubtitleLayoutSettings) -> bool:
    lines = 1
    current_length = 0
    for word in words:
        length = len(word.text)
        if length > settings.max_chars_per_line:
            return len(words) == 1
        proposed = length if current_length == 0 else current_length + 1 + length
        if proposed <= settings.max_chars_per_line:
            current_length = proposed
        else:
            lines += 1
            current_length = length
    return lines <= settings.max_lines


def _balanced_lines(words: list[TimedWord], settings: SubtitleLayoutSettings) -> str:
    text = _joined(words)
    if settings.max_lines <= 1 or len(text) <= settings.max_chars_per_line:
        return text
    tokens = [word.text for word in words]
    maximum_lines = min(settings.max_lines, len(tokens))
    best: tuple[tuple[int, int, int, int, int], list[str]] | None = None

    def consider(lines: list[str]) -> None:
        nonlocal best
        lengths = [len(line) for line in lines]
        overflow = sum(max(0, length - settings.max_chars_per_line) for length in lengths)
        orphan = int(len(lines[-1].split()) == 1 and len(lines[-1]) < 8)
        imbalance = max(lengths) - min(lengths)
        score = (overflow, len(lines), orphan, max(lengths), imbalance)
        if best is None or score < best[0]:
            best = (score, lines)

    def partition(start: int, remaining: int, lines: list[str]) -> None:
        if remaining == 1:
            consider(lines + [" ".join(tokens[start:])])
            return
        last_split = len(tokens) - remaining + 1
        for split in range(start + 1, last_split + 1):
            partition(split, remaining - 1, lines + [" ".join(tokens[start:split])])

    for line_count in range(2, maximum_lines + 1):
        partition(0, line_count, [])
    return "\n".join(best[1]) if best else text


def _extend_short_cues(segments, settings, media_duration_ms):
    raw_ranges = [(segment.start_ms, segment.end_ms) for segment in segments]
    for index, segment in enumerate(segments):
        left_limit = 0 if index == 0 else (raw_ranges[index - 1][1] + raw_ranges[index][0]) // 2
        right_limit = (
            media_duration_ms
            if index == len(segments) - 1 and media_duration_ms is not None
            else raw_ranges[index][1] if index == len(segments) - 1
            else (raw_ranges[index][1] + raw_ranges[index + 1][0]) // 2
        )
        segment.start_ms = max(left_limit, segment.start_ms - 50)
        segment.end_ms = min(right_limit, segment.end_ms + 100)
        missing = settings.min_duration_ms - (segment.end_ms - segment.start_ms)
        if missing > 0:
            take_left = min(segment.start_ms - left_limit, (missing + 1) // 2)
            segment.start_ms -= take_left
            missing -= take_left
            take_right = min(right_limit - segment.end_ms, missing)
            segment.end_ms += take_right
            missing -= take_right
            segment.start_ms -= min(segment.start_ms - left_limit, missing)
