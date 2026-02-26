# Quiz Vance Backend (Billing + Entitlements)

## Setup

```bash
cd backend
pip install -r requirements.txt
```

Observacao: para execucao local do backend, use Python 3.12 (mesma base do Docker/Fly).

Set env:

```bash
set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/quizvance
set APP_BACKEND_SECRET=troque-por-um-segredo
set BACKEND_PUBLIC_URL=https://quiz-vance-backend.fly.dev
set FRONTEND_PUBLIC_URL=https://seu-frontend.com
set MP_ACCESS_TOKEN=APP_USR-xxxxxxxx
```

Run:

```bash
uvicorn app.main:app --reload --port 8080
```

Suporte operacional (consulta/reconciliacao):

```bash
python scripts/support_tools.py user --user-id 123
python scripts/support_tools.py checkout --checkout-id SEU_CHECKOUT_ID
python scripts/support_tools.py reconcile --checkout-id SEU_CHECKOUT_ID
```

## Endpoints

- `POST /auth/register`
- `POST /auth/login`
- `GET /plans/me/{user_id}`
- `POST /billing/checkout/start`
- `POST /billing/checkout/confirm`
- `POST /billing/checkout/reconcile`
- `POST /usage/consume`
- `POST /billing/webhook`
- `POST /billing/webhook/mercadopago`

## Mercado Pago (automatico)

- `POST /billing/checkout/start` cria `checkout_session` e, com MP configurado, devolve `checkout_url`.
- O app abre `checkout_url` para o usuario pagar no Mercado Pago.
- Mercado Pago chama `POST /billing/webhook/mercadopago` e o backend ativa premium automaticamente quando `status=approved`.
- `POST /billing/checkout/confirm` continua disponivel como fallback manual.
- Em producao, use `APP_USR-...` e configure `FRONTEND_PUBLIC_URL` para retorno do checkout.
- O backend usa reconciliacao idempotente para auto-corrigir plano mesmo com reenvio de notificacao.

## Webhook behavior

- Idempotency by `event_id` in `webhook_events`.
- On `payment_succeeded` (manual) or Mercado Pago `approved`, plan is activated (`premium_30`).
- Direct activation endpoint is blocked to avoid premium unlock by simple click.

## Free vs Premium policy

- Free:
  - quiz/flashcards unlimited but slower + economic model
  - dissertativa correction limited to 1/day
- Premium:
  - fast + full model
  - dissertativa unlimited
