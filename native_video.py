"""Embed the receiver's own native window; never subclass a foreign-process HWND."""
import ctypes
from ctypes import wintypes


class NativeVideo:
    def __init__(self, parent, pid, log):
        self.parent = parent
        self.pid = pid
        self.log = log
        self.hwnd = 0
        self.user = ctypes.WinDLL('user32',use_last_error=True)
        self.user.IsWindow.argtypes=[wintypes.HWND];self.user.IsWindow.restype=wintypes.BOOL
        self.user.IsWindowVisible.argtypes=[wintypes.HWND];self.user.IsWindowVisible.restype=wintypes.BOOL
        self.user.GetParent.argtypes=[wintypes.HWND];self.user.GetParent.restype=wintypes.HWND
        self.user.SetParent.argtypes=[wintypes.HWND,wintypes.HWND];self.user.SetParent.restype=wintypes.HWND
        self.user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        self.user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
        self.user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user.MoveWindow.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.BOOL]
        self.user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
        self.user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        self.user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
        self.callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        self.user.EnumWindows.argtypes=[self.callback_type,wintypes.LPARAM]

    def update(self):
        pid = self.pid()
        if not pid: return
        if self.hwnd and not self.user.IsWindow(self.hwnd): self.hwnd=0
        if not self.hwnd:
            candidates=[]
            @self.callback_type
            def visit(hwnd,param):
                found=wintypes.DWORD();self.user.GetWindowThreadProcessId(hwnd,ctypes.byref(found))
                if found.value==pid and self.user.IsWindowVisible(hwnd):
                    name=ctypes.create_unicode_buffer(256);self.user.GetClassNameW(hwnd,name,256)
                    if 'd3d' in name.value.lower() or 'gst' in name.value.lower():
                        candidates.append((hwnd,name.value))
                return True
            self.user.EnumWindows(visit,0)
            if not candidates: return
            self.hwnd,kind=candidates[0]
            self.log('Embedding video window: '+kind)
        parent=int(self.parent.winId())
        if self.user.GetParent(self.hwnd)!=parent:
            # WS_POPUP/CAPTION/THICKFRAME off, WS_CHILD on. SetParent is a supported
            # cross-process operation; the renderer keeps its own window procedure.
            style=self.user.GetWindowLongPtrW(self.hwnd,-16)
            style=(style & ~0x80C40000) | 0x44000000
            self.user.SetWindowLongPtrW(self.hwnd,-16,style)
            ctypes.set_last_error(0)
            result=self.user.SetParent(self.hwnd,parent)
            error=ctypes.get_last_error()
            if not result and error:
                self.log('Video embedding failed: '+str(error));self.hwnd=0;return
        self.user.MoveWindow(self.hwnd,0,0,self.parent.width(),self.parent.height(),True)
        self.user.ShowWindow(self.hwnd,5)

    def overlay(self, widget):
        if widget.isVisible():
            # QWidget.raise_ can be a no-op when Qt's sibling order is unchanged,
            # even though a foreign child has just been attached above it.
            self.user.SetWindowPos(int(widget.winId()),0,0,0,0,0,0x0013)
