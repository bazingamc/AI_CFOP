# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cfop_analyzer_gui.py'],
    pathex=[],
    binaries=[('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\lib\\site-packages\\tkwebview\\platform\\win32\\x64\\webview.dll', 'tkwebview/platform/win32/x64')],
    datas=[],
    hiddenimports=['openai', 'httpx', 'http', 'h11', 'anyio', 'sniffio', 'certifi', 'idna', 'h2', 'hpack', 'hyperframe', 'hpack.struct', 'hpack.hpack', 'tkinter', 'tkinter.ttk', 'tkinter.scrolledtext', 'tkinter.messagebox', 'tkinter.filedialog', 'tkinter.font', 'tkwebview', 'tkwebview.core'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'cv2', 'opencv', 'tensorflow', 'torch', 'keras', 'selenium', 'pytest', 'IPython', 'jupyter', 'notebook', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'django', 'flask', 'fastapi', 'sqlalchemy', 'pymongo', 'redis', 'boto3', 'botocore', 'h5py', 'tables'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI_CFOP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['cube_ai_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI_CFOP',
)
