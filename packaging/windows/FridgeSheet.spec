# packaging/windows/FridgeSheet.spec
# -*- mode: python ; coding: utf-8 -*-
"""One-folder, windowed bundle of fridgesheet/web/__main__.py.

Run from the repo root: pyinstaller --noconfirm --clean packaging/windows/FridgeSheet.spec
Chromium (ms-playwright/) and SumatraPDF.exe are copied in afterwards by build.ps1; the
code finds them next to the exe (frozen_environment, sumatra_path).
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = [(os.path.join(ROOT, "fridgesheet", "host", "logon-task.xml"), os.path.join("fridgesheet", "host"))]
# web/app.py resolves its templates and assets by Path(__file__).parent, which in a
# one-folder bundle is _internal/fridgesheet/web/; these destinations put them there.
datas += [(os.path.join(ROOT, "fridgesheet", "web", "templates"), os.path.join("fridgesheet", "web", "templates"))]
datas += [(os.path.join(ROOT, "fridgesheet", "web", "static"), os.path.join("fridgesheet", "web", "static"))]
datas += collect_data_files("tzdata")                 # Windows has no system zoneinfo
datas += copy_metadata("fridgesheet")          # importlib.metadata.version() for the About box
datas += copy_metadata("keyring")                    # keyring discovers backends through entry points

hiddenimports = [
    "keyring.backends.Windows",
    "win32ctypes.core", "win32ctypes.pywin32",       # keyring's Windows backend
    "win32timezone",                                 # pywin32 needs it at runtime
]
hiddenimports += collect_submodules("tzdata")        # zoneinfo imports tzdata.zoneinfo.America etc. as modules
# The part 1 spike (docs/superpowers/plans/2026-09-15-web-b-server-core.md, "Task 1 outcome")
# proved this exact list makes FastAPI, uvicorn and Jinja2 serve from a frozen bundle.
hiddenimports += collect_submodules("uvicorn") + ["fastapi", "jinja2", "multipart", "anyio._backends._asyncio"]

a = Analysis(
    [os.path.join(ROOT, "fridgesheet", "web", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["mcp"],                                # the MCP server is not part of the Windows product
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FridgeSheet",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(SPECPATH, "FridgeSheet.ico"),    # rendered from web/static/mark.svg by scripts/render_mark.py
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FridgeSheet")
