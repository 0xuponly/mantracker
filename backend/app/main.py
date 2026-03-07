from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.routers import profiles, accounts, portfolio, unlock, settings
from app.security.crypto import AppLockedError, CredentialDecryptError


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    # shutdown if needed


app = FastAPI(
    title="Portfolio Tracker",
    description="Local-only portfolio tracker. Create profiles locally; import/export via file. No sign-in, no cloud.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    # Dev ports may change (Vite/Electron). Allow localhost/127.0.0.1 on any port.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router)
app.include_router(accounts.router)
app.include_router(portfolio.router)
app.include_router(unlock.router)
app.include_router(settings.router)


@app.exception_handler(AppLockedError)
def app_locked_handler(request, exc: AppLockedError):
    return JSONResponse(
        status_code=403,
        content={"detail": "App locked. Enter passphrase to unlock."},
    )


@app.exception_handler(CredentialDecryptError)
def credential_decrypt_handler(request, exc: CredentialDecryptError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
