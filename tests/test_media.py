import numpy as np

from subsgen.media import denoise_audio


def test_fft_denoiser_is_deterministic_finite_and_preserves_length():
    generator = np.random.default_rng(42)
    samples = generator.normal(0, 0.03, 16_000).astype("float32")
    first = denoise_audio(samples)
    second = denoise_audio(samples)
    assert first.shape == samples.shape
    assert np.isfinite(first).all()
    assert np.array_equal(first, second)
    assert np.sqrt(np.mean(first ** 2)) < np.sqrt(np.mean(samples ** 2))


def test_fft_denoiser_honors_cancellation():
    samples = np.zeros(16_000, dtype="float32")
    try:
        denoise_audio(samples, lambda: True)
    except InterruptedError:
        pass
    else:
        raise AssertionError("Expected denoising cancellation")
