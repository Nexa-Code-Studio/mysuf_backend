# MySuf Backend

This is a FastAPI backend project using a modular monolith structure.

## Tech Stack
- FastAPI
- SQLAlchemy 2.x (asyncpg)
- Alembic
- PostgreSQL
- Pydantic v2
- JWT Authentication

## Setup Instructions

1. Create a virtual environment and activate it:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

3. Configure environment variables in `.env` file. Ensure `POSTGRES_PASSWORD` and other database settings match your local PostgreSQL setup.

4. Initialize database using Alembic (After the first migration is generated):
   ```bash
   alembic upgrade head
   ```

5. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```
