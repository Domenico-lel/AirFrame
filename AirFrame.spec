# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)
from PyInstaller.utils.hooks import collect_all
winrt_datas, winrt_binaries, winrt_imports = collect_all('winrt')
a = Analysis([str(project/'app.py')], pathex=[str(project)], binaries=[],
    datas=[], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False, optimize=0)
# Qt 6.12 uses Windows' native ICU API. The build host also has a Poppler
# ICU with the same DLL name but version-suffixed symbols. Never bundle it.
a.binaries = [entry for entry in a.binaries
    if Path(entry[0]).name.lower() != 'icuuc.dll'
    and not Path(entry[0]).name.lower().startswith('icudt')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AirFrame',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)
mouse = Analysis([str(project/'bluetooth_mouse.py')], pathex=[str(project)],
    binaries=winrt_binaries, datas=winrt_datas, hiddenimports=winrt_imports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
mouse_exe = EXE(PYZ(mouse.pure), mouse.scripts, [], exclude_binaries=True,
    name='AirFrameMouse', debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe,mouse_exe,a.binaries,mouse.binaries,a.datas,mouse.datas,
    strip=False,upx=False,name='AirFrame')
