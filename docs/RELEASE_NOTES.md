# SubsLab 0.2.0

SubsLab is an offline subtitle editor with local AI transcription, translation into English, and Hebrew transcription through Ivrit-AI.

## Install on Windows

1. Download **SubsLab-Setup.exe** under **Assets** below.
2. Run the installer, then launch **SubsLab** from the Start menu.
3. Open **Tools → Local AI models** and download the model you need once.
4. Open an audio or video file and generate your subtitles. Installed models work offline.

Supports Windows 10/11 on 64-bit Intel/AMD PCs. Python and a GPU are not required. The **Source code** downloads are for developers; use **SubsLab-Setup.exe** to install the app.

The installer is currently unsigned, so Windows may show an unknown-publisher or SmartScreen warning. Only proceed with a file you expected from this repository. **SHA256SUMS.txt** provides the installer checksum.

## What's included

- SubsLab branding and a refreshed dark editing workspace.
- Local Whisper transcription, translation into English, and Ivrit-AI Hebrew transcription.
- Hebrew and Arabic right-to-left editing, subtitle preview, waveform seeking, and keyboard controls.
- Subtitle timing repair, readability warnings and fixes, text-safe reflow, and undo/redo.
- Model download progress, cancellable transcription, recovery snapshots, and subtitle export.

The Windows release build runs the complete test suite, checks packaged application startup, and verifies installation, installed application startup, and uninstallation before publication.

[Full Windows installation guide](https://github.com/amits0410/SubsLab/blob/main/docs/WINDOWS_INSTALLATION.md)

Apple Silicon macOS builds are available separately through the macOS build workflow; this release's installer is for Windows.
