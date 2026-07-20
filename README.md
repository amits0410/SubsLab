# SubsGen Studio

SubsGen Studio is a privacy-first desktop subtitle editor and local transcription tool. Audio and video stay on the computer: after an AI model has been downloaded once, transcription, English translation, Hebrew processing, editing, playback, recovery, and SRT export work without a network connection.

The application icon is provided in PNG, Windows ICO, and macOS ICNS formats under `assets/`; both development launches and packaged builds use the same branding.

## MVP features

- Local Whisper transcription and speech-to-English translation.
- Mandatory Ivrit-AI routing for Hebrew transcription.
- Faster-Whisper CPU/CUDA inference on Windows and CPU fallback on macOS.
- MLX-Whisper acceleration for general models on Apple Silicon.
- MP4, MOV, M4V, MP3, WAV, and M4A decoding and playback.
- Segment playback, text editing, splitting, deletion, direct timestamps, and 100 ms nudging.
- Automatic 50 ms minimum durations, reversed-time repair, and overlap prevention.
- UTF-8 SRT import/export with automatic Hebrew bidirectional markers, plus VTT and ASS export.
- Background waveform loading with click-to-seek and validated boundary dragging.
- Optional local FFT background-noise reduction and transcription glossary prompting.
- Find/replace, a quality report, playback speed, cue looping, and context playback.
- Atomic recovery snapshots with recent undo/redo history that never copy the user's media.
- Resumable model installation with pinned revisions, SHA-256 verification, and offline health checks.

Speaker diarization, imported-SRT machine translation, burned-in video export, batch queues, and automatic updates remain post-MVP systems.

## Development setup

Python 3.11–3.13 is supported. Create a virtual environment, then install the platform extra:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[windows-ai,test,build]"
.venv\Scripts\subsgen-studio.exe
```

On an Apple Silicon Mac:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[mac-ai,test,build]'
.venv/bin/subsgen-studio
```

Open **Models** in the application and install the model required for the selected language and task. Model downloads are the only workflow that requires internet access.

For Windows CUDA acceleration, a compatible NVIDIA driver plus the CUDA 12/cuDNN 9 runtime is required. If CUDA cannot initialize, the application reports the fallback and continues with int8 CPU inference. Hebrew on macOS uses the Ivrit-AI CTranslate2 model on CPU; general multilingual transcription uses MLX acceleration.

## Tests

The core tests use only the Python standard library and do not download AI models:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

With the test extra installed, `pytest` can run the same suite. Real-model and hardware smoke tests are intentionally opt-in because model artifacts are large and CUDA/Apple hardware is platform-specific.

## Architecture

- `domain.py` defines the stable segment, request, model, progress, and backend contracts.
- `timeline.py` owns all timing invariants so the UI and imported data share one policy.
- `srt.py` keeps directional markers out of editable text and owns atomic SRT, VTT, and ASS serialization.
- `model_store.py` owns capability routing and atomic on-demand model installation.
- `backends.py`, `media.py`, and `worker.py` isolate optional native AI dependencies and run inference outside the UI process.
- `waveform.py` renders the seekable waveform and emits boundary edits through the shared timeline validator.
- `ui.py` contains the PySide6 application shell, media player, subtitle cards, model manager, search/report tools, save flows, and recovery lifecycle.

Application data follows the operating system's standard per-user application-data location. Model folders and the single recovery snapshot live there; media is referenced by path and never copied.

## Packaging

Build the Windows application directory with:

```powershell
.\scripts\build.ps1
```

The script intentionally fails unless the `windows-ai` extra is installed, preventing a release that opens but cannot transcribe. Pass `-Installer` when Inno Setup's `iscc` is available. Set `SUBSGEN_SIGN_CERT_SHA1` to sign the executable and installer with `signtool`.

On Apple Silicon, run `scripts/build_macos.sh`. It likewise checks for both the MLX and CTranslate2 runtimes before creating an application bundle and DMG. Set `SUBSGEN_CODESIGN_IDENTITY` for Developer ID signing and `SUBSGEN_NOTARY_PROFILE` for notarization and stapling. Unsigned local development builds need neither variable.

See the complete [macOS build, distribution, and recipient setup guide](docs/MACOS_SETUP_GUIDE.md) before sending a DMG to another user.

## Privacy boundary

The application has no telemetry, cloud transcription endpoint, login, or media-upload code. The Hugging Face client is imported only by the explicit model-install action. Runtime inference receives a local path and decoded local samples.
