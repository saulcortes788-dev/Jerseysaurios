"""Entrada WSGI para Gunicorn. La configuración se obtiene del entorno."""
from negocio import create_app
app=create_app()
