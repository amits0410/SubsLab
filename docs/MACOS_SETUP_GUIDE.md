# SubsLab for macOS

This guide covers building SubsLab on an Apple Silicon Mac, sending it to another Mac user, and installing it. The current macOS release supports Apple Silicon only (M1, M2, M3, M4, or newer), not Intel Macs.

## What you send

Send the finished file:

```text
dist/SubsLab.dmg
```

Do not send the Windows `.exe`, the `.venv` directory, the source directory, or a loose `.app` folder. A macOS application is a bundle containing many files; the DMG preserves it correctly during transfer.

There are two distribution choices:

- **Trusted testing:** Build an unsigned DMG and send it to someone who knows and trusts you. macOS will show an unidentified-developer warning, which the recipient must explicitly override.
- **Normal distribution:** Sign with an Apple Developer ID and notarize the DMG. This is strongly recommended for nontechnical users or wider distribution.

Apple explains Developer ID distribution and notarization at [Distributing software on macOS](https://developer.apple.com/macos/distribution/) and [Signing Mac software with Developer ID](https://developer.apple.com/developer-id/).

## Requirements for the build Mac

- An Apple Silicon Mac running macOS 12 or later.
- Python 3.11, 3.12, or 3.13. Python 3.12 is recommended.
- Xcode Command Line Tools.
- Approximately 8 GB of free working space for Python packages and build output.
- Internet access while installing build dependencies.
- For signed distribution: membership in the Apple Developer Program and a **Developer ID Application** certificate.

The Mac user running the finished app does not need Python, Xcode, Homebrew, or the source code.

## Build the app on a Mac

You cannot build the macOS app from the existing Windows computer. Copy or clone the project onto the Apple Silicon Mac, open Terminal, and run the following commands from the project directory.

### 1. Install the command-line tools

```bash
xcode-select --install
```

If they are already installed, macOS will say so.

### 2. Check Python and the processor

```bash
uname -m
python3 --version
```

`uname -m` must print `arm64`. Python must be between 3.11 and 3.13. If necessary, install Python 3.12 from [python.org](https://www.python.org/downloads/macos/) or with Homebrew.

### 3. Create the build environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[mac-ai,test,build]'
```

Keep the virtual environment active for the remaining build commands.

### 4. Run the tests

```bash
PYTHONPATH=src python -m pytest
```

Do not distribute a build if the tests fail.

### 5A. Create an unsigned testing DMG

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

The result is `dist/SubsLab.dmg`. Use this route only for a trusted tester who is expecting the file.

### 5B. Create a signed and notarized DMG

Install a **Developer ID Application** certificate through Xcode or the Apple Developer portal, then list the available signing identities:

```bash
security find-identity -v -p codesigning
```

Store notarization credentials in the macOS Keychain. Replace the example values with the Apple Account and Team ID belonging to the developer account. The command securely prompts for an app-specific password.

```bash
xcrun notarytool store-credentials "subsgen-notary" \
  --apple-id "developer@example.com" \
  --team-id "ABCDE12345"
```

Set the two values consumed by the existing build script and build:

```bash
export SUBSLAB_CODESIGN_IDENTITY="Developer ID Application: Your Name (ABCDE12345)"
export SUBSLAB_NOTARY_PROFILE="subsgen-notary"
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

The script signs the app with the hardened runtime, creates the DMG, submits it through `notarytool`, waits for Apple, and staples the successful notarization ticket to the DMG.

### 6. Verify the release

```bash
codesign --verify --deep --strict --verbose=2 "dist/SubsLab.app"
xcrun stapler validate "dist/SubsLab.dmg"
spctl --assess --type execute --verbose=4 "dist/SubsLab.app"
shasum -a 256 "dist/SubsLab.dmg"
```

For an unsigned testing build, `codesign`, `stapler`, and `spctl` are expected to report that trusted signing or notarization is absent. The SHA-256 command works for both release types; save its output and send the hash to the recipient.

Test the DMG on a different Apple Silicon Mac or a clean macOS user account before distributing it.

## How to send the app

1. Rename the DMG with a version number, for example `SubsLab-0.2.0-arm64.dmg`.
2. Calculate its SHA-256 value with `shasum -a 256`.
3. Upload the DMG to a normal file-transfer service such as iCloud Drive, OneDrive, Google Drive, Dropbox, or a private download page. AirDrop or a USB drive also works.
4. Send the download link and the expected SHA-256 value to the recipient. Preferably send the hash through a separate message.
5. Tell the recipient whether the build is signed/notarized or an unsigned trusted-test build.

Do not modify the DMG after calculating its hash. Renaming does not change the file's SHA-256 value, but update the filename shown beside the hash when sharing it.

For regular distribution, use a signed and notarized DMG. Apple’s Gatekeeper checks Developer ID signatures and notarization for applications downloaded outside the App Store. An unsigned build places the security decision on the recipient and is unsuitable for broad public distribution.

---

# Installation instructions for the recipient

The section below can be copied directly into a message to the Mac user.

## System requirements

- Apple Silicon Mac: M1, M2, M3, M4, or newer.
- macOS 12 or later.
- At least 4 GB of free space; more may be needed for multiple offline AI models.
- Internet access for the initial model installation. Once a model is installed, transcription with that model works offline.

Intel Macs are not supported by this version.

## Install SubsLab

1. Download `SubsLab.dmg`.
2. If the sender supplied a SHA-256 value, open Terminal and verify the download:

   ```bash
   shasum -a 256 ~/Downloads/SubsLab.dmg
   ```

   The displayed value must exactly match the value supplied by the sender.

3. Double-click the DMG to open it.
4. Drag **SubsLab** into the **Applications** folder in Finder.
5. Eject the SubsLab disk image.
6. Open **Applications**, then open **SubsLab**.

A signed and notarized build should show the normal first-launch confirmation. Confirm only if you expected the app and trust its sender.

## Opening an unsigned trusted-test build

Only follow these steps if you personally trust the sender and the SHA-256 value matches.

1. Try to open SubsLab once so macOS records the blocked launch.
2. Open **System Settings → Privacy & Security**.
3. Scroll to **Security** and select **Open Anyway** for SubsLab.
4. Confirm **Open** when macOS asks again.

Apple documents this controlled exception in [Safely open apps on your Mac](https://support.apple.com/102445). Do not disable Gatekeeper globally and do not use random Terminal commands to remove security attributes.

If macOS says the app “will damage your computer,” moves it to Trash, or says it was modified or damaged, stop and request a fresh signed/notarized copy from the sender.

## Install an offline transcription model

1. Open **Models** in SubsLab.
2. Install the model needed for the intended workflow.
3. Keep the app open until download and SHA-256 verification finish.

The general Apple Silicon model is approximately 1 GB. Hebrew transcription requires the Ivrit-AI model, approximately 1.7 GB. Model installation requires internet access; installed models remain on the Mac and work offline afterward.

## First transcription

1. Select **Open media** and choose an MP4, MOV, M4V, MP3, WAV, or M4A file.
2. Choose **Transcribe** or **Translate to English**.
3. Select the spoken language. Hebrew transcription is automatically routed to the Ivrit-AI model.
4. Select **Generate subtitles** and wait for processing to finish.
5. Review and edit the subtitle cards, then save the result as SRT.

Media remains in its original location. SubsLab does not upload the media or copy it into cloud storage.

## Updating or removing the app

To update, quit SubsLab, open the new DMG, and replace the existing application in **Applications**. Installed models and recovery data are stored separately in the current user’s Application Support data, so replacing the app normally leaves them intact.

To remove only the application, drag **SubsLab** from Applications to the Trash. Removing its downloaded models and settings is a separate manual cleanup step.

## Troubleshooting

- **The app has a crossed-out icon or says it is unsupported:** Confirm that `uname -m` prints `arm64`. Intel Macs are unsupported.
- **The app cannot be verified:** Ask the sender for a notarized build. Use **Open Anyway** only for a trusted testing build with a matching SHA-256 value.
- **A model will not install:** Check the internet connection and available disk space, then retry from **Models**. Partial downloads are resumable.
- **Transcription works only while online:** Confirm that the required model finished installation and verification. The media-processing stage itself is local.
- **A managed work Mac blocks the app:** The organization’s administrator may prohibit applications outside its approved software catalog. Contact its IT administrator; do not bypass the policy.
