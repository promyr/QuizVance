from datetime import datetime
import os
import json
from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from . import models, schemas, services


app = FastAPI(title="Quiz Vance Billing API", version="1.0.0")
Base.metadata.create_all(bind=engine)
APP_SECRET = os.getenv("APP_BACKEND_SECRET", "")


def _auth_out(db: Session, user: models.User) -> schemas.AuthOut:
    plan = services.ensure_plan_row(db, user.id)
    active = services.premium_active(plan)
    return schemas.AuthOut(
        user_id=user.id,
        name=user.name,
        email_id=user.email_id,
        plan_code=plan.plan_code,
        premium_active=active,
        premium_until=plan.premium_until,
    )


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


@app.post("/auth/register", response_model=schemas.AuthOut)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(models.User).filter(models.User.email_id == payload.email_id.strip().lower()).first()
    if exists:
        raise HTTPException(status_code=409, detail="ID ja cadastrado")
    user = models.User(
        name=payload.name.strip(),
        email_id=payload.email_id.strip().lower(),
        password_hash=services.hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    services.grant_initial_trial(db, user.id)
    return _auth_out(db, user)


@app.post("/auth/login", response_model=schemas.AuthOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email_id == payload.email_id.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    if not services.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    return _auth_out(db, user)


@app.get("/plans/me/{user_id}", response_model=schemas.AuthOut)
def my_plan(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    return _auth_out(db, user)


@app.post("/plans/activate")
def activate_plan(payload: schemas.ActivatePlanIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    ok, msg = services.activate_premium(db, payload.user_id, payload.plan_code)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg, "plan": _auth_out(db, user)}


@app.post("/usage/consume")
def consume_usage(payload: schemas.ConsumeUsageIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    ok, used = services.consume_daily_limit(db, payload.user_id, payload.feature_key, payload.limit_per_day)
    return {"allowed": ok, "used": used, "limit_per_day": payload.limit_per_day}


@app.post("/billing/webhook")
def billing_webhook(payload: schemas.WebhookPaymentIn, db: Session = Depends(get_db)):
    exists = db.query(models.WebhookEvent).filter(models.WebhookEvent.event_id == payload.event_id).first()
    if exists:
        return {"ok": True, "message": "evento ja processado"}

    event = models.WebhookEvent(
        provider=payload.provider,
        event_id=payload.event_id,
        payload_json=json.dumps(payload.model_dump(), ensure_ascii=False),
    )
    db.add(event)
    db.commit()

    payment = models.Payment(
        user_id=payload.user_id,
        provider=payload.provider,
        provider_tx_id=payload.tx_id,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        plan_code=payload.plan_code,
        status="paid" if payload.event_type == "payment_succeeded" else "pending",
        paid_at=datetime.utcnow() if payload.event_type == "payment_succeeded" else None,
    )
    db.add(payment)
    db.commit()

    if payload.event_type == "payment_succeeded":
        services.activate_premium(db, payload.user_id, payload.plan_code)

    return {"ok": True}


@app.post("/internal/upsert-user")
def upsert_user(
    payload: schemas.UpsertUserIn,
    app_secret: str | None = Header(default=None, alias="X-App-Secret"),
    db: Session = Depends(get_db),
):
    if APP_SECRET and app_secret != APP_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if user:
        user.name = payload.name.strip()
        user.email_id = payload.email_id.strip().lower()
        db.commit()
        db.refresh(user)
        services.ensure_plan_row(db, user.id)
        return {"ok": True, "user_id": user.id, "updated": True}

    # Insercao com id fixo para mapear com app local
    user = models.User(
        id=payload.user_id,
        name=payload.name.strip(),
        email_id=payload.email_id.strip().lower(),
        password_hash=services.hash_password(f"local-sync-{payload.user_id}"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    services.ensure_plan_row(db, user.id)
    return {"ok": True, "user_id": user.id, "created": True}
