#!/usr/bin/env sh
set -eu

if [ ! -x "backend/.venv/bin/ruff" ] || [ ! -x "backend/.venv/bin/pytest" ]; then
  cat <<'MSG'
Missing backend virtual environment or required tools.

Expected:
  backend/.venv/bin/ruff
  backend/.venv/bin/pytest

Create it with:
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements-dev.txt
MSG
  exit 1
fi

printf "Running backend lint...\n"
backend/.venv/bin/ruff check backend

printf "\nRunning backend tests...\n"
backend/.venv/bin/pytest backend/tests

printf "\nRunning Python compile check...\n"
python3 -m compileall backend/app backend/tests

printf "\nRunning git whitespace check...\n"
git diff --check

printf "\nBackend checks passed.\n"
