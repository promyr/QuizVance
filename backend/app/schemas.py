from datetime import datetime
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    name: str
    email_id: str
    password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email_id: str
    password: str


class AuthOut(BaseModel):
    user_id: int
    name: str
    email_id: str
    plan_code: str
    premium_active: bool
    premium_until: datetime | None = None


class ActivatePlanIn(BaseModel):
    user_id: int
    plan_code: str


class CheckoutStartIn(BaseModel):
    user_id: int
    plan_code: str
    provider: str = "mercadopago"
    name: str = ""
    email_id: str = ""


class CheckoutConfirmIn(BaseModel):
    user_id: int
    checkout_id: str
    auth_token: str
    tx_id: str
    provider: str = "mercadopago"


class CheckoutReconcileIn(BaseModel):
    user_id: int
    checkout_id: str


class ConsumeUsageIn(BaseModel):
    user_id: int
    feature_key: str
    limit_per_day: int


class WebhookPaymentIn(BaseModel):
    provider: str
    event_id: str
    event_type: str
    user_id: int
    tx_id: str
    amount_cents: int = 0
    currency: str = "BRL"
    plan_code: str = "premium_30"


class UpsertUserIn(BaseModel):
    user_id: int
    name: str
    email_id: str


class UserSettingsOut(BaseModel):
    user_id: int
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    api_key: str | None = None
    economia_mode: bool = False
    telemetry_opt_in: bool = False


class UpsertUserSettingsIn(BaseModel):
    user_id: int
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    api_key: str | None = None
    economia_mode: bool = False
    telemetry_opt_in: bool = False
