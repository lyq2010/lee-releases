[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$SourceRoot,
    [Parameter(Mandatory)] [string]$MsixDirectory,
    [Parameter(Mandatory)] [string]$InstallerDirectory,
    [Parameter(Mandatory)] [string]$StageDirectory,
    [Parameter(Mandatory)] [string]$NotesPath,
    [Parameter(Mandatory)] [string]$Version,
    [Parameter(Mandatory)] [string]$SourceTag,
    [Parameter(Mandatory)] [string]$PublicTag,
    [Parameter(Mandatory)] [string]$CertificateThumbprint,
    [Parameter(Mandatory)] [string]$Repository
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedSourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$resolvedStageDirectory = [IO.Path]::GetFullPath($StageDirectory)
$resolvedNotesPath = [IO.Path]::GetFullPath($NotesPath)
$packages = @(Get-ChildItem -LiteralPath ([IO.Path]::GetFullPath($MsixDirectory)) -Recurse -File -Filter *.msix)
if ($packages.Count -ne 1) {
    throw "Expected exactly one MSIX, found $($packages.Count)"
}
$signature = Get-AuthenticodeSignature -LiteralPath $packages[0].FullName
if (!$signature.SignerCertificate -or $signature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
    throw "MSIX signer does not match the configured Lee's Mail certificate"
}

$installers = @(Get-ChildItem -LiteralPath ([IO.Path]::GetFullPath($InstallerDirectory)) -File -Filter *.exe)
if ($installers.Count -ne 1) {
    throw "Expected exactly one setup executable, found $($installers.Count)"
}

New-Item -ItemType Directory -Force $resolvedStageDirectory | Out-Null
$msixName = "LeesMail_${Version}_x64.msix"
$packageName = "LeesMail_${Version}_x64-setup.exe"
$certificateName = "LeesMail_CN-Lee.cer"
$sourceName = "lees-mail_${Version}_source.zip"
$publishedPackagePath = Join-Path $resolvedStageDirectory $packageName
$publishedMsixPath = Join-Path $resolvedStageDirectory $msixName
Copy-Item -LiteralPath $installers[0].FullName -Destination $publishedPackagePath -Force
Copy-Item -LiteralPath $packages[0].FullName -Destination $publishedMsixPath -Force
Export-Certificate -Cert "Cert:\CurrentUser\My\$CertificateThumbprint" `
    -FilePath (Join-Path $resolvedStageDirectory $certificateName) -Force | Out-Null

& git -C $resolvedSourceRoot archive --format=zip --output (Join-Path $resolvedStageDirectory $sourceName) $SourceTag
if ($LASTEXITCODE -ne 0) {
    throw "Source archive creation failed"
}

$publishedPackage = Get-Item -LiteralPath $publishedPackagePath
$publishedMsix = Get-Item -LiteralPath $publishedMsixPath
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $publishedPackage.FullName).Hash
$msixHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $publishedMsix.FullName).Hash
$base = "https://github.com/$Repository/releases/download/$PublicTag"
$manifest = [ordered]@{
    version = $Version
    platform = "windows-x86_64"
    package = $packageName
    url = "$base/$packageName"
    sha256 = $hash
    size = $publishedPackage.Length
    certificateThumbprint = $CertificateThumbprint
    msixPackage = $msixName
    msixSha256 = $msixHash
    msixSize = $publishedMsix.Length
    sourceArchive = $sourceName
}
[IO.File]::WriteAllText(
    (Join-Path $resolvedStageDirectory "latest-lees-mail.json"),
    ($manifest | ConvertTo-Json -Depth 3) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)

$changelog = Get-Content -LiteralPath (Join-Path $resolvedSourceRoot "CHANGELOG.md") -Encoding UTF8
$heading = "## v$Version "
$start = -1
for ($index = 0; $index -lt $changelog.Count; $index++) {
    if ($changelog[$index].StartsWith($heading, [StringComparison]::Ordinal)) {
        $start = $index
        break
    }
}
if ($start -lt 0) {
    throw "CHANGELOG entry not found for v$Version"
}
$end = $changelog.Count
for ($index = $start + 1; $index -lt $changelog.Count; $index++) {
    if ($changelog[$index].StartsWith("## ", [StringComparison]::Ordinal)) {
        $end = $index
        break
    }
}
$changeLines = @($changelog | Select-Object -Skip ($start + 1) -First ($end - $start - 1))
$releaseChanges = ($changeLines -join [Environment]::NewLine).Trim()
if ([string]::IsNullOrWhiteSpace($releaseChanges)) {
    throw "CHANGELOG entry for v$Version has no release notes"
}

$notes = @"
# Lee's Mail $Version

Lee's Mail Windows x64 正式版。

## 安装渠道

- 普通用户下载本 Release 的签名安装程序即可安装或更新 Lee's Mail。
- Cloudflare 翻译访问密钥不包含在安装包、源码归档或 Release 资产中；仅授权用户可在应用的翻译设置中配置。

## 更新内容

$releaseChanges
## 安装与校验

- 运行已签名的安装程序即可安装证书和 MSIX 软件包。

- 安装程序 SHA-256: ``$hash``
- MSIX SHA-256: ``$msixHash``
- 签名证书: ``$CertificateThumbprint``
- 已附带对应的 GPL-3.0 源码归档。
"@
New-Item -ItemType Directory -Force (Split-Path $resolvedNotesPath -Parent) | Out-Null
[IO.File]::WriteAllText($resolvedNotesPath, $notes, [Text.UTF8Encoding]::new($false))

$manifest
