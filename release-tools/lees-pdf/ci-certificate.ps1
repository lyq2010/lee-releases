# Trust setup belongs only to disposable, administrator GitHub-hosted Windows VMs.
function Set-CiCertificateTrust {
    param([Parameter(Mandatory)][string]$CertificateFile,
          [Parameter(Mandatory)][string]$ExpectedSha256)
    if (!$IsWindows -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
        throw '证书信任配置仅允许 GitHub-hosted Windows runner'
    }
    $certificate = [Security.Cryptography.X509Certificates.X509Certificate2]::new($CertificateFile)
    try {
        $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant()
        if ($ExpectedSha256 -cnotmatch '^[a-f0-9]{64}$' -or $actual -cne $ExpectedSha256) {
            throw 'CI 证书与固定发布者不符'
        }
        # CurrentUser Root opens a native security dialog even without PowerShell confirmation.
        $null = Import-Certificate -FilePath $CertificateFile -CertStoreLocation Cert:\LocalMachine\Root -Confirm:$false
        $null = Import-Certificate -FilePath $CertificateFile -CertStoreLocation Cert:\LocalMachine\TrustedPeople -Confirm:$false
    } finally { $certificate.Dispose() }
}
