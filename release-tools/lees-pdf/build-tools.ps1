# Use the approved distribution entry, not the secondary compiler under Bin/.
function Get-NsisCompiler([string]$ExtractedDirectory) {
    $compiler = Join-Path $ExtractedDirectory 'nsis-3.11/makensis.exe'
    if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '固定 NSIS 发行入口缺失' }
    return $compiler
}