#!/usr/bin/env bash
set -euo pipefail

python -c 'import mlx_whisper, faster_whisper, ctranslate2; print("macOS AI runtimes detected")'
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "SubsLab requires an Apple Silicon (arm64) build host." >&2
  exit 1
fi
python -m PyInstaller --noconfirm --clean SubsLab.spec
lipo "dist/SubsLab.app/Contents/MacOS/SubsLab" -verify_arch arm64
test -f "dist/SubsLab.app/Contents/Resources/assets/subslab.png"

sign_identity="${SUBSLAB_CODESIGN_IDENTITY:-${SUBSGEN_CODESIGN_IDENTITY:-}}"
notary_profile="${SUBSLAB_NOTARY_PROFILE:-${SUBSGEN_NOTARY_PROFILE:-}}"
if [[ -n "$sign_identity" ]]; then
  codesign --force --options runtime --timestamp --sign "$sign_identity" "dist/SubsLab.app"
  codesign --verify --deep --strict --verbose=2 "dist/SubsLab.app"
fi

dmg_temp_root="${TMPDIR:-/tmp}"
dmg_staging="$(mktemp -d "$dmg_temp_root/subslab-dmg.XXXXXX")"
cleanup_dmg_staging() {
  if [[ -n "$dmg_staging" && "$dmg_staging" == "$dmg_temp_root/subslab-dmg."* ]]; then
    rm -rf -- "$dmg_staging"
  fi
}
trap cleanup_dmg_staging EXIT
ditto "dist/SubsLab.app" "$dmg_staging/SubsLab.app"
ln -s /Applications "$dmg_staging/Applications"
cp docs/MACOS_INSTALLATION.txt "$dmg_staging/READ-ME-FIRST.txt"
hdiutil create -volname "SubsLab" -srcfolder "$dmg_staging" -ov -format UDZO "dist/SubsLab.dmg"
hdiutil verify "dist/SubsLab.dmg"
(cd dist && shasum -a 256 SubsLab.dmg > SHA256.txt)

if [[ -n "$notary_profile" ]]; then
  if [[ -z "$sign_identity" ]]; then
    echo "Notarization requires SUBSLAB_CODESIGN_IDENTITY." >&2
    exit 1
  fi
  xcrun notarytool submit "dist/SubsLab.dmg" --keychain-profile "$notary_profile" --wait
  xcrun stapler staple "dist/SubsLab.dmg"
  xcrun stapler validate "dist/SubsLab.dmg"
  (cd dist && shasum -a 256 SubsLab.dmg > SHA256.txt)
fi
