from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from .domain import SubtitleSegment

MIN_DURATION_MS = 50
NUDGE_MS = 100


class TimelineError(ValueError):
    pass


def repair_segments(
    segments: list[SubtitleSegment], media_duration_ms: int | None = None
) -> tuple[list[SubtitleSegment], int]:
    """Return a chronological, non-overlapping timeline and a repair count."""
    repaired = 0
    clean: list[SubtitleSegment] = []
    for source in segments:
        start, end = int(source.start_ms), int(source.end_ms)
        if start > end:
            start, end = end, start
            repaired += 1
        if start < 0:
            start = 0
            repaired += 1
        if media_duration_ms is not None:
            bounded_start = min(start, max(0, media_duration_ms - MIN_DURATION_MS))
            bounded_end = min(end, media_duration_ms)
            repaired += int((bounded_start, bounded_end) != (start, end))
            start, end = bounded_start, bounded_end
        if end - start < MIN_DURATION_MS:
            end = start + MIN_DURATION_MS
            if media_duration_ms is not None and end > media_duration_ms:
                end = media_duration_ms
                start = max(0, end - MIN_DURATION_MS)
            repaired += 1
        clean.append(SubtitleSegment(source.id, start, end, source.text))
    original_order = [item.id for item in clean]
    clean.sort(key=lambda item: (item.start_ms, item.end_ms))
    repaired += int(original_order != [item.id for item in clean])

    for index in range(1, len(clean)):
        previous, current = clean[index - 1], clean[index]
        if current.start_ms >= previous.end_ms:
            continue
        if current.start_ms - previous.start_ms >= MIN_DURATION_MS:
            previous.end_ms = current.start_ms
        else:
            current.start_ms = previous.end_ms
            if current.end_ms - current.start_ms < MIN_DURATION_MS:
                current.end_ms = current.start_ms + MIN_DURATION_MS
        if media_duration_ms is not None and current.end_ms > media_duration_ms:
            raise TimelineError("The media is too short to repair all subtitle ranges")
        repaired += 1
    Timeline(clean, media_duration_ms)
    return clean, repaired


def active_segment_index(segments: list[SubtitleSegment], position_ms: int) -> int | None:
    low, high = 0, len(segments)
    while low < high:
        middle = (low + high) // 2
        if segments[middle].start_ms <= position_ms:
            low = middle + 1
        else:
            high = middle
    index = low - 1
    return index if index >= 0 and segments[index].start_ms <= position_ms < segments[index].end_ms else None


def retime_segment_duration(
    segments: list[SubtitleSegment], index: int, target_duration_ms: int, media_duration_ms: int | None = None
) -> list[SubtitleSegment]:
    """Retime one cue verbatim without moving any neighboring speech cues."""
    if not 0 <= index < len(segments):
        raise IndexError(index)
    output = [replace(item) for item in segments]
    current = output[index]
    target = max(MIN_DURATION_MS, int(target_duration_ms))
    if target < current.end_ms - current.start_ms:
        current.end_ms = current.start_ms + target
        return Timeline(output, media_duration_ms).segments

    left_limit = output[index - 1].end_ms if index else 0
    right_limit = (
        output[index + 1].start_ms
        if index + 1 < len(output)
        else media_duration_ms if media_duration_ms is not None else max(current.end_ms, left_limit + target)
    )
    if target > right_limit - left_limit:
        raise TimelineError(
            "The cue has insufficient adjacent silence for the requested reading speed; "
            "neighboring synchronized subtitles were left unchanged"
        )

    extra = target - (current.end_ms - current.start_ms)
    desired_start = current.start_ms - extra // 2
    current.start_ms = max(left_limit, min(desired_start, right_limit - target))
    current.end_ms = current.start_ms + target
    return Timeline(output, media_duration_ms).segments


