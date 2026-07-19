import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .migrations import run_startup_migrations
from .routers import admin, auth, barbers, shops, stripe_webhooks
from .seed import seed_demo_shop

Base.metadata.create_all(bind=engine)
run_startup_migrations()
seed_demo_shop()

app = FastAPI(title="FadeTap API")

frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins.split(",")],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+):5173",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shops.router)
app.include_router(auth.router)
app.include_router(barbers.router)
app.include_router(admin.router)
app.include_router(stripe_webhooks.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
