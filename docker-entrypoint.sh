#!/bin/sh
set -e

MODE="${1:-app}"

case "$MODE" in
  app)
    echo "Waiting for PostgreSQL..."

    until pg_isready -h "$PG__HOST" -p "$PG__PORT" -U "${DEFAULT_ADMIN_USER:-postgres}" -d "${DEFAULT_ADMIN_DB:-postgres}"; do
      sleep 1
    done

    echo "Creating database/user if needed..."
    python create_database.py

    echo "Initializing database tables..."
    python init_db.py

    echo "Starting FastAPI..."
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ;;

  *)
    exec "$@"
    ;;
esac