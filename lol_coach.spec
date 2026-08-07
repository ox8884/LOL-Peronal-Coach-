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
    # 함수 내 import로 참조되는 모듈 (정적 분석 보험)
    "lol_coach.lcu",
    "lol_coach.log",
    "lol_coach.llm",
    "lol_coach.gui.widget",
    "lol_coach.gui.tooltip",
    "lol_coach.gui.watcher",
    "lol_coach.gui.champ_autocomplete",
    "lol_coach.gui.api_help",
    "lol_coach.gui.setup_dialog",
    "lol_coach.analysis.review",
    "lol_coach.analysis.live_fill",
    "lol_coach.analysis.pool",
    "lol_coach.analysis.export",
    "lol_coach.gui.updater",
    "lol_coach.gui.ai_text",
    "lol_coach.gui.constants",
    "lol_coach.gui.update_mixin",
    "lol_coach.gui.ai_mixin",
    "lol_coach.gui.sr_tab",
    "lol_coach.gui.aram_tab",
    "lol_coach.gui.me_tab",
    "lol_coach.gui.live_mixin",
    "lol_coach.gui.notify_mixin",
    "lol_coach.gui.errors",
]

# customtkinter / cloudscraper 전체 수집
for pkg in ("customtkinter", "cloudscraper", "certifi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Packaged catalog JSON + GUI 테마

pkg_data = ROOT / "src" / "lol_coach" / "data"
if pkg_data.is_dir():
    datas.append((str(pkg_data), "lol_coach/data"))

theme_json = ROOT / "src" / "lol_coach" / "gui" / "theme.json"
if theme_json.is_file():
    datas.append((str(theme_json), "lol_coach/gui"))

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
    excludes=["pytest", "matplotlib", "numpy", "pandas", "scipy"],
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
