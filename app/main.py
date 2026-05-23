from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.config import settings
from app.api.v1.router import api_router
from app.modules.buyer_registrations.model_store import close_model_store, initialize_model_store

@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_model_store()
    try:
        yield
    finally:
        await close_model_store()


def custom_generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {"status": "ok"}
