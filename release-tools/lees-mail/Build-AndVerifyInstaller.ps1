[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$SourceRoot,
    [Parameter(Mandatory)] [string]$MsixDirectory,
    [Parameter(Mandatory)] [string]$OutputDirectory,
    [Parameter(Mandatory)] [string]$InstallerDefinition,
    [Parameter(Mandatory)] [string]$InstallScript,
    [Parameter(Mandatory)] [string]$Version,
    [Parameter(Mandatory)] [string]$PackageVersion,
    [Parameter(Mandatory)] [string]$CertificateThumbprint
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedSourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$resolvedMsixDirectory = [IO.Path]::GetFullPath($MsixDirectory)
$resolvedOutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$resolvedDefinition = [IO.Path]::GetFullPath($InstallerDefinition)
$resolvedInstallScript = [IO.Path]::GetFullPath($InstallScript)
$packages = @(Get-ChildItem -LiteralPath $resolvedMsixDirectory -Recurse -File -Filter *.msix)
if ($packages.Count -ne 1) {
    throw "Expected exactly one MSIX, found $($packages.Count)"
}

$inputDirectory = Join-Path $resolvedSourceRoot "artifacts\installer-input"
New-Item -ItemType Directory -Force $inputDirectory, $resolvedOutputDirectory | Out-Null
Copy-Item -LiteralPath $packages[0].FullName -Destination (Join-Path $inputDirectory "LeesMail.msix") -Force
Export-Certificate -Cert "Cert:\CurrentUser\My\$CertificateThumbprint" `
    -FilePath (Join-Path $inputDirectory "LeesMail_CN-Lee.cer") -Force | Out-Null
Copy-Item -LiteralPath $resolvedInstallScript -Destination (Join-Path $inputDirectory "InstallLeesMail.ps1") -Force

$languageFile = Join-Path $inputDirectory "ChineseSimplified.isl"
$languageUrl = "https://raw.githubusercontent.com/jrsoftware/issrc/7fc483339b6f5b531eb4c0c504a8026877c9142f/Files/Languages/ChineseSimplified.isl"
Invoke-WebRequest -Uri $languageUrl -OutFile $languageFile
$languageHash = (Get-FileHash -LiteralPath $languageFile -Algorithm SHA256).Hash
if ($languageHash -ne "6753BE2C5E2740D859900FD902824DB2EC568DA5C5B52486524C9762D778B0B0") {
    throw "Inno Setup Chinese language file hash mismatch: $languageHash"
}

$compiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw "Inno Setup compiler is missing from the runner"
}
& $compiler "/DAppVersion=$Version" "/DSourcePath=$inputDirectory" "/DOutputPath=$resolvedOutputDirectory" $resolvedDefinition
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$setups = @(Get-ChildItem -LiteralPath $resolvedOutputDirectory -File -Filter *.exe)
if ($setups.Count -ne 1) {
    throw "Expected exactly one setup executable, found $($setups.Count)"
}
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -File |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (!$signTool) {
    throw "SignTool is missing from the runner"
}
& $signTool.FullName sign /fd SHA256 /sha1 $CertificateThumbprint /s My $setups[0].FullName
if ($LASTEXITCODE -ne 0) {
    throw "Setup signing failed with exit code $LASTEXITCODE"
}
$setupSignature = Get-AuthenticodeSignature -LiteralPath $setups[0].FullName
if (!$setupSignature.SignerCertificate -or $setupSignature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
    throw "Setup signer does not match the configured Lee's Mail certificate"
}

$logPath = Join-Path $env:RUNNER_TEMP "lees-mail-setup.log"
$process = Start-Process -FilePath $setups[0].FullName `
    -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$logPath" `
    -Wait -PassThru
if ($process.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $logPath) {
        Get-Content -LiteralPath $logPath -Tail 80
    }
    throw "Lee's Mail setup verification failed with exit code $($process.ExitCode)"
}
$installed = @(Get-AppxPackage -Name LeesMail | Where-Object { $_.Version -eq $PackageVersion })
if ($installed.Count -ne 1) {
    throw "Lee's Mail setup did not install package version $PackageVersion"
}
$installed | Remove-AppxPackage
if (Get-AppxPackage -Name LeesMail) {
    throw "Lee's Mail setup verification package cleanup failed"
}

Get-Item -LiteralPath $setups[0].FullName
