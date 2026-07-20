from __future__ import annotations

import multiprocessing as mp
import queue
import traceback
from dataclasses import asdict
from pathlib import Path

from .backends import FasterWhisperBackend, HebrewAutoDetected, MLXWhisperBackend
from .domain import BackendKind, ProgressEvent, TranscriptionRequest
from .model_store import ModelStore, route_request
from .reflow import fallback_words, reflow_subtitles


class TranscriptionJob:
    def __init__(self, process: mp.Process, messages, cancel_event):
        self.process = process
        self.messages = messages
        self.cancel_event = cancel_event

    def cancel(self) -> None:
        self.cancel_event.set()

    def terminate(self) -> None:
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)

    def poll(self) -> list[dict]:
        events = []
        while True:
            try:
                events.append(self.messages.get_nowait())
            except queue.Empty:
                return events

    @property
    def is_alive(self) -> bool:
        return self.process.is_alive()


def start_job(request: TranscriptionRequest, model_root: Path) -> TranscriptionJob:
    context = mp.get_context("spawn")
    messages = context.Queue()
    cancel_event = context.Event()
    process = context.Process(target=_worker_main, args=(request, model_root, messages, cancel_event), daemon=True)
    process.start()
    return TranscriptionJob(process, messages, cancel_event)


def _worker_main(request: TranscriptionRequest, model_root: Path, messages, cancel_event) -> None:
    try:
        manifest = route_request(request)
        model_path = ModelStore(model_root).path_for(manifest)
        if not ModelStore(model_root).is_installed(manifest):
            raise FileNotFoundError(f"Model is not installed: {manifest.display_name}")
        messages.put(
            {
                "type": "progress",
                "progress": 0.01,
                "message": f"Preparing {manifest.display_name} with {manifest.backend.value}…",
            }
        )
        backend = MLXWhisperBackend() if manifest.backend is BackendKind.MLX_WHISPER else FasterWhisperBackend()

        def report(event: ProgressEvent) -> None:
            messages.put({"type": "progress", "progress": event.progress, "message": event.message})

        try:
            result = backend.transcribe(request, model_path, report, cancel_event.is_set)
        except HebrewAutoDetected:
            request = TranscriptionRequest(
                media_path=request.media_path,
                mode=request.mode,
                language="he",
                layout_settings=request.layout_settings,
                glossary=request.glossary,
                denoise=request.denoise,
            )
            manifest = route_request(request)
            model_path = ModelStore(model_root).path_for(manifest)
            if not ModelStore(model_root).is_installed(manifest):
                messages.put(
                    {
                        "type": "model_required",
                        "model_id": manifest.id,
                        "message": (
                            "Hebrew was detected automatically. Hebrew transcription requires the "
                            f"{manifest.display_name}, which is not installed yet."
                        ),
                    }
                )
                return
            request.model_id = manifest.id
            request.backend = manifest.backend
            messages.put(
                {
                    "type": "model_switch",
                    "model_id": manifest.id,
                    "language": "he",
                    "message": f"Hebrew detected — switching to {manifest.display_name}…",
                }
            )
            backend = FasterWhisperBackend()
            result = backend.transcribe(request, model_path, report, cancel_event.is_set)
        if not result.segments and not result.words:
            raise RuntimeError("No speech was detected in the selected media")
        messages.put({"type": "progress", "progress": 0.99, "message": "Reflowing words into readable subtitle cues…"})
        words = result.words or fallback_words(result.segments)
        segments = reflow_subtitles(words, request.layout_settings)
        if cancel_event.is_set():
            messages.put({"type": "cancelled"})
        else:
            messages.put(
                {
                    "type": "result",
                    "segments": [segment.to_dict() for segment in segments],
                    "words": [word.to_dict() for word in words],
                    "layout_settings": request.layout_settings.to_dict(),
                    "detected_language": result.detected_language or request.language,
                }
            )
    except InterruptedError:
        messages.put({"type": "cancelled"})
    except Exception as exc:
        messages.put({"type": "error", "message": str(exc), "details": traceback.format_exc()})
