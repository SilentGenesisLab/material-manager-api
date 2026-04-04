from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import materials


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure base storage directory exists on startup
    Path(settings.FILE_URL).resolve().mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Material Manager API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(materials.router)
