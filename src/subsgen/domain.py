from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol


class TranscriptionMode(str, Enum):
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"


class BackendKind(str, Enum):
    FASTER_WHISPER = "faster-whisper"
    MLX_WHISPER = "mlx-whisper"


@dataclass(slots=True)
class SubtitleSegment:
    id: str
    start_ms: int
    end_ms: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "SubtitleSegment":
        return cls(
            id=str(value["id"]),
            start_ms=int(value["start_ms"]),
            end_ms=int(value["end_ms"]),
            text=str(value.get("text", "")),
        )


@dataclass(slots=True)
class TimedWord:
    text: str
    start_ms: int
    end_ms: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "TimedWord":
        return cls(str(value.get("text", "")), int(value["start_ms"]), int(value["end_ms"]))


@dataclass(slots=True)
class SubtitleLayoutSettings:
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_cps: float = 20.0
    max_wpm: float = 180.0
    min_duration_ms: int = 1_000
    max_duration_ms: int = 7_000
    pause_break_ms: int = 500
    warn_cps: bool = True
    warn_wpm: bool = True
    warn_line_length: bool = True
    warn_line_count: bool = True
    warn_duration: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict | None) -> "SubtitleLayoutSettings":
        if not value:
            return cls()
        defaults = cls()
        return cls(**{name: value.get(name, getattr(defaults, name)) for name in defaults.__dataclass_fields__})


class IssueSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SubtitleIssue:
    segment_id: str
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.WARNING
    measured: float | None = None
    limit: float | None = None


@dataclass(slots=True)
class TranscriptionResult:
    segments: list[SubtitleSegment]
    words: list[TimedWord] = field(default_factory=list)
    detected_language: str | None = None


@dataclass(slots=True)
class TranscriptionRequest:
    media_path: Path
    mode: TranscriptionMode | str
    language: str | None
    model_id: str | None = None
    backend: BackendKind | str | None = None
    layout_settings: SubtitleLayoutSettings = field(default_factory=SubtitleLayoutSettings)
    glossary: tuple[str, ...] = ()
    denoise: bool = False

    def __post_init__(self) -> None:
        self.media_path = Path(self.media_path)
        self.mode = TranscriptionMode(self.mode)
        if self.backend is not None:
            self.backend = BackendKind(self.backend)
        if self.language:
            self.language = self.language.lower()
        if isinstance(self.layout_settings, dict):
            self.layout_settings = SubtitleLayoutSettings.from_dict(self.layout_settings)
        if isinstance(self.glossary, str):
            self.glossary = tuple(item.strip() for item in self.glossary.replace("\n", ",").split(",") if item.strip())
        else:
            self.glossary = tuple(str(item).strip() for item in self.glossary if str(item).strip())

    @property
    def task(self) -> str:
        """Return the inference task safely even after loose GUI/IPC serialization."""
        return TranscriptionMode(self.mode).value


@dataclass(frozen=True, slots=True)
class ModelManifest:
    id: str
    display_name: str
    repository: str
    backend: BackendKind
    languages: tuple[str, ...]
    tasks: tuple[TranscriptionMode, ...]
    approximate_size: int
    platforms: tuple[str, ...]
    hardware: tuple[str, ...]
    revision: str = "main"
    checksum: str | None = None
    required_files: tuple[str, ...] = ("config.json",)

    def supports(self, mode: TranscriptionMode, language: str | None) -> bool:
        language_ok = "*" in self.languages or language is None or language in self.languages
        return mode in self.tasks and language_ok


@dataclass(slots=True)
class ProgressEvent:
    progress: float | None
    message: str


ProgressCallback = Callable[[ProgressEvent], None]
CancelCheck = Callable[[], bool]


class ASRBackend(Protocol):
    def transcribe(
        self,
        request: TranscriptionRequest,
        model_path: Path,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> TranscriptionResult: ...


@dataclass(slots=True)
class SubtitleDocument:
    segments: list[SubtitleSegment] = field(default_factory=list)
    media_path: Path | None = None
    srt_path: Path | None = None
    language: str | None = None
    mode: TranscriptionMode = TranscriptionMode.TRANSCRIBE
    source_words: list[TimedWord] = field(default_factory=list)
    layout_settings: SubtitleLayoutSettings = field(default_factory=SubtitleLayoutSettings)
    glossary: tuple[str, ...] = ()
    denoise: bool = False
