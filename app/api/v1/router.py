from fastapi import APIRouter
from app.api.v1.routes import auth as auth_routes
from app.api.v1.routes import buyer_registrations as buyer_registration_routes
from app.api.v1.routes import family as family_routes
from app.api.v1.routes import subsidies as subsidies_routes
from app.api.v1.routes import users as users_routes
from app.api.v1.routes import vehicles as vehicles_routes
from app.api.v1.routes import registries as registries_routes
from app.api.v1.routes import wallet as wallet_routes
from app.api.v1.routes import webhooks as webhook_routes

api_router = APIRouter()
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
api_router.include_router(buyer_registration_routes.router, prefix="/buyer-registrations", tags=["buyer-registrations"])
api_router.include_router(family_routes.router, prefix="/family", tags=["family"])
api_router.include_router(subsidies_routes.router, prefix="/subsidies", tags=["subsidies"])
api_router.include_router(users_routes.router, prefix="/users", tags=["users"])
api_router.include_router(vehicles_routes.router, prefix="/vehicle-ownerships", tags=["vehicle-ownerships"])
api_router.include_router(registries_routes.router, prefix="/registries", tags=["registries"])
api_router.include_router(wallet_routes.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(webhook_routes.router, prefix="/webhooks", tags=["webhooks"])
