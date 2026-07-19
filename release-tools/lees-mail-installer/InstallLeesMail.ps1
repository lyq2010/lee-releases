[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CertificatePath,

    [Parameter(Mandatory = $true)]
    [string]$PackagePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
    throw "Lee's Mail signing certificate is missing."
}

if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    throw "Lee's Mail MSIX package is missing."
}

$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CertificatePath)
if ($certificate.Subject -ne "CN=Lee") {
    throw "Unexpected Lee's Mail certificate subject: $($certificate.Subject)"
}

$store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
    "TrustedPeople",
    [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine)
$certificateAdded = $false

try {
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $existing = @($store.Certificates.Find(
        [System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint,
        $certificate.Thumbprint,
        $false))
    if ($existing.Count -eq 0) {
        $store.Add($certificate)
        $certificateAdded = $true
    }
}
finally {
    $store.Close()
}

try {
    Add-AppxPackage -LiteralPath $PackagePath -ForceApplicationShutdown -ErrorAction Stop
}
catch {
    if ($certificateAdded) {
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        try {
            $store.Remove($certificate)
        }
        finally {
            $store.Close()
        }
    }
    throw
}
