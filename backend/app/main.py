"""Atlas Industrial Supply -- synthetic business systems API.

FICTIONAL. Atlas Industrial Supply is an invented company built to demonstrate
how a conversational agent integrates with the systems behind a customer
conversation. No data served by this API describes a real customer or order.

This service is the authoritative half of the deployment. The voice agent
decides *what to ask for*; this API decides *what is true and what is allowed*.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api import customers, demo, inventory, orders, products, rfqs
from app.config import get_settings
from app.db import Base, engine
from app.errors import (
    AtlasError,
    atlas_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.logging_config import RequestLoggingMiddleware, configure_logging, log_event
from app.security import require_api_key

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging(settings.log_level)

    # Create the schema if the database has never been initialised. Seeding is
    # left to `python -m seed.seed` so that starting the server never silently
    # overwrites data someone is mid-demo with.
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    log_event(
        "startup",
        database_url=settings.database_url.split("/")[-1],
        tables=len(tables),
        demo_mode=settings.demo_mode,
        auth_enabled=bool(settings.api_key),
    )
    yield


app = FastAPI(
    title="Atlas Industrial Supply -- Internal Systems API",
    version="0.1.0",
    description=(
        "Synthetic order, inventory, product and quoting systems for a fictional industrial "
        "distributor. Consumed by an ElevenLabs voice agent through webhook tools.\n\n"
        "**All data is fabricated.** Atlas Industrial Supply does not exist."
    ),
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)

app.add_exception_handler(AtlasError, atlas_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health() -> dict:
    return {"status": "ok", "service": "atlas-backend", "demo_mode": settings.demo_mode}


# Every business route sits behind the shared-secret check. The agent's webhook
# tools present it; the browser never does, because the frontend talks to these
# endpoints only through its own server routes.
protected = [Depends(require_api_key)]

app.include_router(customers.router, prefix="/api", dependencies=protected)
app.include_router(products.router, prefix="/api", dependencies=protected)
app.include_router(inventory.router, prefix="/api", dependencies=protected)
app.include_router(orders.router, prefix="/api", dependencies=protected)
app.include_router(rfqs.router, prefix="/api", dependencies=protected)
app.include_router(demo.router, prefix="/api", dependencies=protected)