class Timeline:
    """Mutates a sorted subtitle list while preserving non-overlap invariants."""

    def __init__(self, segments: list[SubtitleSegment] | None = None, media_duration_ms: int | None = None):
        self.segments = list(segments or [])
        self.media_duration_ms = media_duration_ms
        self._validate_initial()

    def _validate_initial(self) -> None:
        self.segments.sort(key=lambda item: (item.start_ms, item.end_ms))
        previous_end = 0
        for segment in self.segments:
            if segment.start_ms < 0 or segment.end_ms - segment.start_ms < MIN_DURATION_MS:
                raise TimelineError("Subtitle ranges must be nonnegative and at least 50 ms long")
            if segment.start_ms < previous_end:
                raise TimelineError("Subtitle ranges may not overlap")
            previous_end = segment.end_ms

    def update(self, index: int, start_ms: int, end_ms: int, text: str) -> SubtitleSegment:
        if not 0 <= index < len(self.segments):
            raise IndexError(index)
        start, end = self._normalize_range(start_ms, end_ms)
        previous = self.segments[index - 1] if index else None
        following = self.segments[index + 1] if index + 1 < len(self.segments) else None

        if previous and start < previous.end_ms:
            if start - previous.start_ms >= MIN_DURATION_MS:
                previous.end_ms = start
            else:
                start = previous.start_ms + MIN_DURATION_MS
                end = max(end, start + MIN_DURATION_MS)

        if following and end > following.start_ms:
            if following.start_ms - start >= MIN_DURATION_MS:
                end = following.start_ms
            else:
                start = max(previous.end_ms if previous else 0, following.start_ms - MIN_DURATION_MS)
                end = following.start_ms

        start, end = self._fit_media(start, end)
        if end - start < MIN_DURATION_MS:
            raise TimelineError("There is not enough room between adjacent subtitles")
        updated = SubtitleSegment(self.segments[index].id, start, end, text)
        self.segments[index] = updated
        return updated

    def _normalize_range(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        start, end = max(0, int(start_ms)), max(0, int(end_ms))
        if start > end:
            start, end = end, start
        if end - start < MIN_DURATION_MS:
            end = start + MIN_DURATION_MS
        return self._fit_media(start, end)

    def _fit_media(self, start: int, end: int) -> tuple[int, int]:
        if self.media_duration_ms is None:
            return start, end
        duration = max(MIN_DURATION_MS, self.media_duration_ms)
        if start >= duration:
            start = duration - MIN_DURATION_MS
        end = min(end, duration)
        if end - start < MIN_DURATION_MS:
            start = max(0, end - MIN_DURATION_MS)
        return start, end

    def nudge(self, index: int, boundary: str, delta_ms: int) -> SubtitleSegment:
        current = self.segments[index]
        start = current.start_ms + delta_ms if boundary == "start" else current.start_ms
        end = current.end_ms + delta_ms if boundary == "end" else current.end_ms
        if boundary not in {"start", "end"}:
            raise ValueError("boundary must be 'start' or 'end'")
        return self.update(index, start, end, current.text)

    def split(self, index: int, at_ms: int) -> tuple[SubtitleSegment, SubtitleSegment]:
        current = self.segments[index]
        if not current.start_ms + MIN_DURATION_MS <= at_ms <= current.end_ms - MIN_DURATION_MS:
            raise TimelineError("Split point must leave at least 50 ms on each side")
        left_text, right_text = _split_text(current.text)
        left = replace(current, end_ms=at_ms, text=left_text)
        right = SubtitleSegment(str(uuid4()), at_ms, current.end_ms, right_text)
        self.segments[index : index + 1] = [left, right]
        return left, right

    def delete(self, index: int) -> SubtitleSegment:
        return self.segments.pop(index)


def _split_text(text: str) -> tuple[str, str]:
    words = text.strip().split()
    if len(words) < 2:
        return text.strip(), ""
    midpoint = (len(words) + 1) // 2
    return " ".join(words[:midpoint]), " ".join(words[midpoint:])
