"""Seed local sin red: .venv/bin/python seed_categorias.py [--vincular-productos]."""
import argparse
import sqlite3
from app import create_app
from negocio.categories import seed_categories, assign_product_category

if __name__=='__main__':
    parser = argparse.ArgumentParser(description='Carga las 30 categorías solicitadas sin duplicados ni descargas.')
    parser.add_argument('--vincular-productos',action='store_true',help='Vincula solo productos que aún no tienen categoría jerárquica, usando sus datos locales.')
    args = parser.parse_args()
    app = create_app()
    with sqlite3.connect(app.config['DATABASE']) as db:
        db.row_factory=sqlite3.Row
        count=seed_categories(db)
        linked=0
        if args.vincular_productos:
            for p in db.execute('SELECT id FROM products WHERE category_id IS NULL').fetchall():
                linked += bool(assign_product_category(db,p['id'],derive=True))
        print(f'Categorías nuevas: {count}. Productos vinculados: {linked}. Sin solicitudes de red.')
