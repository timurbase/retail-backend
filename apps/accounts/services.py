"""
Auth services — OTP generation, verification, and SMS dispatch.

Kept out of views.py so unit tests can target services directly without
spinning up DRF requests.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import OTPCode, User

log = logging.getLogger(__name__)


def _normalize_phone(raw: str) -> str:
    """+998 90 123 45 67 → +998901234567. Accepts 9-digit local form too."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 9:
        return f"+998{digits}"
    if len(digits) == 12 and digits.startswith("998"):
        return f"+{digits}"
    if raw.startswith("+") and len(digits) == 12:
        return f"+{digits}"
    raise ValueError("Telefon raqam noto'g'ri formatda")


def _generate_code() -> str:
    length = settings.OTP["LENGTH"]
    # secrets.randbelow keeps timing-attack safe
    n = secrets.randbelow(10**length)
    return str(n).zfill(length)


def _hit_rate_limit(phone: str) -> bool:
    window_start = timezone.now() - timedelta(hours=1)
    count = OTPCode.objects.filter(phone=phone, created_at__gte=window_start).count()
    return count >= settings.OTP["RATE_LIMIT_PER_HOUR"]


def request_otp(raw_phone: str, purpose: str, ip: str | None = None) -> dict:
    phone = _normalize_phone(raw_phone)

    if _hit_rate_limit(phone):
        return {"ok": False, "error": "rate_limited", "phone": phone}

    # Invalidate any open codes for this phone+purpose
    OTPCode.objects.filter(
        phone=phone, purpose=purpose, consumed_at__isnull=True
    ).update(consumed_at=timezone.now())

    code = _generate_code()
    otp = OTPCode(
        phone=phone,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(seconds=settings.OTP["TTL_SECONDS"]),
        requester_ip=ip,
    )
    otp.set_code(code)
    otp.save()

    _send_sms(phone, code, purpose)
    return {"ok": True, "phone": phone, "ttl": settings.OTP["TTL_SECONDS"]}


class OtpResult:
    """Discriminated outcome of verify_otp so views can distinguish
    'no such user' (login) from 'no such code' from 'wrong code'."""

    __slots__ = ("user", "error")

    def __init__(self, user: User | None = None, error: str | None = None):
        self.user = user
        self.error = error


def verify_otp(raw_phone: str, code: str, purpose: str) -> OtpResult:
    """Verify SMS code and resolve a User.

    Behaviour per purpose:
      - login:    user MUST already exist; otherwise OtpResult(error='no_user').
      - register: user is created if missing (caller will attach memberships).
      - reset:    user MUST already exist.
    """
    phone = _normalize_phone(raw_phone)

    otp = (
        OTPCode.objects.filter(
            phone=phone,
            purpose=purpose,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        return OtpResult(error="invalid")

    otp.attempts += 1
    if otp.attempts > settings.OTP["MAX_ATTEMPTS"]:
        otp.consumed_at = timezone.now()
        otp.save(update_fields=("attempts", "consumed_at"))
        return OtpResult(error="too_many_attempts")

    if not otp.check_code(code):
        otp.save(update_fields=("attempts",))
        return OtpResult(error="invalid")

    otp.consumed_at = timezone.now()
    otp.save(update_fields=("attempts", "consumed_at"))

    user = _resolve_user(phone, purpose)
    if user is None:
        # Login/reset on a phone that was never registered. Don't auto-
        # create — that would let anyone with an SMS intercept claim a
        # phone number with zero accountability.
        return OtpResult(error="no_user")

    user.last_login = timezone.now()
    user.save(update_fields=("last_login",))
    return OtpResult(user=user)


def _resolve_user(phone: str, purpose: str) -> User | None:
    if purpose == "register":
        user, _ = User.objects.get_or_create(phone=phone)
        return user
    # login / reset: user must already exist
    return User.objects.filter(phone=phone).first()


def _send_sms(phone: str, code: str, purpose: str) -> None:
    provider = settings.SMS["PROVIDER"]
    text = f"RetailFlow tasdiqlash kodi: {code}"

    if provider == "console":
        log.warning("[SMS:console] → %s | %s | %s", phone, purpose, text)
        return

    # TODO: wire Eskiz.uz here in production. Stubbed to avoid silent dispatch.
    log.error("SMS provider %r is not implemented yet. Phone=%s", provider, phone)


def update_membership_last_seen(user: User, store_id) -> None:
    from .models import Membership

    Membership.objects.filter(user=user, store_id=store_id).update(
        last_seen_at=timezone.now()
    )


def memberships_for(user: User, portal: str | None = None):
    from .models import Membership

    qs = Membership.objects.select_related("store", "store__company").filter(
        Q(user=user) & ~Q(status="blocked")
    )
    if portal:
        qs = qs.filter(portal=portal)
    return qs
