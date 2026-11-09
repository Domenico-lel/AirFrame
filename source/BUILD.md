# Rebuild the Windows prototype

## Desktop shell

From the AirFrame project folder with Python 3.11 x64:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

For logic checks:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python -m unittest test_core -v
Remove-Item Env:QT_QPA_PLATFORM
```

For a distributable shell:

```powershell
.venv\Scripts\python -m PyInstaller --noconfirm AirFrame.spec
```

The spec builds windowed `AirFrame.exe` and console helper `AirFrameMouse.exe` into the same distribution with shared `_internal` dependencies. The UI starts the helper hidden using JSON-lines IPC; keep both executables together. `requirements.txt` is the dependency source of truth: PyWinRT runtime 4.1.0 and Windows namespace packages pinned with the `4!10.0.28000.2957` epoch/version. The mouse helper uses Windows GATT server APIs and requires an adapter supporting the BLE peripheral role; installing dependencies cannot add this hardware capability.

Copy engine, Configura-rete.ps1, LEGGIMI.md, LICENSE and third-party notices next to the generated executable. Keep _internal intact. Do not distribute the executable by itself.

The spec deliberately excludes unrelated `icuuc.dll` / ICU data binaries that PyInstaller may discover on the build host PATH (for example through Poppler). Qt in this build uses the native Windows ICU API; accidentally bundling a third-party ICU of the same name causes a missing-procedure error when importing QtCore. Do not replace the spec with the default generated one without repeating the packaged startup check.

## Receiver

Use an MSYS2 UCRT64 environment on Windows x64. Install:

```sh
pacman -S --needed mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-libplist mingw-w64-ucrt-x86_64-gstreamer mingw-w64-ucrt-x86_64-gst-plugins-base mingw-w64-ucrt-x86_64-gst-plugins-good mingw-w64-ucrt-x86_64-gst-plugins-bad mingw-w64-ucrt-x86_64-gst-libav
cmake -S source/UxPlay -B build -G Ninja -DNO_MARCH_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

Stage the binary and shared-library closure from PowerShell, with paths adjusted to your MSYS2 install:

```powershell
.venv\Scripts\python -m pip install pefile
.venv\Scripts\python source\stage_engine.py --prefix C:\msys64\ucrt64 --receiver build\uxplay.exe --destination engine
```

The receiver supplies machine-readable `@AF` events on stdout when AIRFRAME_WINDOW is set. This variable enables integration metadata; it no longer passes a foreign HWND into GStreamer. The shell reparents the renderer-owned native window using SetParent, preserving the receiver's own window procedure. This avoids cross-process subclassing failures. The integration is currently Windows-specific. macOS needs a separate native video embedding implementation and has not been tested.

The basic pipeline has been tested with local synthetic video. The user confirmed real iPhone screen reception. Audio synchronization, PIN/model/rotation details and lock/unlock behavior still require hardware validation. The optional AssistiveTouch BLE mouse is experimental. Pairing and input have been confirmed on a real iPhone, but latency and precision were reported as poor; the latest pacing/Raw Input update still needs device validation. No simulated device is reported as a real connection.
