# Preserve the product installer configuration while replacing private runtime resources.
function New-LeesPdfWindowsConfig([string]$SourceRoot,[string]$CertificateThumbprint) {
    $platform=Get-Content (Join-Path $SourceRoot 'apps/desktop/src-tauri/tauri.windows.conf.json') -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
    if(!$platform.bundle.windows.nsis){throw 'Windows installer configuration is missing'}
    return @{certificateThumbprint=$CertificateThumbprint;digestAlgorithm='sha256';timestampUrl='http://timestamp.digicert.com';minimumWebview2Version='109.0.1518.78';nsis=$platform.bundle.windows.nsis}
}
