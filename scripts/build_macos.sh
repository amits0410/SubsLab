#!/usr/bin/env bash
set -euo pipefail

python -c 'import mlx_whisper, faster_whisper, ctranslate2; print("macOS AI runtimes detected")'
python -m PyInstaller --noconfirm --clean SubsGenStudio.spec

if [[ -n "${SUBSGEN_CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp --sign "$SUBSGEN_CODESIGN_IDENTITY" "dist/SubsGen Studio.app"
fi

hdiutil create -volname "SubsGen Studio" -srcfolder "dist/SubsGen Studio.app" -ov -format UDZO "dist/SubsGen-Studio.dmg"

if [[ -n "${SUBSGEN_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "dist/SubsGen-Studio.dmg" --keychain-profile "$SUBSGEN_NOTARY_PROFILE" --wait
  xcrun stapler staple "dist/SubsGen-Studio.dmg"
fi
