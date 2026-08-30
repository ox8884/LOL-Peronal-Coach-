; 롤실전코치 — Inno Setup 6+ 설치 스크립트
; 컴파일:  ISCC.exe installer\롤실전코치.iss
; 또는:    powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
;
; 사전 조건: dist\롤실전코치.exe 가 빌드되어 있어야 함
;   → scripts\build_exe.ps1

#define MyAppName      "롤실전코치"
#define MyAppVersion   "1.6.108"
#define MyAppPublisher "Personal"
#define MyAppURL       "https://developer.riotgames.com/"
#define MyAppExeName   "롤실전코치.exe"
#define MyAppId        "{{A7C3E9F2-4B1D-4E8A-9C2F-6D5E8A1B3C4D}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppComments=개인 LoL 코칭 툴 — 카운터픽 · ARAM 증강 · 경기 복기
AppCopyright=Personal use
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
AllowNoIcons=yes
; 사용자 선택 가능 (기본: Program Files\롤실전코치)
UsePreviousAppDir=yes
; 관리자 권한 (Program Files) — 필요 시 "현재 사용자만" 으로 낮출 수 있음
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; 출력
OutputDir=..\installer_output
OutputBaseFilename=롤실전코치 Setup v{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; 압축
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
; 64비트
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 마법사 설명
InfoBeforeFile=info_before.txt
; 설치 완료 후 재시작 불필요
CloseApplications=yes
RestartApplications=no
; 버전 표시
VersionInfoVersion={#MyAppVersion}.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup — 개인 LoL 코칭 툴
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
korean.WelcomeLabel1=[name] 설치를 시작합니다
korean.WelcomeLabel2=이 프로그램은 픽타임에 쓰는 개인 LoL 코칭 툴입니다.%n%n· 협곡 카운터픽 · ARAM 증강 · 경기 복기%n%n계속하려면 [다음]을 클릭하세요.
korean.FinishedLabel=설치가 완료되었습니다.%n%n첫 실행 시 Riot API 키 입력을 안내합니다.
english.WelcomeLabel2=This is a personal LoL coaching tool for pick phase.%n%n· SR counters · ARAM Mayhem · Match review%n%nClick Next to continue.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
[Files]
; PyInstaller onedir 출력 폴더 전체 (실행마다 압축 해제 없음 — 기동 속도)
Source: "..\dist\롤실전코치\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 선택: 아이콘 리소스 (바로가기용 — exe 내장 아이콘 우선)
Source: "..\assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; 시작 메뉴
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "개인 LoL 코칭 툴"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"; Comment: "롤실전코치 제거"
; 바탕화면 (Tasks 선택 시)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "개인 LoL 코칭 툴"; Tasks: desktopicon

[Run]
; 설치 완료 후 실행 체크박스 (기본 선택)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

[UninstallDelete]
; 설치 폴더에 남은 임시 파일만 정리 (.env 는 AppData 에 있으므로 유지)
Type: filesandordirs; Name: "{app}\cache"
Type: files; Name: "{app}\.write_test"

[Code]
function InitializeSetup(): Boolean;
begin
  { exe 는 컴파일 타임에 [Files] 로 인스톨러에 포함된다.
    런타임에 빌드 환경 경로를 검사하면 사용자 PC 에서 설치가 막히므로
    이 함수는 항상 통과시킨다. }
  Result := True;
end;
