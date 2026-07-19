#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef SourcePath
  #error SourcePath is required
#endif
#ifndef OutputPath
  #error OutputPath is required
#endif

[Setup]
AppId={{DCE23705-D418-4C42-BA32-61E659944747}
AppName=Lee's Mail
AppVersion={#AppVersion}
AppPublisher=Lee
VersionInfoVersion={#AppVersion}.0
DefaultDirName={autopf}\Lee's Mail
CreateAppDir=no
Uninstallable=no
OutputDir={#OutputPath}
OutputBaseFilename=LeesMail_{#AppVersion}_x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=yes
DisableProgramGroupPage=yes
SetupLogging=yes
SignedUninstaller=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourcePath}\LeesMail_CN-Lee.cer"; Flags: dontcopy
Source: "{#SourcePath}\LeesMail.msix"; Flags: dontcopy
Source: "{#SourcePath}\InstallLeesMail.ps1"; Flags: dontcopy

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  PowerShellPath: String;
  Parameters: String;
begin
  Result := '';
  ExtractTemporaryFile('LeesMail_CN-Lee.cer');
  ExtractTemporaryFile('LeesMail.msix');
  ExtractTemporaryFile('InstallLeesMail.ps1');

  PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  Parameters :=
    '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' +
    AddQuotes(ExpandConstant('{tmp}\InstallLeesMail.ps1')) +
    ' -CertificatePath ' + AddQuotes(ExpandConstant('{tmp}\LeesMail_CN-Lee.cer')) +
    ' -PackagePath ' + AddQuotes(ExpandConstant('{tmp}\LeesMail.msix'));

  if not Exec(PowerShellPath, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := '无法启动 Lee''s Mail 安装程序。';
    exit;
  end;

  if ResultCode <> 0 then
    Result := Format('Lee''s Mail 安装失败（错误代码 %d）。请查看安装日志。', [ResultCode]);
end;
