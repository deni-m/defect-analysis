#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv-mac}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Creating macOS virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"

echo "Installing/updating project dependencies"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -e .

echo "Starting Streamlit at http://localhost:8501"
exec "$PY" -m streamlit run src/qa_bugs/ui/app.py \
  --server.address=localhost \
  --server.port=8501 \
  --server.maxUploadSize=200 \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false \
  "$@"
