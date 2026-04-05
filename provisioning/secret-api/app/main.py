from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.util import configure_json_logging

from .config import get_settings
from .db import init_db
from .routes.bootstrap import router as bootstrap_router
from .routes.health import router as health_router

settings = get_settings()
configure_json_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("service starting")
    yield
    logger.info("service stopping")


app = FastAPI(title="Bootstrap Secret API", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(bootstrap_router)
