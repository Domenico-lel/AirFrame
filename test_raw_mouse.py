"""Packet ABI/decoder and sensitivity tests. No input or Bluetooth is sent."""
import ctypes
import struct
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from mouse_overlay import MouseOverlay
from raw_mouse import RawInputDevice, RawInputHeader, RawMouse, decode_motion

def packet(dx=0, dy=0, *, flags=0, kind=0, declared_size=48):
    # Literal Win64 wire layout, independently constructed from ctypes classes.
    return struct.pack('<IIQQH2xHHIiiI', kind, declared_size, 0, 0,
                       flags, 0, 0, 0, dx, dy, 0)

class DecoderTests(unittest.TestCase):
    def test_windows_x64_abi(self):
        self.assertEqual(ctypes.sizeof(ctypes.c_void_p), 8)
        self.assertEqual(ctypes.sizeof(RawInputDevice), 16)
        self.assertEqual(ctypes.sizeof(RawInputHeader), 24)
        self.assertEqual(ctypes.sizeof(RawMouse), 24)
        self.assertEqual(RawMouse.buttons.offset, 4)
        self.assertEqual(RawMouse.dx.offset, 12)
        self.assertEqual(RawMouse.dy.offset, 16)

    def test_signed_relative_motion_and_no_coalesce_flag(self):
        self.assertEqual(decode_motion(packet(-2147483648, 2147483647)),
                         (-2147483648, 2147483647))
        self.assertEqual(decode_motion(packet(-31, 17, flags=8)), (-31, 17))
        self.assertEqual(decode_motion(packet()), (0, 0))

    def test_absolute_nonmouse_and_short_packets_rejected(self):
        self.assertIsNone(decode_motion(packet(1, 2, flags=1)))
        self.assertIsNone(decode_motion(packet(1, 2, kind=1)))
        self.assertIsNone(decode_motion(packet()[:-1]))
        self.assertIsNone(decode_motion(packet(declared_size=49)))

    def test_undersized_declared_header_rejected(self):
        self.assertIsNone(decode_motion(packet(10, 20, declared_size=24)))

class SensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.canvas = QWidget()
        self.overlay = MouseOverlay(self.canvas)
        self.events = []
        self.overlay.movement.connect(lambda x, y: self.events.append((x, y)))

    def tearDown(self):
        self.overlay.release_capture('unit test')
        self.canvas.close()

    def test_fractional_carry_preserves_small_signed_motion(self):
        self.overlay.set_sensitivity(.25)
        with patch.object(QApplication, 'keyboardModifiers', return_value=Qt.KeyboardModifier.NoModifier):
            for _ in range(4):
                self.overlay._motion(1, -1)
        self.assertEqual(self.events, [(1, -1)])
        self.assertEqual(self.overlay._remainder, [0., 0.])

    def test_shift_quarter_precision_and_reset(self):
        self.overlay.set_sensitivity(2.)
        with patch.object(QApplication, 'keyboardModifiers', return_value=Qt.KeyboardModifier.ShiftModifier):
            for _ in range(4):
                self.overlay._motion(1, -1)
        self.assertEqual(self.events, [(1, -1), (1, -1)])
        self.overlay._remainder = [.5, -.5]
        self.overlay.set_sensitivity(1.)
        self.assertEqual(self.overlay._remainder, [0., 0.])
        self.overlay._remainder = [.5, -.5]
        self.overlay.release_capture('test')
        self.assertEqual(self.overlay._remainder, [0., 0.])

    def test_sensitivity_bounds(self):
        self.overlay.set_sensitivity(100)
        self.assertEqual(self.overlay.sensitivity, 3.)
        self.overlay.set_sensitivity(-100)
        self.assertEqual(self.overlay.sensitivity, .25)

if __name__ == '__main__':
    unittest.main(verbosity=2)
