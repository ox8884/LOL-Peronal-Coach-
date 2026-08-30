# 롤 실전 코치 — PyInstaller onedir 빌드 (실행마다 압축 해제 없음 — 기동 속도)
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
# onedir: dist\롤실전코치\ 롤실전코치.exe — 없으면 폴백으로 dist 루트 탐색
$appDir = Join-Path $dist "롤실전코치"
$exe = $null
if (Test-Path $appDir) {
    $exe = Get-ChildItem -Path $appDir -Filter "*.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}
if (-not $exe) {
    $exe = Get-ChildItem -Path $dist -Filter "*.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}
if ($exe) {
    $dirMb = 0.0
    if (Test-Path $appDir) {
        $dirMb = [math]::Round(((Get-ChildItem $appDir -Recurse | Measure-Object Length -Sum).Sum) / 1MB, 1)
    }
    Write-Host ""
    Write-Host "빌드 완료: $($exe.FullName)  (exe $([math]::Round($exe.Length / 1MB, 1)) MB / 폴더 $dirMb MB)" -ForegroundColor Green
    Write-Host "API 키와 설정: %LOCALAPPDATA%\롤실전코치 에 저장됩니다."
    Write-Host "아이콘 캐시: 같은 사용자 데이터 폴더의 cache\icons\ 에 저장됩니다."
} else {
    Write-Host "빌드 실패 — dist 폴더를 확인하세요." -ForegroundColor Red
    exit 1
}
