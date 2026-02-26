from datetime import datetime
import os
import json
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from .database import Base, engine, get_db
from . import models, schemas, services, mercadopago


app = FastAPI(title="Quiz Vance Billing API", version="1.0.0")
Base.metadata.create_all(bind=engine)
APP_SECRET = os.getenv("APP_BACKEND_SECRET", "")


def _realign_users_id_sequence(db: Session | None = None) -> None:
    """Corrige sequencia de PK em Postgres quando houver insercoes com ID explicito."""
    stmt = text(
        "SELECT setval("
        "pg_get_serial_sequence('users', 'id'), "
        "COALESCE((SELECT MAX(id) FROM users), 0) + 1, "
        "false"
        ");"
    )
    try:
        if db is not None:
            bind = db.get_bind()
            dialect = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
            if "postgres" not in dialect:
                return
            db.execute(stmt)
            db.commit()
            return

        dialect = str(getattr(getattr(engine, "dialect", None), "name", "") or "").lower()
        if "postgres" not in dialect:
            return
        with engine.begin() as conn:
            conn.execute(stmt)
    except Exception:
        # Fallback silencioso: nao deve impedir o boot da API.
        if db is not None:
            db.rollback()


_realign_users_id_sequence()


def _backend_public_url(request: Request) -> str:
    env_url = str(os.getenv("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")
    if env_url:
        return env_url
    return str(request.base_url).rstrip("/")


def _frontend_public_url() -> str:
    return str(os.getenv("FRONTEND_PUBLIC_URL") or "").strip().rstrip("/")


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


def _ensure_user_settings_row(db: Session, user_id: int) -> models.UserSettings:
    row = db.query(models.UserSettings).filter(models.UserSettings.user_id == int(user_id)).first()
    if row:
        return row
    row = models.UserSettings(
        user_id=int(user_id),
        provider="gemini",
        model="gemini-2.5-flash",
        economia_mode=0,
        telemetry_opt_in=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "db": "up", "ts": datetime.utcnow().isoformat()}
    except Exception as ex:
        raise HTTPException(status_code=503, detail=f"db_down: {ex}") from ex


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
    try:
        db.commit()
    except IntegrityError as ex:
        db.rollback()
        detail = str(getattr(ex, "orig", ex) or "").lower()
        if ("users_pkey" in detail) or ("duplicate key value violates unique constraint" in detail and "users" in detail):
            _realign_users_id_sequence(db)
            user = models.User(
                name=payload.name.strip(),
                email_id=payload.email_id.strip().lower(),
                password_hash=services.hash_password(payload.password),
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError as ex2:
                db.rollback()
                detail2 = str(getattr(ex2, "orig", ex2) or "").lower()
                if ("email_id" in detail2) or ("users_email_id_key" in detail2):
                    raise HTTPException(status_code=409, detail="ID ja cadastrado") from ex2
                raise HTTPException(status_code=500, detail="Falha ao criar usuario.") from ex2
        elif ("email_id" in detail) or ("users_email_id_key" in detail):
            raise HTTPException(status_code=409, detail="ID ja cadastrado") from ex
        else:
            raise HTTPException(status_code=500, detail="Falha ao criar usuario.") from ex
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
def activate_plan(
    payload: schemas.ActivatePlanIn,
    app_secret: str | None = Header(default=None, alias="X-App-Secret"),
    db: Session = Depends(get_db),
):
    if APP_SECRET and app_secret != APP_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    # Ativacao direta bloqueada para evitar fraude por clique.
    raise HTTPException(status_code=403, detail="Ativacao direta bloqueada. Use checkout e confirmacao de pagamento.")


@app.post("/billing/checkout/start")
def start_checkout(payload: schemas.CheckoutStartIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        email = str(payload.email_id or "").strip().lower()
        name = str(payload.name or "").strip()
        if not email:
            email = f"user-{int(payload.user_id)}@quizvance.local"
        if not name:
            name = f"Usuario {int(payload.user_id)}"
        user = models.User(
            id=int(payload.user_id),
            name=name,
            email_id=email,
            password_hash=services.hash_password(f"local-sync-{payload.user_id}"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        services.ensure_plan_row(db, user.id)
    provider = str(payload.provider or "").strip().lower()
    if not provider:
        provider = "mercadopago" if mercadopago.enabled() else "manual"
    if provider in {"mercadopago", "mp"} and not mercadopago.enabled():
        raise HTTPException(status_code=400, detail="Mercado Pago nao configurado no backend.")

    checkout, msg = services.create_checkout_session(db, payload.user_id, payload.plan_code, provider)
    if not checkout:
        raise HTTPException(status_code=400, detail=msg)

    checkout_url = ""
    preference_id = ""
    if provider in {"mercadopago", "mp"}:
        backend_public = _backend_public_url(request)
        frontend_public = _frontend_public_url()
        notification_url = f"{backend_public}/billing/webhook/mercadopago"
        back_success = f"{frontend_public}/plans?checkout=success" if frontend_public else ""
        back_pending = f"{frontend_public}/plans?checkout=pending" if frontend_public else ""
        back_failure = f"{frontend_public}/plans?checkout=failure" if frontend_public else ""
        pref = mercadopago.create_checkout_preference(
            checkout_id=checkout.checkout_id,
            user_id=payload.user_id,
            plan_code=checkout.plan_code,
            amount_cents=int(checkout.amount_cents or 0),
            notification_url=notification_url,
            payer_email=user.email_id,
            back_url_success=back_success,
            back_url_pending=back_pending,
            back_url_failure=back_failure,
        )
        if mercadopago.is_test_token():
            checkout_url = str(pref.get("sandbox_init_point") or pref.get("init_point") or "").strip()
        else:
            checkout_url = str(pref.get("init_point") or pref.get("sandbox_init_point") or "").strip()
        preference_id = str(pref.get("id") or "").strip()
        if not checkout_url:
            reason = str(pref.get("message") or pref.get("error") or "").strip()
            if not reason:
                cause = pref.get("cause")
                if isinstance(cause, list) and cause:
                    first = cause[0] if isinstance(cause[0], dict) else {}
                    reason = str(first.get("description") or first.get("code") or "").strip()
            raise HTTPException(status_code=502, detail=f"Falha ao criar checkout no Mercado Pago. {reason}".strip())
        if preference_id:
            checkout.payment_code = preference_id
            db.commit()
            db.refresh(checkout)

    return {
        "ok": True,
        "message": msg,
        "checkout_id": checkout.checkout_id,
        "auth_token": checkout.auth_token,
        "payment_code": checkout.payment_code,
        "amount_cents": int(checkout.amount_cents or 0),
        "currency": checkout.currency,
        "plan_code": checkout.plan_code,
        "expires_at": checkout.expires_at,
        "provider": provider,
        "checkout_url": checkout_url,
        "preference_id": preference_id,
    }


@app.post("/billing/checkout/confirm")
def confirm_checkout(payload: schemas.CheckoutConfirmIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    ok, msg, _row = services.confirm_checkout_session(
        db,
        payload.user_id,
        payload.checkout_id,
        payload.auth_token,
        payload.tx_id,
        payload.provider,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg, "plan": _auth_out(db, user)}


@app.post("/billing/checkout/reconcile")
def reconcile_checkout(payload: schemas.CheckoutReconcileIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    checkout = (
        db.query(models.CheckoutSession)
        .filter(models.CheckoutSession.checkout_id == str(payload.checkout_id or "").strip())
        .first()
    )
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout nao encontrado")
    if int(checkout.user_id) != int(payload.user_id):
        raise HTTPException(status_code=403, detail="Checkout nao pertence ao usuario")

    if str(checkout.status or "") == "confirmed":
        return {"ok": True, "message": "Checkout ja confirmado.", "plan": _auth_out(db, user)}

    if str(checkout.provider or "").lower() not in {"mercadopago", "mp"}:
        raise HTTPException(status_code=400, detail="Reconciliacao automatica disponivel apenas para Mercado Pago.")

    payment = mercadopago.search_latest_payment_by_external_reference(str(checkout.checkout_id))
    if not payment:
        return {"ok": False, "message": "Pagamento ainda nao localizado no Mercado Pago.", "plan": _auth_out(db, user)}

    status = str(payment.get("status") or "").strip().lower()
    if status != "approved":
        return {"ok": False, "message": f"Pagamento ainda nao aprovado (status: {status or 'desconhecido'}).", "plan": _auth_out(db, user)}

    tx_id = str(payment.get("id") or "").strip()
    if not tx_id:
        return {"ok": False, "message": "Pagamento aprovado sem identificador de transacao.", "plan": _auth_out(db, user)}

    currency = str(payment.get("currency_id") or "BRL").strip() or "BRL"
    amount_cents = int(round(float(payment.get("transaction_amount") or 0) * 100))
    ok, msg, _payment_row = services.finalize_checkout_payment(
        db,
        checkout,
        provider="mercadopago",
        tx_id=tx_id,
        amount_cents=amount_cents,
        currency=currency,
        plan_code=str(checkout.plan_code or "premium_30"),
    )
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


@app.post("/billing/webhook/mercadopago")
async def billing_webhook_mercadopago(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    params = request.query_params
    topic = str(payload.get("type") or payload.get("topic") or params.get("type") or params.get("topic") or "").strip().lower()
    action = str(payload.get("action") or params.get("action") or "").strip().lower()

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    payment_id = str(data.get("id") or params.get("data.id") or "").strip()
    if not payment_id:
        # Alguns formatos antigos mandam id diretamente na query.
        qid = str(params.get("id") or "").strip()
        if qid.isdigit():
            payment_id = qid

    if "payment" not in topic and "payment" not in action:
        return {"ok": True, "message": "evento ignorado"}
    if not payment_id:
        return {"ok": True, "message": "evento sem payment_id"}

    event_id = f"mp:{payment_id}:{action or topic or 'event'}"
    exists = db.query(models.WebhookEvent).filter(models.WebhookEvent.event_id == event_id).first()
    if exists:
        return {"ok": True, "message": "evento ja processado"}

    payment = await run_in_threadpool(mercadopago.get_payment, payment_id)
    status = str(payment.get("status") or "").strip().lower()
    metadata = payment.get("metadata") if isinstance(payment.get("metadata"), dict) else {}
    checkout_id = str(metadata.get("checkout_id") or payment.get("external_reference") or "").strip()
    tx_id = str(payment.get("id") or payment_id).strip()
    plan_code = str(metadata.get("plan_code") or "").strip().lower()
    currency = str(payment.get("currency_id") or "BRL").strip() or "BRL"
    amount_cents = int(round(float(payment.get("transaction_amount") or 0) * 100))

    event_payload = {
        "notification": payload,
        "query": dict(params),
        "payment": payment,
    }
    event = models.WebhookEvent(
        provider="mercadopago",
        event_id=event_id,
        payload_json=json.dumps(event_payload, ensure_ascii=False),
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "message": "evento ja processado"}

    if status != "approved":
        db.commit()
        return {"ok": True, "message": f"status {status or 'unknown'} ignorado"}
    if not checkout_id:
        db.commit()
        return {"ok": True, "message": "pagamento aprovado sem checkout_id"}

    checkout = db.query(models.CheckoutSession).filter(models.CheckoutSession.checkout_id == checkout_id).first()
    if not checkout:
        db.commit()
        return {"ok": True, "message": "checkout nao encontrado"}

    ok, msg, _payment_row = services.finalize_checkout_payment(
        db,
        checkout,
        provider="mercadopago",
        tx_id=tx_id,
        amount_cents=amount_cents,
        currency=currency,
        plan_code=plan_code or str(checkout.plan_code or "premium_30"),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


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


@app.get("/internal/user-settings/{user_id}", response_model=schemas.UserSettingsOut)
def get_user_settings(
    user_id: int,
    app_secret: str | None = Header(default=None, alias="X-App-Secret"),
    db: Session = Depends(get_db),
):
    if APP_SECRET and app_secret != APP_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    row = _ensure_user_settings_row(db, int(user_id))
    return schemas.UserSettingsOut(
        user_id=int(user_id),
        provider=str(row.provider or "gemini"),
        model=str(row.model or "gemini-2.5-flash"),
        api_key=str(row.api_key) if row.api_key else None,
        economia_mode=bool(int(row.economia_mode or 0)),
        telemetry_opt_in=bool(int(row.telemetry_opt_in or 0)),
    )


@app.post("/internal/user-settings", response_model=schemas.UserSettingsOut)
def upsert_user_settings(
    payload: schemas.UpsertUserSettingsIn,
    app_secret: str | None = Header(default=None, alias="X-App-Secret"),
    db: Session = Depends(get_db),
):
    if APP_SECRET and app_secret != APP_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    user = db.query(models.User).filter(models.User.id == int(payload.user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    row = _ensure_user_settings_row(db, int(payload.user_id))
    row.provider = str(payload.provider or "gemini").strip().lower() or "gemini"
    row.model = str(payload.model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    row.api_key = str(payload.api_key).strip() if payload.api_key is not None else None
    row.economia_mode = 1 if bool(payload.economia_mode) else 0
    row.telemetry_opt_in = 1 if bool(payload.telemetry_opt_in) else 0
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return schemas.UserSettingsOut(
        user_id=int(payload.user_id),
        provider=str(row.provider or "gemini"),
        model=str(row.model or "gemini-2.5-flash"),
        api_key=str(row.api_key) if row.api_key else None,
        economia_mode=bool(int(row.economia_mode or 0)),
        telemetry_opt_in=bool(int(row.telemetry_opt_in or 0)),
    )
