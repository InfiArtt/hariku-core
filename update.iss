; Hariku Updater Script - Semi-Automatic with Progress UI
[Setup]
AppId={{4907aea0-bc99-454c-ac74-893a94beffbc}}
AppName=Hariku
AppVersion=2.1.0
DefaultDirName={sd}\Inflinity\Hariku
DefaultGroupName=Inflinity
OutputDir=Output-update
OutputBaseFilename=latestV2
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest

; UI Settings: Menghilangkan semua halaman konfirmasi tapi tetap memunculkan jendela progres
DisableWelcomePage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
DisableDirPage=yes
DisableStartupPrompt=yes
; Menghilangkan tombol Cancel agar user tidak membatalkan update di tengah jalan
AllowCancelDuringInstall=no

[Files]
; Flag 'ignoreversion' wajib ada agar file ditimpa total
Source: "Hariku.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Run]
; Langsung jalankan setelah install selesai tanpa perlu postinstall (karena UI-nya skip)
Filename: "{app}\Hariku.exe"; Flags: nowait

[Code]
// --- HELPER FUNCTIONS ---

function IsModuleInUse(FileName: String): Boolean;
begin
  Result := False;
  if FileExists(FileName) then
  begin
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
  
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4907aea0-bc99-454c-ac74-893a94beffbc}_is1', 'InstallLocation', OldInstallPath) then
  begin
    ExePath := AddBackslash(OldInstallPath) + 'Hariku.exe';
  end
  else
  begin
    ExePath := ExpandConstant('{sd}\Inflinity\Hariku\Hariku.exe');
  end;

  // Deteksi dan tutup otomatis tanpa MessageBox (karena ini updater)
  // Tapi jika gagal tutup, baru tampilkan pesan error
  if IsModuleInUse(ExePath) then
  begin
      Exec('taskkill.exe', '/f /im Hariku.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1000); 
  end;
  
  // Jika setelah ditunggu masih terbuka (misal: taskkill gagal), tampilkan peringatan
  while IsModuleInUse(ExePath) do
  begin
    if MsgBox('The update cannot proceed because Hariku is still open.' #13#13 + 
              'Please close the app manually and click OK to continue.', 
              mbError, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure InitializeWizard;
begin
  // Mengubah teks judul saat proses instalasi berjalan agar informatif
  WizardForm.Caption := 'Updating Hariku to Version 2.1.0';
  WizardForm.StatusLabel.Caption := 'Updating files, please wait...';
end;