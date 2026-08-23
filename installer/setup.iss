; Inno Setup 6 script for LongForm Music Studio.
; Build the portable output first (installer\build_portable.ps1), then:
;   ISCC.exe installer\setup.iss
; Produces releases\LongFormMusicStudio-<version>-setup.exe

#define MyAppName "LongForm Music Studio"
; VERSION is always three-part (X.Y.Z), so the fixed-fileversion string
; returned here always carries exactly one trailing ".0" - trim it.
#define MyAppVersionFull GetVersionNumbersString("..\dist\LongFormMusicStudio\LongFormMusicStudio.exe")
#define MyAppVersion Copy(MyAppVersionFull, 1, Len(MyAppVersionFull) - 2)
#define MyAppExeName "LongFormMusicStudio.exe"

[Setup]
AppId={{8C6F4A52-7B1D-4E9B-9F3A-LFMS00112233}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher="LFMS Project"
DefaultDirName={autopf}\LongFormMusicStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\releases
OutputBaseFilename=LongFormMusicStudio-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\LongFormMusicStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
