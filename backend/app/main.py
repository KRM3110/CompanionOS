import logging
import os

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import state
from .chat_jobs import ChatJobEngine
from .db import init_db
from .llm_client import close_llm_client, init_llm_client
from .routes import (
    alerts,
    chat,
    health,
    memory,
    modes,
    research,
    security,
    sessions,
    tools,
    workspaces,
)

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    health,
    modes,
    sessions,
    memory,
    chat,
    alerts,
    tools,
    security,
    workspaces,
    research,
):
    app.include_router(module.router)


@app.on_event("startup")
async def _startup():
    await init_db()
    await init_llm_client()
    state.CHAT_JOB_ENGINE = ChatJobEngine(
        settings=state.settings,
        modes=state.MODES,
        tools_registry=state.TOOLS_REGISTRY,
    )
    await state.CHAT_JOB_ENGINE.start()


@app.on_event("shutdown")
async def _shutdown():
    if state.CHAT_JOB_ENGINE:
        await state.CHAT_JOB_ENGINE.stop()
        state.CHAT_JOB_ENGINE = None
    await close_llm_client()
