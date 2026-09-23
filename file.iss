[Setup]
; Keep this AppId fixed so new versions upgrade the existing install.
AppId={{4907aea0-bc99-454c-ac74-893a94beffbc}}
AppName=Hariku
AppVersion=2.1.0
AppPublisher=InfiArtt
AppPublisherURL=https://github.com/InfiArtt/hariku-core
AppSupportURL=https://github.com/InfiArtt/hariku-core/issues
AppUpdatesURL=https://github.com/InfiArtt/hariku/releases
; Version info embedded in the installer .exe (the CI stamps the real version).
VersionInfoVersion=2.1.0
VersionInfoProductName=Hariku
VersionInfoCompany=InfiArtt
VersionInfoDescription=Hariku Setup
VersionInfoCopyright=Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors
DefaultDirName={sd}\Inflinity\Hariku
DefaultGroupName=Inflinity
OutputDir=Output
OutputBaseFilename=HarikuV2-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
UninstallDisplayIcon={app}\Hariku.exe
PrivilegesRequired=lowest
LicenseFile=License.txt

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "startup"; Description: "Run Hariku when Windows starts"; GroupDescription: "Startup behavior:"; Flags: unchecked
; checkedonce: this option is ticked by default.
Name: "runafterinstall"; Description: "Run Hariku after installation"; GroupDescription: "Post-installation actions:"; Flags: checkedonce

[Files]
Source: "Hariku.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Hariku"; Filename: "{app}\Hariku.exe"
Name: "{userdesktop}\Hariku"; Filename: "{app}\Hariku.exe"; Tasks: desktopicon
Name: "{userstartup}\Hariku"; Filename: "{app}\Hariku.exe"; Tasks: startup

[Run]
Filename: "{app}\Hariku.exe"; Description: "Run Hariku"; Flags: nowait postinstall skipifsilent; Tasks: runafterinstall

[Code]
// --- HELPER FUNCTIONS ---

function IsModuleInUse(FileName: String): Boolean;
begin
  Result := False;
  if FileExists(FileName) then
  begin
    // Try to rename the file to itself. If it fails, the file is locked/in use.
    if not RenameFile(FileName, FileName) then
      Result := True;
  end;
end;

// --- EVENT HANDLERS ---

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  OldInstallPath: String;
  ExePath: String;
begin
  Result := True;
  
  // Try to find the existing installation path from Registry to avoid {app} expansion error
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4907aea0-bc99-454c-ac74-893a94beffbc}_is1', 'InstallLocation', OldInstallPath) then
  begin
    ExePath := AddBackslash(OldInstallPath) + 'Hariku.exe';
  end
  else
  begin
    // Fallback to default path if not found in registry
    ExePath := ExpandConstant('{sd}\Inflinity\Hariku\Hariku.exe');
  end;

  // Detection loop
  while IsModuleInUse(ExePath) do
  begin
    if MsgBox('Hariku is currently running.' #13#13 + 
              'The installer needs to close the application to proceed with the update. Click OK to close it automatically.', 
              mbConfirmation, MB_OKCANCEL) = IDOK then
    begin
      // Force kill the process
      Exec('taskkill.exe', '/f /im Hariku.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1000); // Wait for the OS to release file locks
    end
    else
    begin
      // Abort installation if user cancels
      Result := False;
      Exit;
    end;
  end;
end;

procedure InitializeWizard;
begin
  MsgBox('Welcome! Thank you for choosing Hariku.'#13#13 +
         'Your support and feedback help make this app better.'#13#13 +
         'For more information visit https://github.com/InfiArtt/hariku-core',
         mbInformation, MB_OK);
end;