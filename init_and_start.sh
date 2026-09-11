#!/bin/bash
set -e

echo "Initializing database schema..."
python run_init_db.py

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port $PORT

