"""Punto de entrada local de la tienda y su administración."""
import os
from negocio import create_app, parse_money, parse_nonnegative_integer, peso

if __name__ == "__main__":
    try:
        port = int(os.environ.get('JERSEY_PORT', '5000'))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        raise SystemExit('El puerto debe ser un número entre 1 y 65535.')
    create_app().run(host="127.0.0.1", port=port, debug=False)
