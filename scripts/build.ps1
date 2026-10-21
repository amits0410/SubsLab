param([switch]$Installer)

$ErrorActionPreference = "Stop"
python -c "import faster_whisper, ctranslate2; print('Windows AI runtime detected')"
if ($LASTEXITCODE -ne 0) { throw 'Windows AI dependencies are missing.' }
python -m PyInstaller --noconfirm --clean SubsLab.spec
if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }

$signCertificate = if ($env:SUBSLAB_SIGN_CERT_SHA1) { $env:SUBSLAB_SIGN_CERT_SHA1 } else { $env:SUBSGEN_SIGN_CERT_SHA1 }
if ($signCertificate) {
    & signtool sign /sha1 $signCertificate /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\SubsLab\SubsLab.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Executable signing failed.' }
}

if ($Installer) {
    $env:PYTHONPATH = 'src'
    $appVersion = python -c "from subsgen.branding import APP_VERSION; print(APP_VERSION)"
    & iscc "/DMyAppVersion=$appVersion" packaging\windows\installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    if ($signCertificate) {
        & signtool sign /sha1 $signCertificate /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\SubsLab-Setup.exe"
        if ($LASTEXITCODE -ne 0) { throw 'Installer signing failed.' }
    }
}
