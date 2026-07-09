# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for TestGen Web App
Builds a single testgen.exe that starts the web server.
"""

import sys
from pathlib import Path

# Project root
ROOT = Path('.').resolve()

# Collect all testgen Python modules
testgen_pkg = ROOT / 'testgen'
python_files = []
for py_file in testgen_pkg.rglob('*.py'):
    python_files.append((str(py_file), str(py_file.parent.relative_to(ROOT))))

# Collect static web assets
static_dir = testgen_pkg / 'web' / 'static'
static_files = []
for f in static_dir.rglob('*'):
    if f.is_file():
        dest_dir = str(f.parent.relative_to(ROOT))
        static_files.append((str(f), dest_dir))

# Templates
templates_dir = ROOT / 'templates'
template_files = []
if templates_dir.exists():
    for f in templates_dir.rglob('*'):
        if f.is_file():
            template_files.append((str(f), str(f.parent.relative_to(ROOT))))

# Combine all data files
all_data = static_files + template_files

a = Analysis(
    ['testgen/web/gui.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=all_data,
    hiddenimports=[
        'testgen',
        'testgen.core',
        'testgen.core.models',
        'testgen.core.base',
        'testgen.parsers',
        'testgen.parsers.openapi_parser',
        'testgen.parsers.code_parser',
        'testgen.parsers.natural_lang_parser',
        'testgen.generators',
        'testgen.generators.generator',
        'testgen.generators.llm_client',
        'testgen.generators.prompt_builder',
        'testgen.generators.template_engine',
        'testgen.outputs',
        'testgen.outputs.pytest_adapter',
        'testgen.outputs.json_adapter',
        'testgen.outputs.excel_adapter',
        'testgen.orchestrator',
        'testgen.cli',
        'testgen.web',
        'testgen.web.server',
        'testgen.web.launcher',
        # Dependencies
        'click',
        'jinja2',
        'jinja2.ext',
        'yaml',
        'openpyxl',
        'openai',
        'fastapi',
        'uvicorn',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette',
        'anyio',
        'httpcore',
        'httpx',
        'multipart',
        'aiofiles',
        'docx',
        'pdfplumber',
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'numpy',
        'scipy',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TestGen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No CMD window for desktop app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Set to .ico path if you have an icon
)


















