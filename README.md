# SubsLab

SubsLab is a privacy-first desktop subtitle editor and local transcription tool. Audio and video stay on the computer: after an AI model has been downloaded once, transcription, English translation, Hebrew processing, editing, playback, recovery, and SRT export work without a network connection.

The application icon is provided in PNG, Windows ICO, and macOS ICNS formats under `assets/`; both development launches and packaged builds use the same branding.

## Download and install

| Your computer | Download | Installation |
| --- | --- | --- |
| Windows 10/11, 64-bit Intel/AMD | [SubsLab-Setup.exe](https://github.com/amits0410/SubsLab/releases/latest/download/SubsLab-Setup.exe) | Run the installer, then open SubsLab from Start. |
| Apple Silicon Mac (M1 or newer), macOS 14+ | [SubsLab-macOS-AppleSilicon.dmg](https://github.com/amits0410/SubsLab/releases/latest/download/SubsLab-macOS-AppleSilicon.dmg) | Open the DMG, drag SubsLab to Applications, then launch it from Applications. |

Python, programming tools, and a GitHub account are not required to install these downloads. Intel Macs are not supported.

On first launch, open **Tools → Local AI models** and install the model you need. This one-time download requires internet; transcription with installed models works offline.

These builds are not signed with a Windows publisher certificate or Apple Developer ID. Windows may show an unknown-publisher warning; macOS may require first-launch approval. Only proceed if you expected the download and trust its source. The release includes separate Windows and macOS SHA-256 checksums.

See the [Windows installation guide](docs/WINDOWS_INSTALLATION.md) or [Mac installation guide](docs/MACOS_INSTALLATION.md) for the steps for your computer. **Code → Download ZIP** and the release's **Source code** downloads contain developer files, not an installer.

## Features

- Dark studio workspace with collapsible transcription setup, a full-width waveform, and clear selected/playing cues.
- Inline Hebrew/Arabic RTL editing, platform-aware shortcuts, and persistent workspace layout.

- Local Whisper transcription and speech-to-English translation.
- Mandatory Ivrit-AI routing for Hebrew transcription.
- Faster-Whisper CPU/CUDA inference on Windows and CPU fallback on macOS.
- MLX-Whisper acceleration for general models on Apple Silicon.
- MP4, MOV, M4V, MP3, WAV, and M4A decoding and playback.
- Segment playback, text editing, splitting, deletion, direct timestamps, and 100 ms nudging.
- Automatic 50 ms minimum durations, reversed-time repair, and overlap prevention.
- UTF-8 SRT import/export with automatic Hebrew bidirectional markers, plus VTT and ASS export.
- Background waveform loading with drag scrubbing and validated boundary dragging.
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
.venv\Scripts\subslab.exe
```

On an Apple Silicon Mac:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[mac-ai,test,build]'
.venv/bin/subslab
```

Open **Tools → Local AI models** and install the model required for the selected language and task. Model downloads are the only workflow that requires internet access. The former `subsgen-studio` launch command remains available as an alias.

Existing model downloads, settings, and recovery history are reused from the original application-data location. The internal `subsgen` module, storage identities, installer AppId, and macOS bundle ID remain stable for compatibility.

For Windows CUDA acceleration, a compatible NVIDIA driver plus the CUDA 12/cuDNN 9 runtime is required. If CUDA cannot initialize, the application reports the fallback and continues with int8 CPU inference. Hebrew on macOS uses the Ivrit-AI CTranslate2 model on CPU; general multilingual transcription uses MLX acceleration.

## Tests

Install the test extra and run the complete core and UI suite without downloading AI models:

```powershell
$env:PYTHONPATH="src"
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest
```

Real-model and hardware smoke tests are opt-in because model artifacts are large and CUDA/Apple hardware is platform-specific. `scripts/preview_ui.py` renders isolated UI previews for visual checks without using personal recovery data.

## Architecture

- `domain.py` defines the stable segment, request, model, progress, and backend contracts.
- `timeline.py` owns all timing invariants so the UI and imported data share one policy.
- `srt.py` keeps directional markers out of editable text and owns atomic SRT, VTT, and ASS serialization.
- `model_store.py` owns capability routing and atomic on-demand model installation.
- `backends.py`, `media.py`, and `worker.py` isolate optional native AI dependencies and run inference outside the UI process.
- `waveform.py` renders the seekable waveform and emits boundary edits through the shared timeline validator.
- `ui.py` coordinates editing, jobs, model management, save flows, and recovery; `workspace.py`, `ui_widgets.py`, `actions.py`, and `theme.py` own layout, reusable controls, shared actions, and visual styling.
- `branding.py` centralizes the public name/version and stable storage identities.

Application data follows the operating system's standard per-user application-data location. Model folders and the single recovery snapshot live there; media is referenced by path and never copied.

## Packaging

Build the Windows application directory with:

```powershell
.\scripts\build.ps1
```

The script intentionally fails unless the `windows-ai` extra is installed, preventing a release that opens but cannot transcribe. Pass `-Installer` when Inno Setup's `iscc` is available. Set `SUBSLAB_SIGN_CERT_SHA1` to sign the executable and installer with `signtool`.

Windows output is `dist/SubsLab/SubsLab.exe`; the optional installer is `dist/SubsLab-Setup.exe`. The **Release SubsLab for macOS** GitHub Actions workflow builds and verifies a drag-to-Applications DMG and publishes `SubsLab-macOS-AppleSilicon.dmg` alongside the Windows installer in the matching release. It can also be run manually from Actions. Historical builds are kept separately.

On Apple Silicon, run `scripts/build_macos.sh`. It likewise checks for both the MLX and CTranslate2 runtimes before creating an application bundle and DMG. Set `SUBSLAB_CODESIGN_IDENTITY` for Developer ID signing and `SUBSLAB_NOTARY_PROFILE` for notarization and stapling. Unsigned local development builds need neither variable.

See the complete [macOS build, distribution, and recipient setup guide](docs/MACOS_SETUP_GUIDE.md) before sending a DMG to another user.

Run `python scripts/package_source.py` to produce a small source ZIP with the build workflow, assets, and tests, excluding virtual environments, models, media, and local build output. See [SubsLab refresh notes and recommended next improvements](docs/SUBSLAB_REFRESH.md).

## Privacy boundary

The application has no telemetry, cloud transcription endpoint, login, or media-upload code. The Hugging Face client is imported only by the explicit model-install action. Runtime inference receives a local path and decoded local samples.
