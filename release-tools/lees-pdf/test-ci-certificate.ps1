# Synthetic certificate, mocked imports: never modifies this computer's trust stores.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ci-certificate.ps1')
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lees-pdf-ci-certificate-' + [Guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $testRoot
$rsa = [Security.Cryptography.RSA]::Create(2048)
$request = [Security.Cryptography.X509Certificates.CertificateRequest]::new(
    'CN=synthetic PDF test', $rsa, [Security.Cryptography.HashAlgorithmName]::SHA256,
    [Security.Cryptography.RSASignaturePadding]::Pkcs1)
$certificate = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddDays(1))
$file = Join-Path $testRoot 'public.cer'
[IO.File]::WriteAllBytes($file, $certificate.RawData)
$hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant()
$imports = [Collections.Generic.List[string]]::new()
function Import-Certificate {
    param($FilePath, $CertStoreLocation, [switch]$Confirm)
    if ($CertStoreLocation -eq 'Cert:\CurrentUser\Root') { throw 'Interactive certificate prompt' }
    if ($Confirm -or $FilePath -ne $file) { throw 'Unexpected certificate import' }
    $imports.Add($CertStoreLocation)
}
function Assert-Rejected([scriptblock]$Work, [string]$Pattern) {
    try { & $Work } catch {
        if ($_.Exception.Message -notmatch $Pattern -or $imports.Count) { throw }
        return
    }
    throw 'Unsafe certificate input was accepted'
}
$previousActions = $env:GITHUB_ACTIONS
$previousRunner = $env:RUNNER_ENVIRONMENT
try {
    $env:GITHUB_ACTIONS = 'true'; $env:RUNNER_ENVIRONMENT = 'github-hosted'
    Assert-Rejected { Set-CiCertificateTrust $file ('0' * 64) } '固定发布者'
    $env:RUNNER_ENVIRONMENT = 'self-hosted'
    Assert-Rejected { Set-CiCertificateTrust $file $hash } 'GitHub-hosted'
    $env:RUNNER_ENVIRONMENT = 'github-hosted'; $env:GITHUB_ACTIONS = $null
    Assert-Rejected { Set-CiCertificateTrust $file $hash } 'GitHub-hosted'
    $env:GITHUB_ACTIONS = 'true'
    Set-CiCertificateTrust $file $hash
    if (($imports -join ',') -ne 'Cert:\LocalMachine\Root,Cert:\LocalMachine\TrustedPeople') {
        throw 'CI trust must avoid the interactive CurrentUser Root store'
    }
    Write-Output 'CI certificate: publisher, local/self-hosted rejection and unattended import passed (mocked)'
} finally {
    $env:GITHUB_ACTIONS = $previousActions; $env:RUNNER_ENVIRONMENT = $previousRunner
    $certificate.Dispose(); $rsa.Dispose()
}
