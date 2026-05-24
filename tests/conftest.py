import pytest_asyncio

from app.core.database import engine

import pytest

@pytest.fixture(scope="session")
def anyio_backend():
    return 'asyncio'


@pytest_asyncio.fixture(autouse=True)
async def dispose_async_engine_pool_after_test():
    yield
    await engine.dispose()
