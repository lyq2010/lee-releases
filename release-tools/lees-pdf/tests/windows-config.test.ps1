#Requires -Version 7.0
param([Parameter(Mandatory)][string]$SourceRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../windows-config.ps1')
$source=Get-Content (Join-Path $SourceRoot 'apps/desktop/src-tauri/tauri.windows.conf.json') -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
$actual=New-LeesPdfWindowsConfig -SourceRoot $SourceRoot -CertificateThumbprint 'fixture-thumbprint'
foreach($name in @('installerIcon','uninstallerIcon','headerImage','sidebarImage','languages','displayLanguageSelector','installerHooks')){
    if(($actual.nsis[$name] | ConvertTo-Json -Compress) -cne ($source.bundle.windows.nsis[$name] | ConvertTo-Json -Compress)){throw "Installer setting lost: $name"}
}
if($actual.certificateThumbprint -ne 'fixture-thumbprint' -or $actual.ContainsKey('resources')){throw 'Signing or resource boundary changed'}
Write-Output 'PASS: release preserves product branding, languages and installer hooks with pinned signing identity'
