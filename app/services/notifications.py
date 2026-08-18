from __future__ import annotations


def notifications_enabled(settings) -> bool:
    """Пуши всегда включены."""
    return True


def set_notifications(settings, enabled: bool) -> None:
    settings.pushes_enabled = True
    settings.quiet_mode = False


def normalize_notification_flags(settings) -> None:
    settings.pushes_enabled = True
    settings.quiet_mode = False
