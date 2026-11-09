"""Windows relative mouse input, before desktop pointer acceleration.

Registered only while AirFrame captures its own mouse window. Keyboard and
legacy button events remain enabled. Cursor recentering creates no raw motion.
"""
import ctypes
from ctypes import wintypes


class RawInputDevice(ctypes.Structure):
    _fields_ = [('usage_page', wintypes.USHORT), ('usage', wintypes.USHORT),
                ('flags', wintypes.DWORD), ('target', wintypes.HWND)]


class RawInputHeader(ctypes.Structure):
    _fields_ = [('kind', wintypes.DWORD), ('size', wintypes.DWORD),
                ('device', wintypes.HANDLE), ('wparam', wintypes.WPARAM)]


class MouseButtons(ctypes.Structure):
    _fields_ = [('flags', wintypes.USHORT), ('data', wintypes.USHORT)]


class ButtonUnion(ctypes.Union):
    _fields_ = [('all', wintypes.ULONG), ('buttons', MouseButtons)]


class RawMouse(ctypes.Structure):
    _fields_ = [('flags', wintypes.USHORT), ('buttons', ButtonUnion),
                ('raw_buttons', wintypes.ULONG), ('dx', wintypes.LONG),
                ('dy', wintypes.LONG), ('extra', wintypes.ULONG)]


def decode_motion(packet):
    """Return relative motion only; absolute/remote-desktop input uses fallback."""
    header_size = ctypes.sizeof(RawInputHeader)
    if len(packet) < header_size + ctypes.sizeof(RawMouse):
        return None
    header = RawInputHeader.from_buffer_copy(packet)
    if header.kind != 0 or not header_size + ctypes.sizeof(RawMouse) <= header.size <= len(packet):
        return None
    mouse = RawMouse.from_buffer_copy(packet[header_size:])
    if mouse.flags & 1:  # MOUSE_MOVE_ABSOLUTE
        return None
    return mouse.dx, mouse.dy


class RawMouseInput:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RawInputDevice), wintypes.UINT, wintypes.UINT]
        self.user.RegisterRawInputDevices.restype = wintypes.BOOL
        self.user.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                              ctypes.POINTER(wintypes.UINT), wintypes.UINT]
        self.user.GetRawInputData.restype = wintypes.UINT
        self.active = False

    def start(self, hwnd):
        # No INPUTSINK/NOLEGACY: receive input only while this app is foreground,
        # and let Qt continue to handle click, wheel and Escape normally.
        device = RawInputDevice(1, 2, 0, hwnd)
        self.active = bool(self.user.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)))
        return self.active

    def stop(self):
        if self.active:
            device = RawInputDevice(1, 2, 1, None)  # RIDEV_REMOVE requires NULL target.
            self.user.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device))
        self.active = False

    def motion(self, handle):
        size = wintypes.UINT()
        header_size = ctypes.sizeof(RawInputHeader)
        failed = 0xFFFFFFFF
        if self.user.GetRawInputData(handle, 0x10000003, None, ctypes.byref(size), header_size) == failed:
            raise OSError(ctypes.get_last_error(), 'GetRawInputData size')
        if not header_size <= size.value <= 65536:
            raise ValueError('Invalid raw mouse packet size')
        data = ctypes.create_string_buffer(size.value)
        if self.user.GetRawInputData(handle, 0x10000003, data, ctypes.byref(size), header_size) == failed:
            raise OSError(ctypes.get_last_error(), 'GetRawInputData packet')
        return decode_motion(data.raw[:size.value])
