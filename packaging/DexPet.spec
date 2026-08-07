# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DexPet macOS .app"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent
ENTRY = str(ROOT / "dexpet_app.py")
HOOKS = str(ROOT / "packaging" / "hooks")

datas = []
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "backend",
    "backend.main",
    "backend.app",
    "backend.api.http",
    "backend.api.ws",
    "backend.core.conversation",
    "backend.core.emotion",
    "backend.core.tools",
    "backend.core.config_service",
    "backend.core.secrets",
    "backend.core.llm.openai_compatible",
    "backend.core.pet_display",
    "backend.plugins.reminder",
    "backend.db.repository",
    "backend.db.schema",
    "desktop",
    "desktop.main",
    "desktop.window",
    "desktop.ws_client",
    "desktop.sprite_animator",
    "desktop.pet_factory",
    "desktop.live2d_widget",
    "desktop.live2d_runtime",
    "shared.messages",
    "shared.live2d_config",
    "keyring.backends",
    "keyring.backends.macOS",
    "live2d",
    "live2d.v3",
    "live2d.v3.lapp_model",
    "live2d.v3.params",
]

for pkg in ("uvicorn", "fastapi", "live2d"):
    try:
        tmp_ret = collect_all(pkg)
    except Exception:
        # live2d is optional; skip if not installed in the build env
        if pkg == "live2d":
            continue
        raise
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

hiddenimports += collect_submodules("apscheduler")

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[HOOKS] if Path(HOOKS).is_dir() else [],
    hooksconfig={},
    runtime_hooks=[str(Path(HOOKS) / "rthook_live2d.py")]
    if (Path(HOOKS) / "rthook_live2d.py").is_file()
    else [],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DexPet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DexPet",
)

ICON = ROOT / "desktop" / "assets" / "AppIcon.icns"

app = BUNDLE(
    coll,
    name="DexPet.app",
    icon=str(ICON) if ICON.is_file() else None,
    bundle_identifier="com.dexpet.app",
    info_plist={
        "CFBundleName": "DexPet",
        "CFBundleDisplayName": "DexPet",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
        "NSAppleEventsUsageDescription": "DexPet needs AppleEvents for reminder notifications.",
    },
)
