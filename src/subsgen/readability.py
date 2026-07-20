from __future__ import annotations

from collections import defaultdict
import math

from .domain import IssueSeverity, SubtitleIssue, SubtitleLayoutSettings, SubtitleSegment


def analyze_readability(
    segments: list[SubtitleSegment], settings: SubtitleLayoutSettings
) -> dict[str, list[SubtitleIssue]]:
    issues: dict[str, list[SubtitleIssue]] = defaultdict(list)
    for segment in segments:
        duration_ms = max(1, segment.end_ms - segment.start_ms)
        duration_s = duration_ms / 1000
        display_text = segment.text.replace("\n", " ").strip()
        character_count = len(display_text)
        word_count = len(display_text.split())
        cps = character_count / duration_s
        wpm = word_count / duration_s * 60
        lines = segment.text.splitlines() or [""]

        if settings.warn_cps and cps > settings.max_cps:
            issues[segment.id].append(_issue(segment, "cps", f"{cps:.1f} CPS (max {settings.max_cps:g})", cps, settings.max_cps))
        if settings.warn_wpm and wpm > settings.max_wpm:
            issues[segment.id].append(_issue(segment, "wpm", f"{wpm:.0f} WPM (max {settings.max_wpm:g})", wpm, settings.max_wpm))
        if settings.warn_line_count and len(lines) > settings.max_lines:
            issues[segment.id].append(
                _issue(segment, "line_count", f"{len(lines)} lines (max {settings.max_lines})", len(lines), settings.max_lines)
            )
        if settings.warn_line_length:
            longest = max(map(len, lines), default=0)
            if longest > settings.max_chars_per_line:
                issues[segment.id].append(
                    _issue(
                        segment,
                        "line_length",
                        f"{longest} characters on one line (max {settings.max_chars_per_line})",
                        longest,
                        settings.max_chars_per_line,
                    )
                )
        if settings.warn_duration and duration_ms < settings.min_duration_ms:
            issues[segment.id].append(
                _issue(segment, "duration_short", f"{duration_s:.1f}s duration (min {settings.min_duration_ms / 1000:g}s)", duration_ms, settings.min_duration_ms)
            )
        required_for_speed = required_reading_duration_ms(segment, settings, include_minimum=False)
        if settings.warn_duration and duration_ms > settings.max_duration_ms and required_for_speed <= settings.max_duration_ms:
            issues[segment.id].append(
                _issue(segment, "duration_long", f"{duration_s:.1f}s duration (max {settings.max_duration_ms / 1000:g}s)", duration_ms, settings.max_duration_ms)
            )
    return dict(issues)


def required_reading_duration_ms(
    segment: SubtitleSegment, settings: SubtitleLayoutSettings, include_minimum: bool = True
) -> int:
    text = segment.text.replace("\n", " ").strip()
    target = settings.min_duration_ms if include_minimum and settings.warn_duration else 50
    if settings.warn_cps and settings.max_cps > 0:
        target = max(target, math.ceil(len(text) / settings.max_cps * 1000))
    if settings.warn_wpm and settings.max_wpm > 0:
        target = max(target, math.ceil(len(text.split()) / settings.max_wpm * 60_000))
    return max(50, target)


def structural_issues(segments: list[SubtitleSegment], media_duration_ms: int | None = None) -> list[SubtitleIssue]:
    issues: list[SubtitleIssue] = []
    previous: SubtitleSegment | None = None
    for segment in segments:
        if segment.start_ms < 0:
            issues.append(_error(segment, "negative", "Start time is negative"))
        if segment.end_ms <= segment.start_ms:
            issues.append(_error(segment, "reversed", "End time must be after start time"))
        if segment.end_ms - segment.start_ms < 50:
            issues.append(_error(segment, "too_short", "Cue must be at least 50 ms long"))
        if previous and segment.start_ms < previous.end_ms:
            issues.append(_error(segment, "overlap", "Cue overlaps the previous cue"))
        if media_duration_ms is not None and segment.end_ms > media_duration_ms:
            issues.append(_error(segment, "past_media", "Cue extends beyond the media duration"))
        previous = segment
    return issues


def _issue(segment, code, message, measured, limit):
    return SubtitleIssue(segment.id, code, message, IssueSeverity.WARNING, float(measured), float(limit))


def _error(segment, code, message):
    return SubtitleIssue(segment.id, code, message, IssueSeverity.ERROR)
