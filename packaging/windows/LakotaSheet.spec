# packaging/windows/LakotaSheet.spec
# -*- mode: python ; coding: utf-8 -*-
"""One-folder, windowed bundle of lakota_grades/web/__main__.py.

Run from the repo root: pyinstaller --noconfirm --clean packaging/windows/LakotaSheet.spec
Chromium (ms-playwright/) and SumatraPDF.exe are copied in afterwards by build.ps1; the
code finds them next to the exe (frozen_environment, sumatra_path).
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = [(os.path.join(ROOT, "lakota_grades", "host", "task.xml"), os.path.join("lakota_grades", "host"))]
datas += [(os.path.join(ROOT, "lakota_grades", "host", "logon-task.xml"), os.path.join("lakota_grades", "host"))]
# web/app.py resolves its templates and assets by Path(__file__).parent, which in a
# one-folder bundle is _internal/lakota_grades/web/; these destinations put them there.
datas += [(os.path.join(ROOT, "lakota_grades", "web", "templates"), os.path.join("lakota_grades", "web", "templates"))]
datas += [(os.path.join(ROOT, "lakota_grades", "web", "static"), os.path.join("lakota_grades", "web", "static"))]
datas += collect_data_files("tzdata")                 # Windows has no system zoneinfo
datas += copy_metadata("lakota-grades-mcp")          # importlib.metadata.version() for the About box
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
    [os.path.join(ROOT, "lakota_grades", "web", "__main__.py")],
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
    name="LakotaSheet",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LakotaSheet")
