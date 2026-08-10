# 롤 실전 코치 — PyInstaller onefile 빌드
# 사용:  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 의존성 설치" -ForegroundColor Cyan
python -m pip install -q -r requirements.txt
python -m pip install -q pyinstaller pillow

Write-Host "==> 아이콘 생성" -ForegroundColor Cyan
python scripts\make_icon.py

Write-Host "==> PYTHONPATH=src 로 빌드" -ForegroundColor Cyan
$env:PYTHONPATH = "$Root\src"
python -m PyInstaller --noconfirm --clean lol_coach.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller 빌드 실패 (exit $LASTEXITCODE) — 옛 dist exe 로 성공 판단하지 않습니다." -ForegroundColor Red
    exit 1
}

$dist = Join-Path $Root "dist"
$exe = Get-ChildItem -Path $dist -Filter "*.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($exe) {
    $mb = [math]::Round($exe.Length / 1MB, 1)
    Write-Host ""
    Write-Host "빌드 완료: $($exe.FullName)  ($mb MB)" -ForegroundColor Green
    Write-Host "API 키와 설정: %LOCALAPPDATA%\롤실전코치 에 저장됩니다."
    Write-Host "아이콘 캐시: 같은 사용자 데이터 폴더의 cache\icons\ 에 저장됩니다."
} else {
    Write-Host "빌드 실패 — dist 폴더를 확인하세요." -ForegroundColor Red
    exit 1
}
