from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .domain import ProgressEvent, SubtitleSegment, TimedWord, TranscriptionRequest, TranscriptionResult
from .media import decode_audio, denoise_audio
from .reflow import fallback_words


class HebrewAutoDetected(RuntimeError):
    """Signals that automatic detection must switch to the mandatory Ivrit model."""


class FasterWhisperBackend:
    def transcribe(self, request, model_path, progress, cancelled):
        try:
            import ctranslate2
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Install the Windows AI dependencies to use Faster-Whisper") from exc

        progress(ProgressEvent(0.02, "Decoding audio…"))
        audio = decode_audio(request.media_path, cancelled)
        progress(ProgressEvent(0.06, f"Audio decoded: {audio.duration_ms / 1000:.1f}s, mono 16 kHz…"))
        if request.denoise:
            progress(ProgressEvent(0.07, "Reducing steady background noise with local FFT processing…"))
            audio.samples = denoise_audio(audio.samples, cancelled)
        if cancelled():
            raise InterruptedError("Transcription cancelled")
        device, compute_type = "cpu", "int8"
        try:
            if ctranslate2.get_cuda_device_count() > 0:
                device, compute_type = "cuda", "float16"
        except Exception:
            pass
        progress(ProgressEvent(0.08, f"Loading {request.model_id or 'Whisper model'} on {device.upper()} ({compute_type})…"))
        try:
            model = WhisperModel(str(model_path), device=device, compute_type=compute_type)
        except Exception:
            if device != "cuda":
                raise
            device, compute_type = "cpu", "int8"
            progress(ProgressEvent(0.08, "CUDA initialization failed; loading CPU int8 fallback…"))
            model = WhisperModel(str(model_path), device=device, compute_type=compute_type)
        language = "he" if request.language == "he" else request.language
        segments, info = model.transcribe(
            audio.samples,
            language=language,
            task=request.task,
            vad_filter=True,
            beam_size=5,
            word_timestamps=True,
            initial_prompt=", ".join(request.glossary) or None,
        )
        detected_language = str(getattr(info, "language", "") or "").lower() or None
        if (
            request.language is None
            and request.mode.value == "transcribe"
            and detected_language == "he"
            and not str(request.model_id or "").startswith("ivrit-")
        ):
            raise HebrewAutoDetected("Hebrew detected during automatic language detection")
        output: list[SubtitleSegment] = []
        words: list[TimedWord] = []
        for segment in segments:
            if cancelled():
                raise InterruptedError("Transcription cancelled")
            start_ms, end_ms = round(segment.start * 1000), round(segment.end * 1000)
            if end_ms - start_ms < 50:
                end_ms = start_ms + 50
            output.append(SubtitleSegment(str(uuid4()), start_ms, end_ms, segment.text.strip()))
            raw_words = list(segment.words or [])
            timed: list[TimedWord] = []
            valid_timings = bool(raw_words)
            for word in raw_words:
                text = str(getattr(word, "word", "")).strip()
                word_start = getattr(word, "start", None)
                word_end = getattr(word, "end", None)
                if not text:
                    continue
                if word_start is None or word_end is None:
                    valid_timings = False
                    continue
                start = round(float(word_start) * 1000)
                timed.append(TimedWord(text, start, max(start + 1, round(float(word_end) * 1000))))
            if valid_timings and timed:
                words.extend(timed)
            else:
                fallback_text = " ".join(str(getattr(word, "word", "")).strip() for word in raw_words).strip()
                fallback_segment = SubtitleSegment(output[-1].id, start_ms, end_ms, fallback_text or output[-1].text)
                words.extend(fallback_words([fallback_segment]))
            fraction = end_ms / max(1, audio.duration_ms)
            progress(ProgressEvent(min(0.98, 0.1 + 0.88 * fraction), f"Transcribing on {device.upper()}…"))
        progress(ProgressEvent(0.985, "Word-level transcription complete…"))
        return TranscriptionResult(output, words, detected_language)


class MLXWhisperBackend:
    def transcribe(self, request, model_path, progress, cancelled):
        try:
            import mlx_whisper
        except ImportError as exc:
            raise RuntimeError("Install the macOS AI dependencies to use MLX-Whisper") from exc
        progress(ProgressEvent(0.02, "Decoding audio…"))
        audio = decode_audio(request.media_path, cancelled)
        progress(ProgressEvent(0.06, f"Audio decoded: {audio.duration_ms / 1000:.1f}s, mono 16 kHz…"))
        if request.denoise:
            progress(ProgressEvent(0.07, "Reducing steady background noise with local FFT processing…"))
            audio.samples = denoise_audio(audio.samples, cancelled)
        if cancelled():
            raise InterruptedError("Transcription cancelled")
        progress(ProgressEvent(0.08, f"Loading {request.model_id or 'Whisper model'} with MLX on Apple Silicon…"))
        result = mlx_whisper.transcribe(
            audio.samples,
            path_or_hf_repo=str(model_path),
            language=request.language,
            task=request.task,
            word_timestamps=True,
            initial_prompt=", ".join(request.glossary) or None,
        )
        if cancelled():
            raise InterruptedError("Transcription cancelled")
        detected_language = str(result.get("language", "") or "").lower() or None
        if request.language is None and request.mode.value == "transcribe" and detected_language == "he":
            raise HebrewAutoDetected("Hebrew detected during automatic language detection")
        output = []
        words: list[TimedWord] = []
        for segment in result.get("segments", []):
            start_ms, end_ms = round(float(segment["start"]) * 1000), round(float(segment["end"]) * 1000)
            output.append(
                SubtitleSegment(str(uuid4()), start_ms, max(start_ms + 50, end_ms), str(segment["text"]).strip())
            )
            raw_words = list(segment.get("words") or [])
            timed: list[TimedWord] = []
            valid_timings = bool(raw_words)
            for word in raw_words:
                text = str(word.get("word", word.get("text", ""))).strip()
                if not text:
                    continue
                if word.get("start") is None or word.get("end") is None:
                    valid_timings = False
                    continue
                word_start = round(float(word["start"]) * 1000)
                timed.append(TimedWord(text, word_start, max(word_start + 1, round(float(word["end"]) * 1000))))
            if valid_timings and timed:
                words.extend(timed)
            else:
                fallback_text = " ".join(
                    str(word.get("word", word.get("text", ""))).strip() for word in raw_words
                ).strip()
                fallback_segment = SubtitleSegment(output[-1].id, start_ms, end_ms, fallback_text or output[-1].text)
                words.extend(fallback_words([fallback_segment]))
        progress(ProgressEvent(0.985, "Word-level transcription complete with MLX…"))
        return TranscriptionResult(output, words, detected_language)
