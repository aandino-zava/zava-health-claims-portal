import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import services
from app.auth import EntraVerifier, current_user, require
from app.config import Settings
from app.database import database
from app.limits import RequestLimits
from app.schemas import (
    AnalyticsResponse,
    ClaimCreate,
    ClaimDetail,
    ClaimList,
    ClaimStatus,
    IdentityResponse,
    ServiceType,
    StatusUpdate,
)
from app.telemetry import configure_logging, event, request_id

STATIC = Path(__file__).parent / "static"


def db_session(request: Request):
    with request.app.state.sessions() as db:
        yield db


def create_app(settings=None):
    settings = settings or Settings()
    configure_logging()
    engine, sessions = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        event("synthetic_demo_started")
        stop, task = asyncio.Event(), None
        if settings.concierge_enabled:
            from app.concierge import run_worker
            task = asyncio.create_task(run_worker(settings, sessions, stop))
        yield
        stop.set()
        if task:
            await task
        engine.dispose()

    app = FastAPI(
        title="Health Claims Portal API",
        version="1.0.0",
        lifespan=lifespan,
        description="Synthetic internal demonstration. All claims operations require assigned roles.",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings, app.state.engine, app.state.sessions = settings, engine, sessions
    app.state.verifier = EntraVerifier(settings) if settings.auth_mode == "entra" else None
    app.add_middleware(RequestLimits, max_bytes=settings.max_request_bytes,
                       per_minute=settings.requests_per_minute)

    @app.middleware("http")
    async def headers(request, call_next):
        started = monotonic()
        correlation = uuid4().hex
        token = request_id.set(correlation)
        try:
            response = await call_next(request)
            route = getattr(request.scope.get("route"), "path", "unmatched")
            event("request_completed", method=request.method, route=route, status=response.status_code,
                  duration_ms=round((monotonic() - started) * 1000))
            if response.status_code in {401, 403}:
                event("access_rejected", status=response.status_code)
        except Exception as exc:
            event("request_failed", reason=type(exc).__name__, status=500,
                  method=request.method, route=getattr(request.scope.get("route"), "path", "unmatched"))
            response = JSONResponse(status_code=500, content={"detail": "Unexpected application error"})
        finally:
            request_id.reset(token)
        response.headers["X-Request-ID"] = correlation
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = (
            "public, max-age=0, must-revalidate" if request.url.path.startswith("/static/") else "no-store"
        )
        if request.url.path != "/docs":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                f"connect-src 'self' {settings.entra_authority_host}; "
                f"frame-src 'self' {settings.entra_authority_host}; form-action 'self'"
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Avoid echoing personal-looking input values back into error telemetry.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request, exc):
        event("database_unavailable", reason="database_error")
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})

    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(db=Depends(db_session)):
        db.execute(text("SELECT id FROM claims LIMIT 1"))
        return {"status": "ready"}

    @app.get("/api/config", include_in_schema=False)
    def config():
        return {
            "auth_mode": settings.auth_mode,
            "tenant_id": settings.entra_tenant_id,
            "spa_client_id": settings.entra_spa_client_id,
            "authority": f"{settings.entra_authority_host}/{settings.entra_tenant_id}",
            "scope": f"api://{settings.entra_api_client_id}/Claims.Access",
        }

    @app.get("/api/v1/me", tags=["Identity"], response_model=IdentityResponse)
    def me(user=Depends(current_user)):
        return {"subject": user.subject, "roles": sorted(user.roles)}

    @app.get("/api/v1/claims", response_model=ClaimList, tags=["Claims"], operation_id="listClaims")
    def claims(
        q: str = Query("", max_length=100),
        status: ClaimStatus | None = None,
        service_type: ServiceType | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        user=Depends(require("Claims.Reader")),
        db=Depends(db_session),
    ):
        return services.list_claims(db, q, status, service_type, offset, limit)

    @app.get(
        "/api/v1/claims/{claim_id}", response_model=ClaimDetail, tags=["Claims"], operation_id="getClaim"
    )
    def claim(claim_id: str, user=Depends(require("Claims.Reader")), db=Depends(db_session)):
        return services.detail(services.get_claim(db, claim_id))

    @app.post(
        "/api/v1/claims",
        response_model=ClaimDetail,
        status_code=201,
        tags=["Claims"],
        operation_id="createClaim",
        description="Requires Claims.Writer and an Idempotency-Key. Synthetic claims only.",
        responses={200: {"model": ClaimDetail, "description": "Identical submission replayed using its original key"}},
    )
    def create(
        data: ClaimCreate,
        response: Response,
        idempotency_key: str = Header(min_length=8, max_length=128),
        user=Depends(require("Claims.Writer")),
        db=Depends(db_session),
    ):
        row, created = services.create_claim(db, data, user.subject, idempotency_key)
        response.status_code = 201 if created else 200
        return services.detail(row)

    @app.patch(
        "/api/v1/claims/{claim_id}/status",
        response_model=ClaimDetail,
        tags=["Claims"],
        operation_id="updateClaimStatus",
        description="Requires Claims.Reviewer. Use expected_version from the latest claim. Records an audit event.",
    )
    def status(
        claim_id: str, data: StatusUpdate, user=Depends(require("Claims.Reviewer")), db=Depends(db_session)
    ):
        return services.detail(services.change_status(db, claim_id, data, user.subject))

    @app.get("/api/v1/analytics", tags=["Analytics"], operation_id="getClaimsAnalytics",
             response_model=AnalyticsResponse)
    def analytics(user=Depends(require("Claims.Reader")), db=Depends(db_session)):
        return services.analytics(db)

    @app.get("/api/v1/transitions", tags=["Claims"], operation_id="getAllowedTransitions",
             response_model=dict[str, list[str]])
    def transitions(user=Depends(require("Claims.Reader"))):
        return services.TRANSITIONS

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
