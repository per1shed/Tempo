from __future__ import annotations


def notifications_enabled(settings) -> bool:
    """Единый контроль пушей (учитывает старый quiet_mode)."""
    return bool(settings.pushes_enabled) and not bool(settings.quiet_mode)


def set_notifications(settings, enabled: bool) -> None:
    settings.pushes_enabled = bool(enabled)
    settings.quiet_mode = False


def normalize_notification_flags(settings) -> None:
    if settings.quiet_mode:
        settings.pushes_enabled = False
        settings.quiet_mode = False
