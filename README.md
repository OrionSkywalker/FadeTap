# FadeTap

Multi-tenant appointment booking and payment platform for barber shops and other appointment-based providers.

## Deployment

- **Frontend:** Vercel, with `frontend` selected as the Root Directory.
- **API and PostgreSQL:** Render, using the included `render.yaml` Blueprint.

### Vercel environment variable

```text
VITE_API_BASE_URL=https://YOUR-RENDER-API.onrender.com
```

### Render environment variables

Configure these in the Render dashboard; never commit them:

```text
APP_BASE_URL=https://YOUR-VERCEL-APP.vercel.app
API_BASE_URL=https://YOUR-RENDER-API.onrender.com
FRONTEND_ORIGINS=https://YOUR-VERCEL-APP.vercel.app
COOKIE_SECURE=true
JWT_SECRET=generate-a-long-random-secret
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://YOUR-RENDER-API.onrender.com/api/auth/google/callback
PLATFORM_ADMIN_EMAILS=you@example.com
```

In Google Cloud, add the production `GOOGLE_REDIRECT_URI` to the OAuth client's authorized redirect URIs. In Stripe, add the Render webhook URL: `https://YOUR-RENDER-API.onrender.com/api/stripe/webhook`.
