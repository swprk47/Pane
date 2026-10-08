; Pane installer (Inno Setup 6). Build with:  python tools/build_release.py --installer
; Standalone:  ISCC.exe /DAppVersion=1.1.0 installer\pane.iss      (needs dist\Pane\ from PyInstaller)

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppName "Pane"
#define AppExe "Pane.exe"
#define AppUserModelId "Pane.Player"
#define SourceDir "..\dist\Pane"

[Setup]
; Never change AppId: it is how a new version finds and replaces the installed one.
AppId={{8C6E2F5A-3B1D-4E7A-9D52-6A1F0C4B7E31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default (no administrator prompt); the user can choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-setup
SetupIconFile=..\assets\pane.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\release\LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} setup

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.AssocTask=Add Pane to the "Open with" list of video files
korean.AssocTask=영상 파일의 "연결 프로그램" 목록에 Pane 등록
english.AssocGroup=File associations:
korean.AssocGroup=파일 연결:
english.DeleteSettingsPrompt=Also delete Pane's settings (resume positions, speed presets, controller layout) and its error log?
korean.DeleteSettingsPrompt=Pane의 설정(이어보기 위치, 배속 프리셋, 컨트롤 배치)과 오류 기록도 함께 삭제할까요?
english.AssocDescription=Pane video player
korean.AssocDescription=Pane 동영상 플레이어

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "{cm:AssocTask}"; GroupDescription: "{cm:AssocGroup}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID matches core/app: SetCurrentProcessExplicitAppUserModelID("Pane.Player"), so the
; taskbar groups the window with this shortcut and a pinned icon keeps working.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelId}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelId}"; Tasks: desktopicon

[Registry]
; ProgId for video files opened with Pane
Root: HKA; Subkey: "Software\Classes\Pane.Video"; ValueType: string; ValueData: "{cm:AssocDescription}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Pane.Video\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Pane.Video\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: fileassoc
; The exe itself (shows up in "Open with" and gets its name/icon there)
Root: HKA; Subkey: "Software\Classes\Applications\Pane.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\Pane.exe\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: fileassoc
; Capabilities: makes Pane selectable in Settings > Default apps (it never claims a default itself)
Root: HKA; Subkey: "Software\Pane\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Pane\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:AssocDescription}"; Tasks: fileassoc
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\Pane\Capabilities"; Flags: uninsdeletevalue; Tasks: fileassoc
#include "extensions.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function ShouldDeleteSettings(): Boolean;
var
  i: Integer;
begin
  { silent uninstall keeps the user's data unless /DELETESETTINGS is passed }
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), '/DELETESETTINGS') = 0 then
      Result := True;
  if (not Result) and (not UninstallSilent) then
    Result := MsgBox(CustomMessage('DeleteSettingsPrompt'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if ShouldDeleteSettings() then
    begin
      { QSettings("Pane", group) lives in HKCU\Software\Pane\<group> }
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Pane\AppSettings');
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Pane\ControllerLayout');
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Pane\SpeedSettings');
      DelTree(ExpandConstant('{localappdata}\Pane'), True, True, True);
    end;
    { drop the parent key only when nothing is left in it }
    RegDeleteKeyIfEmpty(HKCU, 'Software\Pane');
  end;
end;
