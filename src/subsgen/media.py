from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AudioData:
    samples: object
    duration_ms: int


def decode_audio(path: Path, cancelled=lambda: False) -> AudioData:
    """Decode any PyAV-supported input into 16 kHz mono float32 samples."""
    try:
        import av
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("PyAV and NumPy are required for media decoding") from exc

    chunks = []
    with av.open(str(path)) as container:
        streams = [stream for stream in container.streams if stream.type == "audio"]
        if not streams:
            raise ValueError("The selected media file has no audio stream")
        stream = streams[0]
        resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=16_000)
        for frame in container.decode(stream):
            if cancelled():
                raise InterruptedError("Transcription cancelled")
            converted = resampler.resample(frame)
            for output in converted if isinstance(converted, list) else [converted]:
                if output is not None:
                    chunks.append(output.to_ndarray().reshape(-1).astype("float32", copy=False))
        flushed = resampler.resample(None)
        for output in flushed if isinstance(flushed, list) else [flushed]:
            if output is not None:
                chunks.append(output.to_ndarray().reshape(-1).astype("float32", copy=False))
    samples = np.concatenate(chunks) if chunks else np.empty(0, dtype="float32")
    if not samples.size:
        raise ValueError("The audio stream is empty")
    return AudioData(samples=samples, duration_ms=round(samples.size / 16_000 * 1000))


def decode_waveform(path: Path, maximum_points: int = 1600, cancelled=lambda: False) -> tuple[list[float], int]:
    """Stream media into a bounded peak overview without retaining decoded audio."""
    try:
        import av
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("PyAV and NumPy are required for waveform decoding") from exc

    peaks: list[float] = []
    total_samples = 0
    with av.open(str(path)) as container:
        streams = [stream for stream in container.streams if stream.type == "audio"]
        if not streams:
            raise ValueError("The selected media file has no audio stream")
        resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=16_000)

        def consume(output) -> None:
            nonlocal total_samples
            if output is None:
                return
            values = output.to_ndarray().reshape(-1).astype("float32", copy=False)
            total_samples += values.size
            peaks.append(float(np.max(np.abs(values))) if values.size else 0.0)

        for frame in container.decode(streams[0]):
            if cancelled():
                raise InterruptedError("Waveform loading cancelled")
            converted = resampler.resample(frame)
            for output in converted if isinstance(converted, list) else [converted]:
                consume(output)
        flushed = resampler.resample(None)
        for output in flushed if isinstance(flushed, list) else [flushed]:
            consume(output)
    if not total_samples:
        raise ValueError("The audio stream is empty")
    if len(peaks) > maximum_points:
        bucket = (len(peaks) + maximum_points - 1) // maximum_points
        peaks = [max(peaks[start:start + bucket]) for start in range(0, len(peaks), bucket)]
    return peaks, round(total_samples / 16_000 * 1000)


def denoise_audio(samples, cancelled=lambda: False):
    """Reduce steady broadband noise with deterministic FFT spectral subtraction."""
    import numpy as np

    source = np.asarray(samples, dtype="float32")
    if source.size < 1024:
        return source.copy()
    frame_size, hop = 1024, 256
    window = np.hanning(frame_size).astype("float32")
    frame_count = 1 + (source.size - 1) // hop
    padded_size = (frame_count - 1) * hop + frame_size
    padded = np.pad(source, (0, max(0, padded_size - source.size)))
    spectra = []
    for index in range(frame_count):
        if cancelled():
            raise InterruptedError("Audio denoising cancelled")
        start = index * hop
        spectra.append(np.fft.rfft(padded[start:start + frame_size] * window))
    matrix = np.asarray(spectra)
    magnitude = np.abs(matrix)
    noise = np.percentile(magnitude, 20, axis=0)
    cleaned_magnitude = np.maximum(magnitude - 1.35 * noise, magnitude * 0.08)
    cleaned = cleaned_magnitude * np.exp(1j * np.angle(matrix))
    output = np.zeros(padded_size, dtype="float32")
    normalization = np.zeros(padded_size, dtype="float32")
    for index, spectrum in enumerate(cleaned):
        start = index * hop
        frame = np.fft.irfft(spectrum, n=frame_size).astype("float32") * window
        output[start:start + frame_size] += frame
        normalization[start:start + frame_size] += window * window
    valid = normalization > 0.05
    output[valid] /= normalization[valid]
    output[~valid] = source[np.flatnonzero(~valid) % source.size]
    return np.clip(output[:source.size], -1.0, 1.0)
