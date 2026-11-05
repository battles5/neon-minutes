; Setup wizard of Neon Minutes. Built by installer\build_installer.ps1, which passes:
;   /DAppVersion=x.y.z  /DStage=<staging folder>  /O<output folder>
;   and the download/disk sizes measured at build time (MB): DlTorchCuda, DlTorchCpu, DlDeps,
;   DlModelCuda, DlModelCpu, InstCuda, InstCpu
; Per-user install (no admin rights). The heavy parts (PyTorch, Whisper) are downloaded at
; install time by installer\postinstall.py, in the variant that fits the PC's hardware, while
; a progress page shows the step, the amount downloaded and the time left.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Stage
  #define Stage "..\build\stage"
#endif
#ifndef DlTorchCuda
  #define DlTorchCuda "2800"
  #define DlTorchCpu "120"
  #define DlDeps "300"
  #define DlModelCuda "3100"
  #define DlModelCpu "1650"
  #define InstCuda "5500"
  #define InstCpu "1300"
#endif
#define AppName "Neon Minutes"
#define AppExe "{app}\runtime\pythonw.exe"
#define AppArgs "-m meeting_transcriber.gui"

[Setup]
AppId={{6F2B4E61-3C1D-4B8A-9E57-2A9D0C7B5F13}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Orso Peruzzi
AppPublisherURL=https://github.com/battles5/neon-minutes
AppComments=Trascrizione locale delle riunioni con i nomi di chi parla
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#Stage}\LICENSE.txt
InfoBeforeFile=requisiti.txt
SetupIconFile={#Stage}\assets\piuma.ico
WizardImageFile={#Stage}\assets\wizard_side.bmp
WizardSmallImageFile={#Stage}\assets\wizard_small.bmp
UninstallDisplayIcon={app}\assets\piuma.ico
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputBaseFilename=NeonMinutes-Setup-{#AppVersion}
; Only the setup's own files; downloads and their space are checked on the hardware page.
ExtraDiskSpaceRequired=0
CloseApplications=yes

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"
Name: "modelli"; Description: "Scarica subito il modello Whisper, così la prima trascrizione parte subito (consigliato)"

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}\{#AppName}"; Filename: "{#AppExe}"; Parameters: "{#AppArgs}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\piuma.ico"; Comment: "Trascrivi riunioni con i nomi di chi parla"
Name: "{autoprograms}\{#AppName}\Guida"; Filename: "{app}\docs\Guide.html"
Name: "{autoprograms}\{#AppName}\Ripara componenti"; Filename: "{app}\runtime\python.exe"; Parameters: "-u ""{app}\installer\postinstall.py"" --app ""{app}"" --variant auto --models"; WorkingDir: "{app}"; IconFilename: "{app}\assets\piuma.ico"; Comment: "Reinstalla PyTorch e le librerie (per esempio dopo aver cambiato scheda video o driver)"
Name: "{autoprograms}\{#AppName}\Disinstalla"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{#AppExe}"; Parameters: "{#AppArgs}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\piuma.ico"; Tasks: desktopicon

[InstallDelete]
; The program was called "Trascrittore riunioni" up to 1.1.0 and "Neon Verbale" from 1.2.0 to 1.4.0
; (same AppId, so this is an upgrade): drop the shortcuts with the old names, the new ones are
; created below. The program folder itself is moved in PrepareToInstall.
Type: filesandordirs; Name: "{autoprograms}\Trascrittore riunioni"
Type: files; Name: "{autodesktop}\Trascrittore riunioni.lnk"
Type: filesandordirs; Name: "{autoprograms}\Neon Verbale"
Type: files; Name: "{autodesktop}\Neon Verbale.lnk"
; The user guide was docs\Guida.html up to 1.3.0's English docs.
Type: files; Name: "{app}\docs\Guida.html"

[Run]
Filename: "{#AppExe}"; Parameters: "{#AppArgs}"; WorkingDir: "{app}"; Description: "Avvia {#AppName}"; Flags: postinstall nowait skipifsilent; Check: ComponentsReady
Filename: "{app}\docs\Guide.html"; Description: "Apri la guida"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
; Everything pip put in the bundled Python, caches and logs.
Type: filesandordirs; Name: "{app}"

[Code]
var
  HardwarePage: TWizardPage;
  HardwareMemo: TNewMemo;
  ProgressPage: TOutputProgressWizardPage;
  GpuVariant, GpuText, LastError, GpuWarning: String;
  PostInstallOk: Boolean;

function NextField(var S: String; const Sep: String): String;
var
  P: Integer;
begin
  P := Pos(Sep, S);
  if P = 0 then begin
    Result := Trim(S);
    S := '';
  end else begin
    Result := Trim(Copy(S, 1, P - 1));
    S := Copy(S, P + Length(Sep), Length(S));
  end;
end;

function MajorOf(const S: String): Integer;
var
  P: Integer;
begin
  P := Pos('.', S);
  if P = 0 then Result := StrToIntDef(S, 0) else Result := StrToIntDef(Copy(S, 1, P - 1), 0);
end;

function MinorOf(const S: String): Integer;
var
  P: Integer;
begin
  P := Pos('.', S);
  if P = 0 then Result := 0 else Result := StrToIntDef(Copy(S, P + 1, 2), 0);
end;

{ "6,1 GB" from megabytes, rounded to the nearest tenth. }
function GB(const MB: Integer): String;
var
  Tenths: Integer;
begin
  Tenths := (MB + 50) div 100;
  Result := IntToStr(Tenths div 10) + ',' + IntToStr(Tenths mod 10) + ' GB';
end;

{ Same rules as installer\postinstall.py: CUDA 12.8 needs compute capability 7.5+, }
{ driver 570+, and Whisper large-v3 needs at least 3.5 GB of video memory. }
procedure DetectHardware();
var
  ResultCode, MemMB, CapMajor, CapMinor: Integer;
  TmpFile, Line, Name, Mem, Driver, Cap: String;
  Lines: TArrayOfString;
begin
  GpuVariant := 'cpu';
  GpuText := 'Nessuna scheda video NVIDIA trovata.';
  TmpFile := ExpandConstant('{tmp}\gpu.txt');
  if Exec(ExpandConstant('{cmd}'), '/C nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader,nounits > "' + TmpFile + '" 2>nul',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
     and (ResultCode = 0) and LoadStringsFromFile(TmpFile, Lines) and (GetArrayLength(Lines) > 0) then
  begin
    Line := Lines[0];
    Name := NextField(Line, ',');
    Mem := NextField(Line, ',');
    Driver := NextField(Line, ',');
    Cap := NextField(Line, ',');
    MemMB := StrToIntDef(Mem, 0);
    CapMajor := MajorOf(Cap);
    CapMinor := MinorOf(Cap);
    if (CapMajor * 10 + CapMinor) < 75 then
      GpuText := 'Trovata ' + Name + ', ma è di una generazione troppo vecchia (compute capability ' + Cap + ', serve 7.5 o superiore).'
    else if MemMB < 3584 then
      GpuText := 'Trovata ' + Name + ', ma ha solo ' + Mem + ' MB di memoria video (ne servono almeno 3,5 GB).'
    else if MajorOf(Driver) < 570 then
      GpuText := 'Trovata ' + Name + ', ma il driver ' + Driver + ' è troppo vecchio (serve 570 o successivo). Aggiornandolo e poi usando "Ripara componenti" si passa alla modalità veloce.'
    else begin
      GpuVariant := 'cuda';
      GpuText := 'Trovata ' + Name + ' (' + IntToStr((MemMB + 512) div 1024) + ' GB di memoria video, driver ' + Driver + ').';
    end;
  end;
end;

function DownloadMB(): Integer;
begin
  if GpuVariant = 'cuda' then Result := {#DlTorchCuda} + {#DlDeps} else Result := {#DlTorchCpu} + {#DlDeps};
  if WizardIsTaskSelected('modelli') then
    if GpuVariant = 'cuda' then Result := Result + {#DlModelCuda} else Result := Result + {#DlModelCpu};
end;

{ Installed size, plus the model if downloaded now. }
function DiskMB(): Integer;
begin
  if GpuVariant = 'cuda' then Result := {#InstCuda} else Result := {#InstCpu};
  if WizardIsTaskSelected('modelli') then
    if GpuVariant = 'cuda' then Result := Result + {#DlModelCuda} else Result := Result + {#DlModelCpu};
end;

{ pip keeps the largest package in a temporary folder while it unpacks it. }
function PeakDiskMB(): Integer;
begin
  if GpuVariant = 'cuda' then Result := DiskMB() + {#DlTorchCuda} else Result := DiskMB() + {#DlDeps};
end;

{ Minutes to download at the given Mbit/s, plus unpacking (measured: about 8 minutes for }
{ the GPU build, antivirus scanning included; the CPU build is much smaller). }
function Minutes(const MB, Mbit: Integer): String;
begin
  if GpuVariant = 'cuda' then
    Result := IntToStr(MB * 8 div Mbit div 60 + 8)
  else
    Result := IntToStr(MB * 8 div Mbit div 60 + 5);
end;

function SummaryText(): String;
var
  Torch, Model: Integer;
begin
  if GpuVariant = 'cuda' then begin
    Torch := {#DlTorchCuda};
    Model := {#DlModelCuda};
    Result := GpuText + #13#10 + 'Verrà installata la versione per GPU NVIDIA (modalità veloce): ' +
      'una riunione di un''ora richiede circa 12-15 minuti.';
  end else begin
    Torch := {#DlTorchCpu};
    Model := {#DlModelCpu};
    Result := GpuText + #13#10 + 'Verrà installata la versione per CPU: funziona su qualunque PC, ma è più lenta ' +
      '(una riunione di un''ora richiede circa 1 ora e mezza su un processore potente, 2-3 ore su un portatile da ufficio).';
  end;
  Result := Result + #13#10#13#10 + 'DA SCARICARE: circa ' + GB(DownloadMB()) + #13#10 +
    '  - PyTorch: ' + GB(Torch) + #13#10 +
    '  - altre librerie: ' + GB({#DlDeps}) + #13#10;
  if WizardIsTaskSelected('modelli') then
    Result := Result + '  - modello Whisper: ' + GB(Model) + #13#10
  else
    Result := Result + '  - modello Whisper (' + GB(Model) + '): al primo utilizzo, perché non hai scelto di scaricarlo ora' + #13#10;
  Result := Result + #13#10 + 'SPAZIO SU DISCO: circa ' + GB(DiskMB()) + ' a installazione finita, ' +
    'fino a ' + GB(PeakDiskMB()) + ' durante l''installazione.' + #13#10#13#10 +
    'TEMPO INDICATIVO: circa ' + Minutes(DownloadMB(), 50) + ' minuti con una connessione da 50 Mbit/s, ' +
    Minutes(DownloadMB(), 200) + ' minuti a 200 Mbit/s. Durante l''installazione vedrai l''avanzamento e il tempo rimanente.';
end;

{ --- upgrade from an older name ------------------------------------------------------------- }

const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F2B4E61-3C1D-4B8A-9E57-2A9D0C7B5F13}_is1';

{ Folder of the installed copy, if its name is one of the program's old names. }
function OldAppDir(): String;
var
  Name: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, UninstallKey, 'Inno Setup: App Path', Result) then begin
    Name := ExtractFileName(RemoveBackslashUnlessRoot(Result));
    if (CompareText(Name, 'Neon Verbale') <> 0) and (CompareText(Name, 'Trascrittore riunioni') <> 0) then
      Result := '';
  end else
    Result := '';
end;

{ Propose the old folder's sibling with the new name: PrepareToInstall moves it there. }
procedure ProposeRenamedDir();
var
  Old: String;
begin
  Old := OldAppDir();
  if Old <> '' then
    WizardForm.DirEdit.Text := AddBackslash(ExtractFilePath(RemoveBackslashUnlessRoot(Old))) + '{#AppName}';
end;

{ Move the old installation (bundled Python and libraries included) to the new folder, so the }
{ upgrade downloads nothing; the old uninstaller goes, the setup writes a new one. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Old, New: String;
begin
  Result := '';
  Old := RemoveBackslashUnlessRoot(OldAppDir());
  New := RemoveBackslashUnlessRoot(WizardDirValue());
  if (Old = '') or not DirExists(Old) or DirExists(New) or (CompareText(Old, New) = 0) then
    Exit;
  if not RenameFile(Old, New) then begin
    Result := 'Non riesco a spostare la versione installata da' + #13#10 + Old + #13#10 + 'a' + #13#10 + New
      + #13#10#13#10 + 'Chiudi Neon Verbale (anche le trascrizioni in corso) e riprova.';
    Exit;
  end;
  Log('Installazione precedente spostata da ' + Old + ' a ' + New);
  DelTree(New + '\unins*.*', False, True, False);
end;

{ An icon pinned to the taskbar points to the old folder: keep it working. }
procedure RefreshPinnedIcons();
var
  Dir: String;
  I: Integer;
  Names: array[0..1] of String;
begin
  Dir := ExpandConstant('{userappdata}\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\');
  Names[0] := 'Neon Verbale.lnk';
  Names[1] := 'Trascrittore riunioni.lnk';
  for I := 0 to 1 do
    if FileExists(Dir + Names[I]) then
      CreateShellLink(Dir + Names[I], '{#AppName}', ExpandConstant('{#AppExe}'), '{#AppArgs}',
        ExpandConstant('{app}'), ExpandConstant('{app}\assets\piuma.ico'), 0, SW_SHOWNORMAL);
end;

procedure InitializeWizard();
begin
  DetectHardware();
  ProposeRenamedDir();
  { A read-only memo rather than a label: the summary is filled in later (it depends on the }
  { tasks chosen) and a label keeps the height it had when it was empty. }
  HardwarePage := CreateCustomPage(wpSelectTasks, 'Verifica dell''hardware e spazio necessario',
    'Cosa verrà installato, quanto verrà scaricato e quanto spazio servirà');
  HardwareMemo := TNewMemo.Create(HardwarePage);
  HardwareMemo.Parent := HardwarePage.Surface;
  HardwareMemo.Align := alClient;
  HardwareMemo.ReadOnly := True;
  HardwareMemo.WordWrap := True;
  HardwareMemo.ScrollBars := ssVertical;
  ProgressPage := CreateOutputProgressPage('Installazione dei componenti',
    'Scarico e installo PyTorch, le librerie e il modello Whisper. Puoi continuare a usare il PC.');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = HardwarePage.ID then
    HardwareMemo.Text := SummaryText();
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  { On an upgrade the folder page is skipped and MemoDirInfo is empty. }
  Result := '';
  if MemoDirInfo <> '' then Result := MemoDirInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then Result := Result + MemoTasksInfo + NewLine + NewLine;
  if GpuVariant = 'cuda' then
    Result := Result + 'Versione:' + NewLine + Space + 'GPU NVIDIA (CUDA 12.8)' + NewLine + NewLine
  else
    Result := Result + 'Versione:' + NewLine + Space + 'CPU' + NewLine + NewLine;
  Result := Result + 'Da scaricare:' + NewLine + Space + 'circa ' + GB(DownloadMB()) + NewLine + NewLine +
    'Spazio su disco:' + NewLine + Space + 'circa ' + GB(DiskMB()) + ' (fino a ' + GB(PeakDiskMB()) +
    ' durante l''installazione)';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  FreeMB, TotalMB: Cardinal;
begin
  Result := True;
  { PyTorch and ONNX Runtime nest files ~130 characters deep under runtime\Lib\site-packages: }
  { on PCs without long-path support a longer folder would break the install halfway. }
  if (CurPageID = wpSelectDir) and (Length(WizardDirValue) > 120) then begin
    SuppressibleMsgBox('Il percorso della cartella è troppo lungo (' + IntToStr(Length(WizardDirValue)) +
      ' caratteri, massimo 120): alcune librerie hanno file molto annidati e Windows non riuscirebbe a crearli.' + #13#10 +
      'Scegli una cartella più corta, per esempio quella proposta.', mbError, MB_OK, IDOK);
    Result := False;
  end;
  if CurPageID = HardwarePage.ID then begin
    if GetSpaceOnDisk(AddBackslash(ExtractFileDrive(WizardDirValue)), True, FreeMB, TotalMB) and (FreeMB < PeakDiskMB()) then
      Result := SuppressibleMsgBox('Sul disco ' + ExtractFileDrive(WizardDirValue) + ' ci sono ' + GB(FreeMB) +
        ' liberi, durante l''installazione ne servono fino a ' + GB(PeakDiskMB()) + '. Continuare comunque?',
        mbConfirmation, MB_YESNO, IDNO) = IDYES;
  end;
end;

{ postinstall.py reports progress as "@@P|<per mille>|<first line>|<second line>", }
{ errors as "@@E|<message>" and warnings as "@@W|<message>"; anything else goes to the log. }
procedure OnPostInstallLine(const S: String; const Error, FirstLine: Boolean);
var
  Rest, PerMille, First: String;
begin
  if Copy(S, 1, 4) = '@@P|' then begin
    Rest := Copy(S, 5, Length(S));
    PerMille := NextField(Rest, '|');
    First := NextField(Rest, '|');
    ProgressPage.SetText(First, Rest);
    ProgressPage.SetProgress(StrToIntDef(PerMille, 0), 1000);
  end else if Copy(S, 1, 4) = '@@E|' then
    LastError := Copy(S, 5, Length(S))
  else if Copy(S, 1, 4) = '@@W|' then
    GpuWarning := Copy(S, 5, Length(S))
  else
    Log('postinstall: ' + S);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Params: String;
begin
  if CurStep = ssInstall then
    Log('Riepilogo mostrato all''utente:' + #13#10 + SummaryText());
  if CurStep <> ssPostInstall then Exit;
  RefreshPinnedIcons();
  Params := '-u "' + ExpandConstant('{app}\installer\postinstall.py') + '" --app "' + ExpandConstant('{app}') +
    '" --variant ' + GpuVariant + ' --wizard';
  if WizardIsTaskSelected('modelli') then Params := Params + ' --models';
  ProgressPage.SetText('Avvio...', '');
  ProgressPage.SetProgress(0, 1000);
  ProgressPage.Show;
  try
    repeat
      LastError := '';
      try
        ExecAndLogOutput(ExpandConstant('{app}\runtime\python.exe'), Params, ExpandConstant('{app}'),
          SW_HIDE, ewWaitUntilTerminated, ResultCode, @OnPostInstallLine);
      except
        ResultCode := -1;
        LastError := GetExceptionMessage;
      end;
      PostInstallOk := ResultCode = 0;
    until PostInstallOk or (SuppressibleMsgBox(
        'L''installazione di PyTorch e delle librerie non è riuscita:' + #13#10 + LastError + #13#10#13#10 +
        'Di solito dipende dalla connessione a Internet o dal proxy aziendale. Dettagli in:' + #13#10 +
        ExpandConstant('{app}\install.log') + #13#10#13#10 + 'Riprovare adesso?',
        mbError, MB_YESNO, IDNO) = IDNO);
  finally
    ProgressPage.Hide;
  end;
  if not PostInstallOk then
    SuppressibleMsgBox('Il programma è installato ma non ancora pronto. Quando la connessione funziona, apri' + #13#10 +
      'Start > Neon Minutes > Ripara componenti.', mbInformation, MB_OK, IDOK)
  else if GpuWarning <> '' then
    SuppressibleMsgBox(GpuWarning, mbInformation, MB_OK, IDOK);
end;

function ComponentsReady(): Boolean;
begin
  Result := PostInstallOk;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
  DataDir := ExpandConstant('{localappdata}\{#AppName}');
  { Not migrated yet if the program was never started after the upgrade from 1.1.0. }
  if not DirExists(DataDir) then
    DataDir := ExpandConstant('{localappdata}\Trascrittore riunioni');
  if DirExists(DataDir) and (SuppressibleMsgBox(
      'Eliminare anche i dati personali del programma?' + #13#10#13#10 +
      '- modelli Whisper scaricati (fino a 3 GB)' + #13#10 +
      '- libreria delle voci riconosciute, glossario, impostazioni' + #13#10#13#10 +
      DataDir + #13#10#13#10 +
      'Le trascrizioni nelle cartelle "Trascrizioni" accanto ai video restano dove sono.',
      mbConfirmation, MB_YESNO, IDNO) = IDYES) then
    DelTree(DataDir, True, True, True);
end;
