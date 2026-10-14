#Requires -Version 7.0
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$true
if($env:RELEASE_TARGET -eq 'windows-x86_64' -and $IsWindows){
    $jdk=Join-Path $env:LEESPDF_RUNTIME_ROOT 'jdk'
}elseif($env:RELEASE_TARGET -eq 'darwin-aarch64' -and $IsMacOS){
    $directory=Join-Path $env:RUNNER_TEMP ('lees-pdf-jdk-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $directory | Out-Null
    $archive=Join-Path $directory 'jdk.tar.gz'
    Invoke-WebRequest -Uri 'https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jdk_aarch64_mac_hotspot_25.0.4.1_1.tar.gz' -OutFile $archive
    if((Get-FileHash $archive).Hash.ToLowerInvariant() -ne '61979887f7506a24a57439ff99adb8b3a7fc89977d9cfe3b8984f58a981b7b9d'){throw 'JDK archive identity mismatch'}
    $package=Join-Path $directory 'package'
    New-Item -ItemType Directory -Path $package | Out-Null
    & tar -xzf $archive -C $package --strip-components=1
    if($LASTEXITCODE){throw 'JDK extraction failed'}
    $jdk=Join-Path $package 'Contents/Home'
}else{throw 'JDK target mismatch'}
$release=Get-Content (Join-Path $jdk 'release') -Raw -Encoding UTF8
if($release -notmatch '(?m)^JAVA_VERSION="25\.0\.4\.1"' -or !(Test-Path (Join-Path $jdk $(if($IsWindows){'bin/javac.exe'}else{'bin/javac'})))){throw 'Exact JDK 25.0.4.1 compiler is required'}
"JAVA_HOME=$jdk" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append
