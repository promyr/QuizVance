from datetime import datetime, timedelta, date
import secrets
import uuid
import os
import base64
import hashlib
import hmac
from sqlalchemy.orm import Session
from . import models


PWD_SCHEME = "pbkdf2_sha256"
PWD_ITERS = 210_000
PLAN_DEFINITIONS = {
    "premium_30": {
        "price_cents": 1499,
        "duration_days": 30,
    },
}
PLAN_PRICES_CENTS = {k: int(v["price_cents"]) for k, v in PLAN_DEFINITIONS.items()}


def hash_password(raw: str) -> str:
    pwd = str(raw or "").encode("utf-8")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pwd, salt, PWD_ITERS)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    dig_b64 = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{PWD_SCHEME}${PWD_ITERS}${salt_b64}${dig_b64}"


def verify_password(raw: str, hashed: str) -> bool:
    value = str(hashed or "").strip()
    pwd = str(raw or "")
    if not value:
        return False
    if value.startswith(f"{PWD_SCHEME}$"):
        try:
            _scheme, iters_s, salt_b64, digest_b64 = value.split("$", 3)
            iters = int(iters_s)
            salt_raw = base64.urlsafe_b64decode(salt_b64 + "=" * (-len(salt_b64) % 4))
            digest_raw = base64.urlsafe_b64decode(digest_b64 + "=" * (-len(digest_b64) % 4))
            probe = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt_raw, max(50_000, iters))
            return hmac.compare_digest(probe, digest_raw)
        except Exception:
            return False

    # Compatibilidade com hashes bcrypt antigos.
    if value.startswith("$2"):
        try:
            from passlib.context import CryptContext  # import tardio para evitar erro de startup
            return CryptContext(schemes=["bcrypt"], deprecated="auto").verify(pwd, value)
        except Exception:
            return False

    return hmac.compare_digest(pwd, value)


