#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3. Instálalo desde el gestor de paquetes de tu distribución Linux."
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Preparando el entorno del proyecto..."
  python3 -m venv .venv || { echo "No se pudo crear el entorno. En Debian/Ubuntu prueba: sudo apt install python3-venv"; exit 1; }
fi
if ! .venv/bin/python -c 'import flask; import PIL' >/dev/null 2>&1; then
  echo "Instalando dependencias (necesitas Internet la primera vez)..."
  .venv/bin/python -m pip install -r requirements.txt
fi
export JERSEY_PORT="${1:-${JERSEY_PORT:-5000}}"
echo "Tienda: http://127.0.0.1:${JERSEY_PORT}"
echo "Administración: http://127.0.0.1:${JERSEY_PORT}/admin"
exec .venv/bin/python app.py
