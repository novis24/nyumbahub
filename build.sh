#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python - <<'PY'
import os
from urllib.parse import urlparse

url = os.getenv("DATABASE_URL")
print("DATABASE_URL exists:", bool(url))
print("DATABASE_URL host:", urlparse(url).hostname if url else None)
PY

python manage.py collectstatic --no-input
python manage.py migrate