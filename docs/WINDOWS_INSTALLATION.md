# Install SubsLab on Windows

These instructions are for Windows 10/11 on a 64-bit Intel or AMD PC. You do not need Python, Git, a GPU, or any programming tools.

## Download and install

1. Open the [latest SubsLab release](https://github.com/amits0410/SubsLab/releases/latest).
2. Under **Assets**, download **SubsLab-Setup.exe**. The automatically listed **Source code** ZIP and TAR files are for developers, not installation.
3. Open the downloaded installer and follow the setup wizard. It installs for your Windows account and adds SubsLab to the Start menu.
4. Launch **SubsLab** from the Start menu or the final setup screen.

The current installer is not code-signed. Windows may show an unknown-publisher or SmartScreen warning. Check that you downloaded the expected installer from this repository; only proceed if you trust its source. Signing is separate from the application's automated build and installation tests.

## Download your AI model once

1. In SubsLab, open **Tools → Local AI models**.
2. Install the model for the language and task you want. Hebrew transcription uses **Ivrit-AI**; translation into English uses the general multilingual Whisper model.
3. Wait for the download and verification to finish. Keep enough free disk space for both the app and the models.

After a model is installed, transcription with that model works offline. Audio and video stay on your computer. A compatible NVIDIA setup is optional; CPU transcription is supported.

## Make your first subtitles

1. Choose **Open media** and select an audio or video file.
2. Expand **Generate subtitles**, select the spoken language and whether to transcribe or translate into English, then start generation.
3. Play the media, review the subtitle cards, and edit as needed.
4. Choose **Save** to export an SRT subtitle file.

## Update or uninstall

To update, close SubsLab, download the newer installer from Releases, and run it. Application settings and installed models are stored separately from the program.

To uninstall, use **Settings → Apps → Installed apps → SubsLab → Uninstall** on Windows 11, or **Settings → Apps → Apps & features** on Windows 10. Uninstalling the app does not remove your original media or exported subtitles. Downloaded models and settings can remain in your user application-data folder.

## Optional download verification

Each release includes **SHA256SUMS.txt**. In PowerShell, run `Get-FileHash .\SubsLab-Setup.exe -Algorithm SHA256` from the download folder and compare the hash with that file. This checks that the downloaded installer matches the published file; it is not a code signature.
