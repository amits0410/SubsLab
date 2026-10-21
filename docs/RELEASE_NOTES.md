# SubsLab 0.2.0

SubsLab is an offline subtitle editor with local AI transcription, translation into English, and Hebrew transcription through Ivrit-AI.

## Choose your download

| Platform | Download under Assets |
| --- | --- |
| Windows 10/11, 64-bit Intel/AMD | **SubsLab-Setup.exe** |
| Apple Silicon Mac (M1 or newer), macOS 14 Sonoma or later | **SubsLab-macOS-AppleSilicon.dmg** |

No Python, programming tools, or GitHub account is needed. Intel Macs are not supported. The **Source code** downloads are for developers.

## Install on Windows

1. Download **SubsLab-Setup.exe** under **Assets** below.
2. Run the installer, then launch **SubsLab** from the Start menu.
3. Open **Tools → Local AI models** and download the model you need once.
4. Open an audio or video file and generate your subtitles. Installed models work offline.

Supports Windows 10/11 on 64-bit Intel/AMD PCs. Python and a GPU are not required. The **Source code** downloads are for developers; use **SubsLab-Setup.exe** to install the app.

The installer is currently unsigned, so Windows may show an unknown-publisher or SmartScreen warning. Only proceed with a file you expected from this repository. **SHA256SUMS.txt** provides the installer checksum.

## Install on Mac

1. Download and open **SubsLab-macOS-AppleSilicon.dmg** under **Assets** below.
2. Drag **SubsLab** onto **Applications** in the disk-image window.
3. Wait for copying to finish, eject the disk image, and open **Applications → SubsLab**.
4. Open **Tools → Local AI models**, install your model once, and then open your media to generate subtitles offline.

This Mac build is not signed with Apple Developer ID or notarized by Apple. If macOS cannot verify the developer, trusted recipients can approve the first launch through **System Settings → Privacy & Security → Open Anyway** after attempting to open the app. See [Apple's instructions](https://support.apple.com/102445). If macOS reports that the app is damaged or will damage your computer, stop and request a fresh copy.

The DMG includes an **Applications** shortcut and **READ-ME-FIRST.txt**. A separate **MACOS-INSTALLATION.txt** download provides the same instructions. **SHA256SUMS-macOS.txt** contains the DMG checksum.

## What's included

- SubsLab branding and a refreshed dark editing workspace.
- Local Whisper transcription, translation into English, and Ivrit-AI Hebrew transcription.
- Hebrew and Arabic right-to-left editing, subtitle preview, waveform seeking, and keyboard controls.
- Subtitle timing repair, readability warnings and fixes, text-safe reflow, and undo/redo.
- Model download progress, cancellable transcription, recovery snapshots, and subtitle export.

The Windows release build runs the complete test suite, checks packaged application startup, and verifies installation, installed application startup, and uninstallation before publication.

The Mac release build runs the complete test suite, verifies Apple Silicon architecture, mounts the DMG, checks its installation shortcut and instructions, copies the app into an isolated Applications directory, ejects the disk image, and checks that the installed copy starts. Interactive playback and transcription still require testing on a user's Mac.

[Windows installation guide](https://github.com/amits0410/SubsLab/blob/main/docs/WINDOWS_INSTALLATION.md) · [Mac installation guide](https://github.com/amits0410/SubsLab/blob/main/docs/MACOS_INSTALLATION.md)
