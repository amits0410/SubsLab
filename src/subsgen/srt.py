from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

from .domain import SubtitleSegment

RLE = "\u202b"
RLM = "\u200f"
PDF = "\u202c"
DIRECTIONAL_MARKS = str.maketrans("", "", "\u202a\u202b\u202c\u202d\u202e\u200e\u200f\u2066\u2067\u2068\u2069")
TIMESTAMP_RE = re.compile(
    r"^(?P<sh>\d{1,3}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,3}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})(?:\s+.*)?$"
)
HEBREW_RE = re.compile(r"[\u0590-\u05ff]")


class SrtError(ValueError):
    pass


def strip_directional_marks(text: str) -> str:
    return text.translate(DIRECTIONAL_MARKS)


def parse_srt(content: str) -> list[SubtitleSegment]:
    normalized = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    result: list[SubtitleSegment] = []
    for number, block in enumerate(re.split(r"\n\s*\n", normalized), start=1):
        lines = block.splitlines()
        if len(lines) < 2:
            raise SrtError(f"Block {number} is incomplete")
        timestamp_index = 1 if lines[0].strip().isdigit() else 0
        if timestamp_index >= len(lines):
            raise SrtError(f"Block {number} has no timestamp")
        match = TIMESTAMP_RE.match(lines[timestamp_index].strip())
        if not match:
            raise SrtError(f"Block {number} has an invalid timestamp")
        start = _parts_to_ms(match, "s")
        end = _parts_to_ms(match, "e")
        text = strip_directional_marks("\n".join(lines[timestamp_index + 1 :]))
        result.append(SubtitleSegment(str(uuid4()), start, end, text))
    result.sort(key=lambda item: (item.start_ms, item.end_ms))
    return result


def serialize_srt(segments: list[SubtitleSegment], repair_hebrew: bool = False) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = strip_directional_marks(segment.text)
        if repair_hebrew:
            text = "\n".join(_repair_rtl_line(line) for line in text.split("\n"))
        blocks.append(
            f"{index}\n{format_timestamp(segment.start_ms)} --> {format_timestamp(segment.end_ms)}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def load_srt(path: Path) -> list[SubtitleSegment]:
    return parse_srt(path.read_text(encoding="utf-8-sig"))


def save_srt(path: Path, segments: list[SubtitleSegment], repair_hebrew: bool = False) -> None:
    _atomic_write_text(path, serialize_srt(segments, repair_hebrew))


def serialize_vtt(segments: list[SubtitleSegment]) -> str:
    blocks = ["WEBVTT"]
    for segment in segments:
        start = format_timestamp(segment.start_ms).replace(",", ".")
        end = format_timestamp(segment.end_ms).replace(",", ".")
        blocks.append(f"{start} --> {end}\n{strip_directional_marks(segment.text)}")
    return "\n\n".join(blocks) + "\n"


def save_vtt(path: Path, segments: list[SubtitleSegment]) -> None:
    _atomic_write_text(path, serialize_vtt(segments))


def serialize_ass(segments: list[SubtitleSegment]) -> str:
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,24,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for segment in segments:
        text = strip_directional_marks(segment.text).replace("{", "\\{").replace("}", "\\}").replace("\n", r"\N")
        events.append(f"Dialogue: 0,{_format_ass_time(segment.start_ms)},{_format_ass_time(segment.end_ms)},Default,,0,0,0,,{text}")
    return header + "\n".join(events) + ("\n" if events else "")


def save_ass(path: Path, segments: list[SubtitleSegment]) -> None:
    _atomic_write_text(path, serialize_ass(segments))


def _format_ass_time(milliseconds: int) -> str:
    value = max(0, int(milliseconds))
    hours, value = divmod(value, 3_600_000)
    minutes, value = divmod(value, 60_000)
    seconds, millis = divmod(value, 1_000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis // 10:02d}"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def format_timestamp(milliseconds: int) -> str:
    value = max(0, int(milliseconds))
    hours, value = divmod(value, 3_600_000)
    minutes, value = divmod(value, 60_000)
    seconds, millis = divmod(value, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_timestamp(value: str) -> int:
    match = re.fullmatch(r"\s*(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})\s*", value)
    if not match:
        raise ValueError("Use HH:MM:SS,mmm")
    hours, minutes, seconds, millis = map(int, match.groups())
    if minutes > 59 or seconds > 59:
        raise ValueError("Minutes and seconds must be below 60")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def contains_hebrew(segments: list[SubtitleSegment]) -> bool:
    return any(HEBREW_RE.search(segment.text) for segment in segments)


def _parts_to_ms(match: re.Match[str], prefix: str) -> int:
    minutes = int(match[f"{prefix}m"])
    seconds = int(match[f"{prefix}s"])
    if minutes > 59 or seconds > 59:
        raise SrtError("Minutes and seconds in SRT timestamps must be below 60")
    return (
        (int(match[f"{prefix}h"]) * 60 + minutes) * 60
        + seconds
    ) * 1000 + int(match[f"{prefix}ms"])


def _repair_rtl_line(line: str) -> str:
    clean = strip_directional_marks(line)
    return f"{RLE}{RLM}{clean}{PDF}" if HEBREW_RE.search(clean) else clean
