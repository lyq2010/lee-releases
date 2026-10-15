#Requires -Version 7.0
$ErrorActionPreference='Stop'
$jdk=$env:JAVA_HOME
$windows=$env:RELEASE_TARGET -eq 'windows-x86_64' -and $IsWindows
$mac=$env:RELEASE_TARGET -eq 'darwin-aarch64' -and $IsMacOS
if(!$jdk -or (!$windows -and !$mac)){throw 'JDK target mismatch'}
$release=Get-Content (Join-Path $jdk 'release') -Raw -Encoding UTF8
if($release -notmatch '(?m)^JAVA_VERSION="25\.0\.4\.1"' -or $release -notmatch '(?m)^IMPLEMENTOR="Eclipse Adoptium"'){throw 'Exact Temurin JDK 25.0.4.1 is required'}
foreach($name in @('java','javac','jar','jlink')){
    $file=Join-Path $jdk ('bin/'+$name+$(if($windows){'.exe'}else{''}))
    if(!(Test-Path -LiteralPath $file -PathType Leaf)){throw 'Complete JDK compiler input is missing'}
}
if(!(Test-Path -LiteralPath (Join-Path $jdk 'jmods/java.base.jmod') -PathType Leaf)){throw 'JDK module input is missing'}
