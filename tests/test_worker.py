import queue
import unittest
from pathlib import Path
from unittest.mock import patch

from subsgen.domain import ProgressEvent, SubtitleSegment, TranscriptionMode, TranscriptionRequest, TranscriptionResult
from subsgen.backends import HebrewAutoDetected
from subsgen.model_store import get_manifest
from subsgen.worker import _worker_main


class Event:
    def __init__(self, value=False):
        self.value = value

    def is_set(self):
        return self.value


class FakeBackend:
    def transcribe(self, request, model_path, progress, cancelled):
        progress(ProgressEvent(0.5, "Halfway"))
        return TranscriptionResult([SubtitleSegment("result", 0, 1000, "Offline result")])


class WorkerTests(unittest.TestCase):
    def test_worker_normalizes_progress_and_result_messages(self):
        messages = queue.Queue()
        request = TranscriptionRequest(Path("media.wav"), TranscriptionMode.TRANSCRIBE, "en")
        manifest = get_manifest("whisper-small-ct2")
        with (
            patch("subsgen.worker.route_request", return_value=manifest),
            patch("subsgen.worker.ModelStore.is_installed", return_value=True),
            patch("subsgen.worker.FasterWhisperBackend", return_value=FakeBackend()),
        ):
            _worker_main(request, Path("models"), messages, Event())
        events = []
        while not messages.empty():
            events.append(messages.get_nowait())
        result = events[-1]
        self.assertIn("Preparing", events[0]["message"])
        self.assertTrue(any(event.get("message") == "Halfway" for event in events))
        self.assertTrue(any("Reflowing" in event.get("message", "") for event in events))
        self.assertEqual(result["type"], "result")
        self.assertEqual(result["segments"][0]["text"], "Offline result")

    def test_worker_reports_preexisting_cancellation(self):
        messages = queue.Queue()
        request = TranscriptionRequest(Path("media.wav"), TranscriptionMode.TRANSCRIBE, "en")
        manifest = get_manifest("whisper-small-ct2")
        with (
            patch("subsgen.worker.route_request", return_value=manifest),
            patch("subsgen.worker.ModelStore.is_installed", return_value=True),
            patch("subsgen.worker.FasterWhisperBackend", return_value=FakeBackend()),
        ):
            _worker_main(request, Path("models"), messages, Event(True))
        event_types = []
        while not messages.empty():
            event_types.append(messages.get_nowait()["type"])
        self.assertEqual(event_types[-1], "cancelled")

    def test_worker_reports_clear_error_when_no_speech_is_detected(self):
        class EmptyBackend:
            def transcribe(self, *args):
                return TranscriptionResult([])

        messages = queue.Queue()
        request = TranscriptionRequest(Path("silence.wav"), TranscriptionMode.TRANSCRIBE, "en")
        manifest = get_manifest("whisper-small-ct2")
        with (
            patch("subsgen.worker.route_request", return_value=manifest),
            patch("subsgen.worker.ModelStore.is_installed", return_value=True),
            patch("subsgen.worker.FasterWhisperBackend", return_value=EmptyBackend()),
        ):
            _worker_main(request, Path("models"), messages, Event())
        events = []
        while not messages.empty():
            events.append(messages.get_nowait())
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("No speech", events[-1]["message"])

    def test_auto_detected_hebrew_switches_to_ivrit_model(self):
        class DetectBackend:
            def transcribe(self, *args):
                raise HebrewAutoDetected()

        class IvritBackend:
            def transcribe(self, request, model_path, progress, cancelled):
                self.request = request
                return TranscriptionResult([SubtitleSegment("he", 0, 1000, "שלום")], detected_language="he")

        messages = queue.Queue()
        generic = get_manifest("whisper-small-ct2")
        ivrit = get_manifest("ivrit-whisper-large-v3-turbo-ct2")
        ivrit_backend = IvritBackend()
        request = TranscriptionRequest(Path("media.wav"), TranscriptionMode.TRANSCRIBE, None, glossary="OpenAI, תל אביב")
        with (
            patch("subsgen.worker.route_request", side_effect=[generic, ivrit]),
            patch("subsgen.worker.ModelStore.is_installed", return_value=True),
            patch("subsgen.worker.FasterWhisperBackend", side_effect=[DetectBackend(), ivrit_backend]),
        ):
            _worker_main(request, Path("models"), messages, Event())
        events = []
        while not messages.empty():
            events.append(messages.get_nowait())
        switch = next(event for event in events if event["type"] == "model_switch")
        result = next(event for event in events if event["type"] == "result")
        self.assertEqual(switch["model_id"], ivrit.id)
        self.assertEqual(ivrit_backend.request.language, "he")
        self.assertEqual(ivrit_backend.request.model_id, ivrit.id)
        self.assertEqual(ivrit_backend.request.glossary, ("OpenAI", "תל אביב"))
        self.assertEqual(result["detected_language"], "he")

    def test_auto_detected_hebrew_requests_missing_ivrit_model(self):
        class DetectBackend:
            def transcribe(self, *args):
                raise HebrewAutoDetected()

        messages = queue.Queue()
        generic = get_manifest("whisper-small-ct2")
        ivrit = get_manifest("ivrit-whisper-large-v3-turbo-ct2")
        request = TranscriptionRequest(Path("media.wav"), TranscriptionMode.TRANSCRIBE, None)
        with (
            patch("subsgen.worker.route_request", side_effect=[generic, ivrit]),
            patch("subsgen.worker.ModelStore.is_installed", side_effect=[True, False]),
            patch("subsgen.worker.FasterWhisperBackend", return_value=DetectBackend()),
        ):
            _worker_main(request, Path("models"), messages, Event())
        events = []
        while not messages.empty():
            events.append(messages.get_nowait())
        required = next(event for event in events if event["type"] == "model_required")
        self.assertEqual(required["model_id"], ivrit.id)
        self.assertFalse(any(event["type"] == "result" for event in events))


if __name__ == "__main__":
    unittest.main()
