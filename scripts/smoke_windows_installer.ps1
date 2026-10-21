param([Parameter(Mandatory = $true)][string]$InstallerPath)

$ErrorActionPreference = 'Stop'
$installerFile = (Resolve-Path -LiteralPath $InstallerPath).Path
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$testId = [Guid]::NewGuid().ToString('N')
$installDirectory = Join-Path $temporaryRoot "subslab-install-$testId"
$installLog = Join-Path $temporaryRoot "subslab-installer-$testId.log"
$uninstallLog = Join-Path $temporaryRoot "subslab-installer-$testId-uninstall.log"
$installedExecutable = Join-Path $installDirectory 'SubsLab.exe'
$uninstaller = Join-Path $installDirectory 'unins000.exe'

try {
    $installArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
        "/DIR=`"$installDirectory`"", "/LOG=`"$installLog`"")
    $installProcess = Start-Process -FilePath $installerFile -ArgumentList $installArguments -WindowStyle Hidden -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) { throw "Installer exited with code $($installProcess.ExitCode). See $installLog" }
    if (-not (Test-Path -LiteralPath $installedExecutable)) { throw 'Installer did not create SubsLab.exe.' }
    if (-not (Test-Path -LiteralPath $uninstaller)) { throw 'Installer did not create its uninstaller.' }

    python (Join-Path $PSScriptRoot 'smoke_app.py') $installedExecutable --seconds 8
    if ($LASTEXITCODE -ne 0) { throw 'Installed application failed its startup test.' }
    Write-Output 'Windows installer and installed application startup passed.'
}
finally {
    if (Test-Path -LiteralPath $uninstaller) {
        $uninstallArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$uninstallLog`"")
        $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList $uninstallArguments -WindowStyle Hidden -Wait -PassThru
        if ($uninstallProcess.ExitCode -ne 0) { throw "Uninstaller exited with code $($uninstallProcess.ExitCode). See $uninstallLog" }
        if (Test-Path -LiteralPath $installedExecutable) { throw 'Uninstaller left the application executable installed.' }
        Write-Output 'Windows uninstallation passed.'
    }
}
