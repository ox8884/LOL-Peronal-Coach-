# 롤실전코치 — exe + Inno Setup 설치 프로그램 빌드
# 사용:
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipExe

param(
    [switch]$SkipExe
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Find-ISCC {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# 1) exe
if (-not $SkipExe) {
    Write-Host "==> 1/2  PyInstaller exe 빌드" -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File "$Root\scripts\build_exe.ps1"
    if ($LASTEXITCODE -ne 0) { throw "exe 빌드 실패" }
} else {
    Write-Host "==> exe 빌드 건너뜀 (-SkipExe)" -ForegroundColor Yellow
}

$exe = Get-ChildItem -Path "$Root\dist" -Filter "*.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $exe) {
    throw "dist\*.exe 없음. 먼저 build_exe.ps1 을 실행하세요."
}
Write-Host "    exe: $($exe.FullName)  ($([math]::Round($exe.Length/1MB,1)) MB)"

# 2) Inno Setup
Write-Host "==> 2/2  Inno Setup 설치 프로그램" -ForegroundColor Cyan
$iscc = Find-ISCC
if (-not $iscc) {
    Write-Host "Inno Setup 이 없습니다. winget 으로 설치를 시도합니다..." -ForegroundColor Yellow
    winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
    $iscc = Find-ISCC
}
if (-not $iscc) {
    throw @"
ISCC.exe 를 찾을 수 없습니다.
1) https://jrsoftware.org/isinfo.php 에서 Inno Setup 6 설치
2) 또는: winget install JRSoftware.InnoSetup
3) 다시: powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipExe
"@
}

$iss = Join-Path $Root "installer\롤실전코치.iss"
if (-not (Test-Path $iss)) {
    # UTF-8 파일명 이슈 시 영문 이름 폴백
    $iss = Get-ChildItem "$Root\installer" -Filter "*.iss" | Select-Object -First 1 -ExpandProperty FullName
}
Write-Host "    ISCC: $iscc"
Write-Host "    script: $iss"

& $iscc $iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 컴파일 실패 (exit $LASTEXITCODE)" }

$outDir = Join-Path $Root "installer_output"
$setup = Get-ChildItem -Path $outDir -Filter "*Setup*.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

Write-Host ""
if ($setup) {
    $mb = [math]::Round($setup.Length / 1MB, 1)
    Write-Host "설치 프로그램 완료: $($setup.FullName)  ($mb MB)" -ForegroundColor Green
    Write-Host "이 파일만 배포하면 됩니다."
} else {
    Write-Host "installer_output 폴더를 확인하세요: $outDir" -ForegroundColor Yellow
}
