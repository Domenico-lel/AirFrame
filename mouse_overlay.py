"""Opt-in relative mouse capture above a foreign native video child.

Create MouseOverlay(canvas.video), connect its signals to the HID worker, and
call set_connected with the HID connection state (not merely AirPlay state).
An explicit toolbar action calls start_capture. Escape returns local control.
Call restack AFTER NativeVideo.update()/overlay(island) on each video refresh.
No iPhone unlock or BLE connection is performed here.
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from raw_mouse import RawMouseInput


class MouseOverlay(QWidget):
    movement = Signal(int, int)
    buttons = Signal(int)
    wheel = Signal(int)
    capture_changed = Signal(bool)
    capture_lost = Signal(str)

    def __init__(self, video_widget):
        super().__init__(video_widget)
        self.connected = False
        self.active = False
        self._mask = 0
        self._wheel_remainder = 0
        self._restore_cursor = None
        self._layered = False
        self.raw_input = RawMouseInput()
        self.sensitivity = 1.0
        self._remainder = [0., 0.]
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName('Controllo mouse iPhone; Escape per uscire')
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._user = ctypes.WinDLL('user32', use_last_error=True)
        self._user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self._user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self._user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self._user.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
        self._user.SetLayeredWindowAttributes.restype = wintypes.BOOL
        self._user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        video_widget.installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.release_capture)
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(100)
        self._watchdog.timeout.connect(self._check_focus)
        self.hide()

    def set_connected(self, connected):
        """Root must pass HID subscribers == 1 AND an active video stream."""
        self.connected = bool(connected)
        if not self.connected:
            self.release_capture('disconnect')

    def start_capture(self):
        """Call from a deliberate toolbar action after its mouse release."""
        if self.active:
            return True
        if (not self.connected or not self.parentWidget().isVisible()
                or QApplication.mouseButtons() != Qt.MouseButton.NoButton):
            return False
        self.setGeometry(self.parentWidget().rect())
        self._restore_cursor = QCursor.pos()
        self.show()
        hwnd = int(self.winId())
        # Nonzero alpha retains hit testing; WS_EX_TRANSPARENT must NOT be set.
        exstyle = self._user.GetWindowLongPtrW(hwnd, -20)
        self._user.SetWindowLongPtrW(hwnd, -20, (exstyle | 0x80000) & ~0x20)
        self._layered = bool(self._user.SetLayeredWindowAttributes(hwnd, 0, 1, 2))
        if not self._layered:
            self.hide()
            return False
        self.active = True
        self._remainder = [0., 0.]
        self.raw_input.start(hwnd)
        QApplication.instance().installEventFilter(self)
        self._mask = 0
        self._wheel_remainder = 0
        self.restack()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.grabMouse()
        QCursor.setPos(self._center())
        self.buttons.emit(0)
        self._watchdog.start()
        self.capture_changed.emit(True)
        return True

    def release_capture(self, reason=''):
        """Idempotent; always release remote buttons before local capture."""
        was_active = self.active
        self.active = False
        self.raw_input.stop()
        self._remainder = [0., 0.]
        if was_active:
            QApplication.instance().removeEventFilter(self)
        self._mask = 0
        self._wheel_remainder = 0
        self.buttons.emit(0)
        self._watchdog.stop()
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self.hide()
        if was_active and self._restore_cursor is not None:
            QCursor.setPos(self._restore_cursor)
        self._restore_cursor = None
        if was_active:
            self.capture_changed.emit(False)
            self.capture_lost.emit(reason or 'released')

    def restack(self):
        if self.active:
            self.setGeometry(self.parentWidget().rect())
            self._user.SetWindowPos(int(self.winId()), 0, 0, 0, 0, 0, 0x0013)

    def _center(self):
        return self.mapToGlobal(self.rect().center())

    def _check_focus(self):
        if self.active and (not self.window().isActiveWindow()
                            or not self.hasFocus() or not self.isVisible()):
            self.release_capture('focus lost')

    def eventFilter(self, watched, event):
        kind = event.type()
        if self.active and kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.release_capture('escape')
            return True
        if self.active and kind in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            self.release_capture('deactivated')
        if watched is self.parentWidget():
            if kind == QEvent.Type.Resize:
                self.setGeometry(self.parentWidget().rect())
            elif kind in (QEvent.Type.Hide, QEvent.Type.Close):
                self.release_capture('hidden')
        return False

    def focusOutEvent(self, event):
        self.release_capture('focus lost')
        super().focusOutEvent(event)

    def paintEvent(self, event):
        # At alpha 1/255 this keeps the D3D stream visible without relying on
        # Qt's backing store to composite a foreign-process sibling window.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

    def set_sensitivity(self, value):
        self.sensitivity = max(.25, min(3., float(value)))
        self._remainder = [0., 0.]

    def _motion(self, dx, dy):
        gain = self.sensitivity
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            gain *= .25
        values = [dx*gain+self._remainder[0], dy*gain+self._remainder[1]]
        result = [int(value) for value in values]
        self._remainder = [value-whole for value, whole in zip(values, result)]
        if any(result):
            self.movement.emit(*result)

    def nativeEvent(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x00FF and self.active and self.raw_input.active:  # WM_INPUT
            try:
                motion = self.raw_input.motion(msg.lParam)
                if motion is None:
                    # Absolute devices (e.g. remote desktop) retain Qt fallback.
                    self.raw_input.stop()
                elif motion != (0, 0):
                    self._motion(*motion)
            except (OSError, ValueError):
                self.raw_input.stop()
        # Default processing owns WM_INPUT cleanup. Never swallow the message.
        return False, 0

    def mouseMoveEvent(self, event):
        if self.active:
            delta = event.globalPosition().toPoint() - self._center()
            if not delta.isNull():
                if not self.raw_input.active:
                    self._motion(delta.x(), delta.y())
                QCursor.setPos(self._center())
        event.accept()

    @staticmethod
    def _button_mask(buttons):
        result = 0
        for button, bit in ((Qt.MouseButton.LeftButton, 1),
                            (Qt.MouseButton.RightButton, 2),
                            (Qt.MouseButton.MiddleButton, 4)):
            if buttons & button:
                result |= bit
        return result

    def _send_buttons(self, event):
        if self.active:
            mask = self._button_mask(event.buttons())
            if mask != self._mask:
                self._mask = mask
                self.buttons.emit(mask)
        event.accept()

    def mousePressEvent(self, event):
        self._send_buttons(event)

    def mouseReleaseEvent(self, event):
        self._send_buttons(event)

    def mouseDoubleClickEvent(self, event):
        self._send_buttons(event)

    def wheelEvent(self, event):
        if self.active:
            self._wheel_remainder += event.angleDelta().y()
            detents = int(self._wheel_remainder / 120)
            if detents:
                self._wheel_remainder -= detents * 120
                self.wheel.emit(detents)
        event.accept()
