"""
Shared validators reused across apps.

STIR (Soliq To'lovchi Identifikatsiya Raqami):
  9 digits → legal entity (MChJ / OOO / AJ)
  14 digits → individual entrepreneur (YaT) — includes JShShIR-style suffix.
"""

import re

from django.core.exceptions import ValidationError

STIR_RE = re.compile(r"^\d{9}$|^\d{14}$")


def validate_stir(value: str) -> None:
    if not value or not STIR_RE.match(value):
        raise ValidationError(
            "STIR aniq 9 (MChJ) yoki 14 (YaT) raqamdan iborat bo'lishi kerak."
        )


def normalize_stir(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    validate_stir(digits)
    return digits