def ensure_plan_row(db: Session, user_id: int):
    row = db.query(models.UserPlan).filter(models.UserPlan.user_id == user_id).first()
    if row:
        return row
    row = models.UserPlan(user_id=user_id, plan_code="free", trial_used=0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def grant_initial_trial(db: Session, user_id: int):
    row = ensure_plan_row(db, user_id)
    if int(row.trial_used or 0) == 0:
        row.trial_used = 1
        row.plan_code = "trial"
        row.trial_started_at = datetime.utcnow()
        row.premium_until = datetime.utcnow() + timedelta(days=1)
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return row


def premium_active(row: models.UserPlan | None) -> bool:
    if not row or not row.premium_until:
        return False
    return row.premium_until > datetime.utcnow()


def plan_duration_days(plan_code: str) -> int:
    plan = str(plan_code or "").strip().lower()
    conf = PLAN_DEFINITIONS.get(plan) or {}
    return int(conf.get("duration_days") or 0)


def activate_premium(db: Session, user_id: int, plan_code: str):
    plan = str(plan_code or "").strip().lower()
    days = plan_duration_days(plan)
    if days <= 0:
        return False, "Plano invalido."
    row = ensure_plan_row(db, user_id)
    base = row.premium_until if row.premium_until and row.premium_until > datetime.utcnow() else datetime.utcnow()
    row.plan_code = plan
    row.premium_until = base + timedelta(days=days)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return True, "Plano ativado."


def checkout_price(plan_code: str) -> int:
    return int(PLAN_PRICES_CENTS.get(str(plan_code or "").strip().lower()) or 0)


def create_checkout_session(db: Session, user_id: int, plan_code: str, provider: str = "manual"):
    plan = str(plan_code or "").strip().lower()
    amount = checkout_price(plan)
    if amount <= 0:
        return None, "Plano invalido."
    checkout_id = uuid.uuid4().hex
    auth_token = secrets.token_urlsafe(24)
    payment_code = f"QVP-{checkout_id[:8].upper()}"
    row = models.CheckoutSession(
        checkout_id=checkout_id,
        user_id=int(user_id),
        plan_code=plan,
        amount_cents=amount,
        currency="BRL",
        provider=str(provider or "manual"),
        auth_token=auth_token,
        payment_code=payment_code,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, "Checkout criado."


def confirm_checkout_session(
    db: Session,
    user_id: int,
    checkout_id: str,
    auth_token: str,
    tx_id: str,
    provider: str = "manual",
):
    row = (
        db.query(models.CheckoutSession)
        .filter(models.CheckoutSession.checkout_id == str(checkout_id or "").strip())
        .first()
    )
    if not row:
        return False, "Checkout nao encontrado.", None
    if int(row.user_id) != int(user_id):
        return False, "Checkout nao pertence ao usuario.", None
    if str(row.auth_token or "") != str(auth_token or ""):
        return False, "Token de checkout invalido.", None
    if str(row.status or "") != "pending":
        return False, "Checkout ja processado.", None
    if row.expires_at <= datetime.utcnow():
        row.status = "expired"
        db.commit()
        return False, "Checkout expirado. Inicie uma nova compra.", None
    tx_clean = str(tx_id or "").strip()
    if not tx_clean:
        return False, "Informe o ID da transacao.", None

    already_paid = (
        db.query(models.Payment)
        .filter(models.Payment.provider == str(provider or "manual"), models.Payment.provider_tx_id == tx_clean)
        .first()
    )
    if already_paid:
        return False, "Transacao ja utilizada.", None

    payment = models.Payment(
        user_id=int(user_id),
        provider=str(provider or "manual"),
        provider_tx_id=tx_clean,
        amount_cents=int(row.amount_cents or 0),
        currency=str(row.currency or "BRL"),
        plan_code=str(row.plan_code or "premium_30"),
        status="paid",
        paid_at=datetime.utcnow(),
    )
    db.add(payment)
    row.status = "confirmed"
    row.confirmed_at = datetime.utcnow()
    ok, msg = activate_premium(db, int(user_id), str(row.plan_code or "premium_30"))
    if not ok:
        db.rollback()
        return False, msg, None
    db.commit()
    return True, "Pagamento confirmado e premium liberado.", row


def finalize_checkout_payment(
    db: Session,
    checkout: models.CheckoutSession,
    *,
    provider: str,
    tx_id: str,
    amount_cents: int,
    currency: str = "BRL",
    plan_code: str = "",
):
    if not checkout:
        return False, "Checkout nao encontrado.", None
    tx_clean = str(tx_id or "").strip()
    if not tx_clean:
        return False, "Transacao sem identificador.", None
    provider_clean = str(provider or "manual").strip().lower() or "manual"
    amount = int(amount_cents or 0)
    if amount <= 0:
        amount = int(checkout.amount_cents or 0)
    curr = str(currency or "").strip().upper() or str(checkout.currency or "BRL")
    paid_plan = str(plan_code or checkout.plan_code or "premium_30").strip().lower()
    now = datetime.utcnow()

    payment = (
        db.query(models.Payment)
        .filter(models.Payment.provider == provider_clean, models.Payment.provider_tx_id == tx_clean)
        .first()
    )
    if not payment:
        payment = models.Payment(
            user_id=int(checkout.user_id),
            provider=provider_clean,
            provider_tx_id=tx_clean,
            amount_cents=amount,
            currency=curr,
            plan_code=paid_plan,
            status="paid",
            paid_at=now,
        )
        db.add(payment)

    checkout.status = "confirmed"
    checkout.confirmed_at = now
    ok, msg = activate_premium(db, int(checkout.user_id), str(checkout.plan_code or paid_plan))
    if not ok:
        db.rollback()
        return False, msg, payment
    db.commit()
    return True, "Pagamento confirmado e premium sincronizado.", payment


def consume_daily_limit(db: Session, user_id: int, feature_key: str, limit_per_day: int):
    if limit_per_day <= 0:
        return True, 0
    today = date.today()
    row = (
        db.query(models.UsageDaily)
        .filter(
            models.UsageDaily.user_id == user_id,
            models.UsageDaily.feature_key == feature_key,
            models.UsageDaily.day_key == today,
        )
        .first()
    )
    if not row:
        row = models.UsageDaily(user_id=user_id, feature_key=feature_key, day_key=today, used_count=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    if int(row.used_count or 0) >= int(limit_per_day):
        return False, int(row.used_count or 0)
    row.used_count = int(row.used_count or 0) + 1
    row.updated_at = datetime.utcnow()
    db.commit()
    return True, int(row.used_count or 0)
