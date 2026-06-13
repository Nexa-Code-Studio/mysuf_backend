from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# Import all models to ensure they are registered with SQLAlchemy's metadata before mappers are configured
import app.modules.users.models
import app.modules.auth.models
import app.modules.buyer_registrations.models
import app.modules.companies.models
import app.modules.gas_stations.models
import app.modules.wallets.models
import app.modules.transactions.models
import app.modules.fuels.models
import app.modules.subsidies.models
import app.modules.vehicles.models
import app.modules.registries.models
import app.modules.notifications.models
import app.modules.spbu_activities.models
import app.modules.system_audit_logs.models

