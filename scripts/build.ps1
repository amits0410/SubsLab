param([switch]$Installer)

$ErrorActionPreference = "Stop"
python -c "import faster_whisper, ctranslate2; print('Windows AI runtime detected')"
python -m PyInstaller --noconfirm --clean SubsGenStudio.spec

if ($env:SUBSGEN_SIGN_CERT_SHA1) {
    & signtool sign /sha1 $env:SUBSGEN_SIGN_CERT_SHA1 /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\SubsGen Studio\SubsGen Studio.exe"
}

if ($Installer) {
    & iscc packaging\windows\installer.iss
    if ($env:SUBSGEN_SIGN_CERT_SHA1) {
        & signtool sign /sha1 $env:SUBSGEN_SIGN_CERT_SHA1 /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\SubsGen-Studio-Setup.exe"
    }
}
