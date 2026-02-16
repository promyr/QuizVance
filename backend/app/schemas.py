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
