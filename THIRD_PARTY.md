# Third party components

AirFrame prototype source: GPL-3.0-or-later.

- UxPlay: https://github.com/FDH2/UxPlay — GPL-3.0-or-later. The exact modified source is included in source/UxPlay; see source/UPSTREAM.txt for the commit and modifications.
- GStreamer and selected plug-ins: https://gstreamer.freedesktop.org/ — individually licensed; see engine/licenses and package manifests. Shared libraries are bundled separately and may be replaced with compatible versions.
- PySide6 / Qt: https://www.qt.io/qt-for-python — LGPLv3/GPLv3/commercial; this GPLv3 prototype uses the open-source distribution. Qt/PySide license notices are preserved in the packaged runtime and licenses directory.
- PyWinRT / winrt-runtime and Windows namespace projections: https://github.com/pywinrt/pywinrt — Python bindings for Windows Runtime used by the optional BLE mouse helper. Exact runtime and namespace package versions are pinned in requirements.txt; preserve the bundled packages' license notices when distributing.
- Windows Bluetooth GATT API documentation and Microsoft BluetoothLEExplorer VirtualKeyboard example are implementation references, not evidence of iPhone interoperability. See references in bluetooth_mouse.py.
- PyInstaller bootloader: https://pyinstaller.org/ — GPL with bootloader exception.
- Device identifier factual mapping cross-checked against DeviceKit: https://github.com/devicekit/DeviceKit/blob/master/Source/Device.generated.swift . No DeviceKit implementation is bundled.

This project is not affiliated with Apple. AirPlay compatibility is supplied by UxPlay; it is not a claim of Apple certification. No DRM bypass is included.

## Rebuilding dependencies

MSYS2 package names and exact versions are in source/msys2-packages.txt. MSYS2 build recipes and source download locations: https://github.com/msys2/MINGW-packages . Use the recipe matching the packaged version and its checksums. This is a local development prototype, not a store release; a public release must complete the corresponding-source distribution audit for every bundled component.
