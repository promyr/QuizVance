from datetime import datetime, timedelta, date
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from . import models


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


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


def activate_premium(db: Session, user_id: int, plan_code: str):
    days = 15 if plan_code == "premium_15" else 30 if plan_code == "premium_30" else 0
    if days <= 0:
        return False, "Plano invalido."
    row = ensure_plan_row(db, user_id)
    base = row.premium_until if row.premium_until and row.premium_until > datetime.utcnow() else datetime.utcnow()
    row.plan_code = plan_code
    row.premium_until = base + timedelta(days=days)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return True, "Plano ativado."


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
