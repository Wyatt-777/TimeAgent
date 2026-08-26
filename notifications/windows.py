"""Windows local notification adapter with an injectable backend for tests."""

from __future__ import annotations

import sys
import ctypes
from dataclasses import dataclass
from typing import Callable


class NotificationError(RuntimeError):
    """Raised when a local notification cannot be delivered."""


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    title: str
    message: str

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.message.strip():
            raise ValueError("notification title and message must not be empty")


@dataclass(frozen=True, slots=True)
class NotificationResult:
    delivered: bool
    backend: str
    error: str | None = None


NotificationBackend = Callable[[NotificationRequest], None]


class WindowsNotificationAdapter:
    """Send a small local balloon notification through the Windows shell."""

    def __init__(
        self,
        *,
        app_name: str = "Local PC Agent",
        backend: NotificationBackend | None = None,
    ) -> None:
        if not app_name.strip():
            raise ValueError("app_name must not be empty")
        self.app_name = app_name
        self._backend = backend

    def send(self, request: NotificationRequest) -> NotificationResult:
        if not isinstance(request, NotificationRequest):
            raise TypeError("request must be a NotificationRequest")
        backend_name = "custom" if self._backend is not None else "win32_shell"
        try:
            if self._backend is not None:
                self._backend(request)
            else:
                self._send_win32(request)
        except Exception as exc:
            return NotificationResult(False, backend_name, f"{type(exc).__name__}: {exc}")
        return NotificationResult(True, backend_name)

    def _send_win32(self, request: NotificationRequest) -> None:
        if sys.platform != "win32":
            raise NotificationError("Windows notifications are only available on win32")
        from ctypes import wintypes

        class NotifyIconData(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeout", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON),
            ]

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        user32.GetDesktopWindow.restype = wintypes.HWND
        user32.LoadIconW.restype = wintypes.HICON
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NotifyIconData)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(NotifyIconData)
        data.hWnd = user32.GetDesktopWindow()
        data.uID = 1
        data.uCallbackMessage = 0x8000 + 20
        data.hIcon = user32.LoadIconW(None, ctypes.c_void_p(32512))
        data.szTip = self.app_name[:127]
        data.uFlags = 0x00000001 | 0x00000002 | 0x00000004
        if not shell32.Shell_NotifyIconW(0, ctypes.byref(data)):
            raise NotificationError("Shell_NotifyIconW(NIM_ADD) failed")
        try:
            data.uFlags |= 0x00000010
            data.szInfo = request.message[:255]
            data.uTimeout = 5000
            data.szInfoTitle = request.title[:63]
            data.dwInfoFlags = 0x00000001
            if not shell32.Shell_NotifyIconW(1, ctypes.byref(data)):
                raise NotificationError("Shell_NotifyIconW(NIM_MODIFY) failed")
        finally:
            shell32.Shell_NotifyIconW(2, ctypes.byref(data))
