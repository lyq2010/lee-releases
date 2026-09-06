[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$SourceRoot,
    [Parameter(Mandatory)] [string]$PackageVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RequiredEnvironmentValue([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name is missing"
    }
    $value
}

$outlookClientId = Get-RequiredEnvironmentValue "OUTLOOK_CLIENT_ID"
$gmailClientId = Get-RequiredEnvironmentValue "GMAIL_CLIENT_ID"
$gmailClientSecret = Get-RequiredEnvironmentValue "GMAIL_CLIENT_SECRET"
$cosBase = (Get-RequiredEnvironmentValue "COS_PUBLIC_BASE_URL").TrimEnd("/")
$signingPfxBase64 = Get-RequiredEnvironmentValue "SIGNING_PFX_BASE64"
$signingPfxPassword = Get-RequiredEnvironmentValue "SIGNING_PFX_PASSWORD"
if ($outlookClientId -notmatch "^[0-9a-fA-F-]{36}$") {
    throw "OUTLOOK_CLIENT_ID is malformed"
}
if ($gmailClientId -notmatch "^[0-9]+-[a-zA-Z0-9_-]+\.apps\.googleusercontent\.com$") {
    throw "GMAIL_CLIENT_ID is malformed"
}
if (!$cosBase.Contains("://")) {
    $cosBase = "https://$cosBase"
}
$cosUri = $null
if (![Uri]::TryCreate($cosBase, [UriKind]::Absolute, [ref]$cosUri) -or $cosUri.Scheme -ne "https") {
    throw "COS_PUBLIC_BASE_URL is malformed"
}
if ([string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) {
    throw "GITHUB_OUTPUT is missing"
}

$pfxPath = Join-Path $env:RUNNER_TEMP "lees-mail-signing.pfx"
[IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($signingPfxBase64))
$securePassword = ConvertTo-SecureString $signingPfxPassword -AsPlainText -Force
$certificate = Import-PfxCertificate -FilePath $pfxPath -Password $securePassword `
    -CertStoreLocation Cert:\CurrentUser\My -Exportable
"thumbprint=$($certificate.Thumbprint)" >> $env:GITHUB_OUTPUT
if (!$certificate.HasPrivateKey) {
    throw "Imported Lee's Mail certificate has no private key"
}
if ($certificate.Subject -ne "CN=Lee") {
    throw "Unexpected certificate subject: $($certificate.Subject)"
}

$resolvedSourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$manifestPath = Join-Path $resolvedSourceRoot "LeesMail.Mail.WinUI\Package.appxmanifest"
[xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
$actualVersion = [string]$manifest.Package.Identity.Version
if ($actualVersion -ne $PackageVersion) {
    throw "Source package version mismatch: $actualVersion != $PackageVersion"
}
if ([Version]$actualVersion -ge [Version]"1.2.21.0") {
    $requiredSources = @(
        "LeesMail.LargeAttachments\LeesMail.LargeAttachments.csproj",
        "large-attachment-web\package.json",
        "tools\LeesMail.LargeAttachments.E2E\LeesMail.LargeAttachments.E2E.csproj"
    )
    foreach ($requiredSource in $requiredSources) {
        $requiredPath = Join-Path $resolvedSourceRoot $requiredSource
        if (!(Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Required large-attachment release source is missing: $requiredSource"
        }
    }
}

$escape = [System.Security.SecurityElement]
$cosManifest = "$cosBase/latest-lees-mail.json"
$content = @"
<Project>
  <PropertyGroup>
    <LeesMailOutlookClientId>$($escape::Escape($outlookClientId))</LeesMailOutlookClientId>
    <LeesMailGmailClientId>$($escape::Escape($gmailClientId))</LeesMailGmailClientId>
    <LeesMailGmailClientSecret>$($escape::Escape($gmailClientSecret))</LeesMailGmailClientSecret>
    <LeesMailCosUpdateManifestUrl>$($escape::Escape($cosManifest))</LeesMailCosUpdateManifestUrl>
    <PackageCertificateThumbprint>$($certificate.Thumbprint)</PackageCertificateThumbprint>
  </PropertyGroup>
</Project>
"@
[IO.File]::WriteAllText(
    (Join-Path $resolvedSourceRoot "LeesMail.Private.props"),
    $content,
    [Text.UTF8Encoding]::new($false)
)
