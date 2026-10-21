# Install SubsLab on a Mac

This guide is for people installing the finished app. You do not need Python, Homebrew, Terminal commands, a GitHub account, or the project source code.

## Check your Mac

Choose **Apple menu → About This Mac**. You need:

- **Chip:** Apple M1 or newer. Intel Macs are not supported.
- **macOS:** 14 Sonoma or later. The bundled MLX runtime [requires macOS 14 or later](https://ml-explore.github.io/mlx/build/html/install.html).
- Free space for the application and your downloaded AI models; allow several GB.

## Download and install

1. Open the [latest SubsLab release](https://github.com/amits0410/SubsLab/releases/latest).
2. Under **Assets**, download **SubsLab-macOS-AppleSilicon.dmg**. The **Source code** ZIP and TAR files are for developers.
3. Open the DMG. Drag **SubsLab** onto the **Applications** shortcut in that window.
4. Wait for copying to finish, then eject the SubsLab disk image in Finder.
5. Open **Finder → Applications → SubsLab**. You can keep it in the Dock for easier access.

## First-launch approval

This release is not signed with Apple Developer ID or notarized by Apple. macOS may say the developer cannot be verified or Apple cannot check the app.

If you expected this download, trust its source, and are certain it has not been tampered with:

1. Try opening SubsLab once.
2. Open **System Settings → Privacy & Security**.
3. Under **Security**, click **Open Anyway** for SubsLab, then confirm **Open**.

See [Apple's explanation of first-launch approval](https://support.apple.com/102445). If macOS says the app is damaged or will damage your computer, stop and request a fresh copy. Do not disable Gatekeeper or remove security attributes through Terminal commands.

## Install a model and create subtitles

1. In SubsLab, open **Tools → Local AI models**.
2. Install the model for your language and task. **Ivrit-AI** is used for Hebrew transcription; the general multilingual model handles translation into English.
3. Wait for download and verification to finish. This one-time installation requires internet; installed models work offline.
4. Choose **Open media**, select an audio or video file, and open the **Generate subtitles** panel.
5. Choose the spoken language and transcription or translation mode, then generate subtitles.
6. Review the results and choose **Save** to export an SRT subtitle file.

Your media stays on your computer. General multilingual models use Apple Silicon acceleration; the Hebrew Ivrit-AI model runs on CPU and can take longer.

## Update or remove SubsLab

To update, quit SubsLab and install the newer DMG the same way, choosing **Replace** when Finder asks. Models, settings, and recovery data are stored separately from the app.

To remove the app, quit it and drag **SubsLab** from Applications to the Trash. Your original media and exported subtitles are not removed. Downloaded models and settings can remain in your user Application Support folder.

## Optional download verification

The release includes **SHA256SUMS-macOS.txt**. If you want to verify the download, run `shasum -a 256 ~/Downloads/SubsLab-macOS-AppleSilicon.dmg` and compare the hash with that file. This checks that the file matches the release; it does not replace Apple signing or notarization.

Developers who need to build or sign the app should use the separate [macOS build guide](MACOS_SETUP_GUIDE.md).
