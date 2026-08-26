"""Local notification adapters and delivery orchestration."""

from .manager import DeliveryResult, NotificationManager
from .windows import NotificationRequest, NotificationResult, WindowsNotificationAdapter

__all__ = [
    "DeliveryResult",
    "NotificationManager",
    "NotificationRequest",
    "NotificationResult",
    "WindowsNotificationAdapter",
]
