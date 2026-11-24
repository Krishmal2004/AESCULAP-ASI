"""Mandatory disclaimer (docs/safety-policy.md section 9)."""

from __future__ import annotations

DISCLAIMER_MARKER = "not a substitute for professional medical judgment"


def emergency_phrase(locale: str | None) -> str:
    """'your local emergency number' or a concrete number like '911'."""
    return locale.strip() if locale and locale.strip() else "your local emergency number"


def disclaimer(locale: str | None = None) -> str:
    return (
        "*Aesculap provides decision support based on published evidence. It is "
        f"{DISCLAIMER_MARKER}, does not provide a final diagnosis or prescription, and must "
        "not be used in an emergency. If you may be experiencing a medical emergency, call "
        f"{emergency_phrase(locale)} immediately.*"
    )


def has_disclaimer(text: str) -> bool:
    return DISCLAIMER_MARKER in text.lower()


def ensure_disclaimer(text: str, locale: str | None = None) -> str:
    if has_disclaimer(text):
        return text
    return f"{text.rstrip()}\n\n{disclaimer(locale)}"
