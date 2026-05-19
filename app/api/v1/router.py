from fastapi import APIRouter
from app.api.v1.routes import auth as auth_routes
from app.api.v1.routes import users as users_routes

api_router = APIRouter()
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
api_router.include_router(users_routes.router, prefix="/users", tags=["users"])
