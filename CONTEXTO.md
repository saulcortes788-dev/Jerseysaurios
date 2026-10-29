# Contexto rápido (leer esto primero, ahorra tokens)

**Qué es:** tienda de jerseys "Jerseysaurios". Flask 3 + SQLite + Jinja + CSS/JS vanilla (sin build). Deploy: Render (`render.yaml`, gunicorn 1 worker, disco `/var/data`).

## Mapa
- `negocio/__init__.py` create_app, config, CSRF, cabeceras/caché, admin catálogo, `/imagenes/`.
- `negocio/store.py` tienda pública, carrito, checkout, pedidos, límite IP, pedidos vencidos.
- `negocio/access.py` login/setup admin. `commands.py` CLI (`create-admin`, `backup-data`, `load-wavesoccer`).
- `negocio/categories.py`, `importer.py`, `media.py` (imágenes), `wavesoccer*.py` (catálogo externo).
- `templates/shop/*` tienda pública · `templates/*.html` admin · `static/shop.css` tienda · `static/style.css` admin.

## Rutas clave
`/` · `/tienda/catalogo` · `/tienda/jersey/<id>` · `/categorias` · `/carrito` · `/admin` · `/configurar` (solo no-producción) · `/salud`.

## Ejecutar
- Docker: `docker compose up -d --build` → http://localhost:8000 · demo: `docker compose exec -T web python cargar_demo.py` · borrar: `docker compose down -v`.
- Tests: `PYTHONPATH=tests:. .venv/Scripts/python -m unittest discover -s tests`
  - En Windows hay ~49 fallos de entorno (`PermissionError WinError 32` en tearDown, rutas cortas `SKYGUA~1`). Comparar contra línea base, no esperar 0.
- Producción exige `SECRET_KEY` ≥32 y `JERSEY_ENV=production` (setup web cerrado → usar `flask create-admin`).

## Estado (2026-10-28)
- Rama `feature/rediseno-v2`: commit `885cdae` (rediseño + fixes). Rediseño visual "Deportivo audaz" (oscuro + lima neón, Anton/Inter) de la tienda, Docker y estos .md **sin commit**. Sin push/PR.
- Pendiente: auditoría a11y formal, verificar 375 px, rediseñar admin (`style.css`), fijar versiones (lock) en `requirements.txt`, limpiar `docs/REVISION_*` y `listado_wavesoccer_nuevo.txt`.
- Ver `CHANGELOG.md`.
