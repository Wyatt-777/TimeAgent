"""Deliver Inbox alerts through policy, cooldown, and a local adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from alerts.model import Alert
from alerts.service import AlertService

from .windows import NotificationRequest, NotificationResult, WindowsNotificationAdapter


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    alert_id: str
    sent: bool
    reason: str
    notification: NotificationResult | None = None


class NotificationManager:
    """Send an alert only when the AlertService policy permits it."""

    def __init__(
        self,
        alert_service: AlertService,
        *,
        adapter: WindowsNotificationAdapter | None = None,
    ) -> None:
        self.alert_service = alert_service
        self.adapter = adapter or WindowsNotificationAdapter()

    def deliver(self, alert: Alert, *, now: datetime | None = None) -> DeliveryResult:
        if not isinstance(alert, Alert):
            raise TypeError("alert must be an Alert")
        now = now or datetime.now(timezone.utc)
        if not self.alert_service.should_notify(alert, now=now):
            return DeliveryResult(alert.id, False, "suppressed_by_policy_or_cooldown")

        notification = self.adapter.send(
            NotificationRequest(title=alert.title, message=alert.summary)
        )
        if not notification.delivered:
            return DeliveryResult(alert.id, False, "notification_failed", notification)
        self.alert_service.mark_notified(alert, now=now)
        return DeliveryResult(alert.id, True, "sent", notification)
