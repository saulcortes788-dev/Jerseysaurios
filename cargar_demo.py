"""Carga opcional e idempotente: python cargar_demo.py. No sustituye datos reales."""
import sqlite3
from app import create_app
from negocio.categories import ensure_category, assign_product_category


def load_demo(database):
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        ensure_category(db,'Demostración')
        for size in ('S','M','L','XL','XXL'):
            db.execute('''INSERT OR IGNORE INTO products(sku,name,team,size,price_cents,stock,minimum_stock,cost_cents,category,description,model_key,season,featured,is_new,on_sale)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (f'DEMO-{size}','[DEMOSTRACIÓN] Jersey de prueba','Equipo de demostración',size,50000,5,2,20000,'Demostración',
                 'Producto y precios ficticios de demostración. No representa mercancía real ni está disponible para venta real.',
                 'DEMO-JERSEY','Demostración',1,1,1))

        for product in db.execute("SELECT id FROM products WHERE sku LIKE 'DEMO-%' AND category_id IS NULL").fetchall():
            assign_product_category(db,product['id'],derive=True)


if __name__=='__main__':
    app=create_app()
    load_demo(app.config['DATABASE'])
    print('Se agregaron tallas DEMO-S a DEMO-XXL, claramente identificadas. Retíralas desde Productos al terminar las pruebas.')
