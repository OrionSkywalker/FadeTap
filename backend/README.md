# FadeTap API

Local FastAPI backend for Stage 1 development.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API uses SQLite by default through `DATABASE_URL=sqlite:///./barber_booking.db`.
Swap this value to a PostgreSQL URL later without changing the model layer.

## Stripe local testing

Use Stripe test mode keys only. Put these values in `backend/.env`:

```powershell
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
APP_BASE_URL=http://localhost:5173
API_BASE_URL=http://localhost:8000
SHOP_SETUP_FEE_CENTS=2000
```

In one terminal, run the backend. In another terminal, forward Stripe test
events to the local webhook:

```powershell
stripe login
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

Copy the `whsec_...` value printed by `stripe listen` into `STRIPE_WEBHOOK_SECRET`,
then restart the backend. Create a shop from the frontend and Stripe Checkout
will open for the one-time setup payment.

Use Stripe's successful test card in Checkout:

```text
4242 4242 4242 4242
Any future expiration date
Any three-digit CVC
Any postal code
```
