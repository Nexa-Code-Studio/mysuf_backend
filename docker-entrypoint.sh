#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Load defaults if not defined
POSTGRES_SERVER=${POSTGRES_SERVER:-db}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
POSTGRES_USER=${POSTGRES_USER:-postgres}

echo "Waiting for database to be ready at ${POSTGRES_SERVER}:${POSTGRES_PORT} as user ${POSTGRES_USER}..."
until pg_isready -h "$POSTGRES_SERVER" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
  echo "Database is unavailable - sleeping"
  sleep 1
done

echo "Database is ready!"

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting FastAPI backend server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
