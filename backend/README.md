# Quiz Vance Backend (Billing + Entitlements)

## Setup

```bash
cd backend
pip install -r requirements.txt
```

Set env:

```bash
set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/quizvance
```

Run:

```bash
uvicorn app.main:app --reload --port 8080
```

## Endpoints

- `POST /auth/register`
- `POST /auth/login`
- `GET /plans/me/{user_id}`
- `POST /plans/activate`
- `POST /usage/consume`
- `POST /billing/webhook`

## Webhook behavior

- Idempotency by `event_id` in `webhook_events`.
- On `payment_succeeded`, plan is activated (`premium_15` or `premium_30`).

## Free vs Premium policy

- Free:
  - quiz/flashcards unlimited but slower + economic model
  - dissertativa correction limited to 1/day
- Premium:
  - fast + full model
  - dissertativa unlimited
