from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .domain import SubtitleDocument, SubtitleLayoutSettings, SubtitleSegment, TimedWord, TranscriptionMode


class RecoveryStore:
    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, document: SubtitleDocument, editor_state: dict | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "media_path": str(document.media_path) if document.media_path else None,
            "srt_path": str(document.srt_path) if document.srt_path else None,
            "language": document.language,
            "mode": TranscriptionMode(document.mode).value,
            "segments": [segment.to_dict() for segment in document.segments],
            "source_words": [word.to_dict() for word in document.source_words],
            "layout_settings": document.layout_settings.to_dict(),
            "glossary": list(document.glossary),
            "denoise": document.denoise,
            "editor_state": editor_state or {},
        }
        fd, temporary = tempfile.mkstemp(prefix="recovery-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self) -> SubtitleDocument:
        payload = self._load_payload()
        if payload.get("version") != 1:
            raise ValueError("Unsupported recovery snapshot")
        return SubtitleDocument(
            segments=[SubtitleSegment.from_dict(item) for item in payload.get("segments", [])],
            media_path=Path(payload["media_path"]) if payload.get("media_path") else None,
            srt_path=Path(payload["srt_path"]) if payload.get("srt_path") else None,
            language=payload.get("language"),
            mode=TranscriptionMode(payload.get("mode", "transcribe")),
            source_words=[TimedWord.from_dict(item) for item in payload.get("source_words", [])],
            layout_settings=SubtitleLayoutSettings.from_dict(payload.get("layout_settings")),
            glossary=tuple(str(item) for item in payload.get("glossary", [])),
            denoise=bool(payload.get("denoise", False)),
        )

    def load_editor_state(self) -> dict:
        payload = self._load_payload()
        value = payload.get("editor_state", {})
        return value if isinstance(value, dict) else {}

    def _load_payload(self) -> dict:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("Unsupported recovery snapshot")
        return payload

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
