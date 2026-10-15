# Hash checks are shared by CI preparation and the final packaging boundary.
function Get-LeesPdfPinnedInput([string]$Uri,[string]$Path,[string]$Sha256) {
    if($Uri -notmatch '^https://' -or $Sha256 -notmatch '^[a-f0-9]{64}$'){throw 'Invalid pinned dependency identity'}
    if(!(Test-Path -LiteralPath $Path)){
        New-Item -ItemType Directory -Path (Split-Path $Path) -Force | Out-Null
        Invoke-WebRequest -Uri $Uri -OutFile $Path
    }
    if((Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant() -ne $Sha256){throw 'Pinned dependency checksum mismatch'}
}
function Assert-LeesPdfNativeSources([string]$SourceRoot,$Index) {
    $bound=@{}
    foreach($entry in $Index.nativeSources){
        if($entry.path -notmatch '^native/(scan-worker|font-worker)/' -or $entry.path -match '(^|/)\.\.(/|$)|\\' -or $bound.ContainsKey($entry.path)){throw 'Invalid or duplicate native source path'}
        $bound[$entry.path]=$true
        if((Get-FileHash -LiteralPath (Join-Path $SourceRoot $entry.path)).Hash.ToLowerInvariant() -ne $entry.sha256){throw 'Native worker source identity mismatch'}
    }
    $tracked=@(& git -C $SourceRoot ls-files native/scan-worker native/font-worker | Sort-Object)
    if($LASTEXITCODE -or $tracked.Count -lt 2 -or @(Compare-Object $tracked @($bound.Keys | Sort-Object)).Count){throw 'Runtime must bind the complete native source list'}
}
function Get-LeesPdfCrtDirectory([string]$Installation) {
    $version=(Get-Content -LiteralPath (Join-Path $Installation 'VC/Auxiliary/Build/Microsoft.VCRedistVersion.default.txt') -Raw).Trim()
    if($version -notmatch '^14\.\d+\.\d+$'){throw 'Unexpected compiler CRT version'}
    $base=Join-Path $Installation "VC/Redist/MSVC/$version/x64"
    $names=@('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','concrt140.dll')
    $candidates=@(Get-ChildItem -LiteralPath $base -Directory -Filter 'Microsoft.VC*.CRT' | Where-Object {
        $directory=$_.FullName
        @($names | Where-Object {!(Test-Path -LiteralPath (Join-Path $directory $_) -PathType Leaf)}).Count -eq 0
    })
    if($candidates.Count -ne 1){throw 'Compiler CRT resource directory is missing or ambiguous'}
    return $candidates[0].FullName
}
