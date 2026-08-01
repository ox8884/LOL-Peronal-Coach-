# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: 롤 실전 코치 GUI (onefile + windowed)

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = [
    "bs4",
    "lxml",
    "lxml.etree",
    "lxml._elementpath",
    "certifi",
    "cloudscraper",
    "requests",
    "urllib3",
    "charset_normalizer",
    "idna",
    "dotenv",
    "customtkinter",
    "darkdetect",
    "packaging",
    "packaging.version",
    "packaging.specifiers",
    "packaging.requirements",
    # 함수 낮 import로 참조되는 신규 모듈 (정적 분석 보험)
    "lol_coach.lcu",
    "lol_coach.log",
    "lol_coach.gui.widget",
    "lol_coach.gui.tooltip",
    "lol_coach.gui.watcher",
    "lol_coach.analysis.pool",
    "lol_coach.analysis.export",
    "lol_coach.analysis.augment_screen",
]

# customtkinter / cloudscraper 전체 수집
for pkg in ("customtkinter", "cloudscraper", "certifi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 프로젝트 데이터 (있을 경우)
data_dir = ROOT / "data"
if data_dir.is_dir():
    datas.append((str(data_dir), "data"))

# Packaged catalog JSON
pkg_data = ROOT / "src" / "lol_coach" / "data"
if pkg_data.is_dir():
    datas.append((str(pkg_data), "lol_coach/data"))

icon_path = ROOT / "assets" / "icon.ico"
icon = str(icon_path) if icon_path.is_file() else None

a = Analysis(
    [str(ROOT / "gui_main.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "numpy", "pandas", "scipy", "mss"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="롤실전코치",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
