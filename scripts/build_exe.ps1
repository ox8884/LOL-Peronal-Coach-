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

$dist = Join-Path $Root "dist"
$exe = Get-ChildItem -Path $dist -Filter "*.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($exe) {
    $mb = [math]::Round($exe.Length / 1MB, 1)
    Write-Host ""
    Write-Host "빌드 완료: $($exe.FullName)  ($mb MB)" -ForegroundColor Green
    Write-Host "실행 시 exe 옆에 .env 가 생성됩니다 (API 키 저장)."
    Write-Host "아이콘 캐시: exe 옆 cache\icons\ 에 런타임 저장 (용량 가벼움 유지)."
} else {
    Write-Host "빌드 실패 — dist 폴더를 확인하세요." -ForegroundColor Red
    exit 1
}
