# Use the approved distribution entry, not the secondary compiler under Bin/.
function Get-NsisCompiler([string]$ExtractedDirectory) {
    $compiler = Join-Path $ExtractedDirectory 'nsis-3.11/makensis.exe'
    if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '固定 NSIS 发行入口缺失' }
    return $compiler
}

function Get-ReleaseClangDirectory([string]$CacheDirectory) {
    # MSVC 14.52 requires Clang 22. The GitHub runner's global LLVM can be older.
    $name = 'LLVM-22.1.8-win64.exe'
    $archive = Join-Path $CacheDirectory $name
    $directory = Join-Path $CacheDirectory 'llvm-22.1.8'
    $sha256 = '16e5709785fef73c854646241c4a92c5cd574318d1b33c63330dd7721903e55c'
    $sevenZip = Join-Path $env:ProgramFiles '7-Zip/7z.exe'
    Invoke-WebRequest -Uri "https://github.com/llvm/llvm-project/releases/download/llvmorg-22.1.8/$name" `
        -OutFile $archive -MaximumRetryCount 2 -RetryIntervalSec 4 -TimeoutSec 300 -ProgressAction SilentlyContinue
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $sha256) {
        throw '固定 LLVM 发行资产的 SHA-256 校验失败'
    }
    & $sevenZip x $archive "-o$directory" -y -bso0 -bsp0
    if ($LASTEXITCODE) { throw '固定 LLVM 发行资产解包失败' }
    $bin = Join-Path $directory 'bin'
    foreach ($file in @('clang.exe', 'libclang.dll')) {
        if (!(Test-Path -LiteralPath (Join-Path $bin $file) -PathType Leaf)) { throw '固定 LLVM 构建工具缺失' }
    }
    return $bin
}
