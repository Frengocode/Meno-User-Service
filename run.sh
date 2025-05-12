#!/bin/bash

alembic upgrade head

echo "Migrations Successfully runned"

uvicorn app.app:app --reload --host 0.0.0.0 --port 8000
