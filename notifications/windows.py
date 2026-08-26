"""Windows local notification adapter with an injectable backend for tests."""

from __future__ import annotations

import sys
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
        try:
            import win32con
            import win32gui
        except ImportError as exc:
            raise NotificationError("pywin32 is required for Windows notifications") from exc

        hwnd = win32gui.GetDesktopWindow()
        icon = win32gui.LoadIcon(None, win32con.IDI_APPLICATION)
        callback = win32con.WM_USER + 20
        base_flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        notify_id = (hwnd, 0, base_flags, callback, icon, self.app_name)
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, notify_id)
        try:
            info_flags = getattr(win32gui, "NIIF_INFO", 1)
            balloon_flags = base_flags | win32gui.NIF_INFO
            balloon = (
                hwnd,
                0,
                balloon_flags,
                callback,
                icon,
                self.app_name,
                0,
                0,
                request.message,
                5000,
                request.title,
                info_flags,
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, balloon)
        finally:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, notify_id)
