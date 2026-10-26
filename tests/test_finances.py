import sqlite3
import unittest
import test_app


class FinanceTests(unittest.TestCase):
    setUp = test_app.BusinessAppTests.setUp
    tearDown = test_app.BusinessAppTests.tearDown
    product = test_app.BusinessAppTests.product

    def test_finance_flow_and_historical_cost(self):
        self.product(cost='200.00')
        self.client.post('/clientes', data={'csrf_token': self.csrf, 'name': 'Ana'})
        self.client.post('/ventas', data={'csrf_token': self.csrf, 'product_id': '1', 'quantity': '2', 'client_id': '1'})
        self.client.post('/productos/1/actualizar', data={'csrf_token': self.csrf, 'price': '700', 'cost': '300', 'stock': '3', 'minimum_stock': '2'})
        self.client.post('/gastos', data={'csrf_token': self.csrf, 'description': 'Transporte', 'category': 'Servicios', 'amount': '50', 'spent_on': '2026-10-26'})
        response = self.client.get('/reportes')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'$749.80', response.data)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            self.assertEqual(db.execute('SELECT unit_cost_cents,client_id FROM sales').fetchone(), (20000, 1))
        for page in ('/', '/productos', '/inventario', '/ventas', '/clientes', '/gastos', '/reportes?desde=2026-10-01&hasta=2026-10-31'):
            self.assertEqual(self.client.get(page).status_code, 200, page)
        self.assertIn(b'$1,199.80', self.client.get('/clientes').data)

    def test_unknown_cost_and_invalid_expense(self):
        self.product()
        self.client.post('/ventas', data={'csrf_token': self.csrf, 'product_id': '1', 'quantity': '1'})
        self.assertIn(b'provisional', self.client.get('/reportes').data)
        self.client.post('/gastos', data={'csrf_token': self.csrf, 'description': 'Error', 'category': 'Otros', 'amount': '-1', 'spent_on': '2026-10-26'})
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0], 0)
        self.assertEqual(self.client.get('/reportes?desde=incorrecto').status_code, 302)

    def test_migration_preserves_legacy_records(self):
        from app import create_app
        from pathlib import Path
        legacy = Path(self.temp_dir.name) / 'legacy.sqlite3'
        with sqlite3.connect(legacy) as db:
            db.executescript((Path(__file__).parent/'fixtures/schema_original.sql').read_text())
            db.execute("INSERT INTO products(sku,name,team,size,price_cents,stock) VALUES('OLD','Anterior','General','U',100,5)")
            db.execute("INSERT INTO sales(product_id,sku,product_name,quantity,unit_price_cents,total_cents) VALUES(1,'OLD','Anterior',1,100,100)")
        create_app({'TESTING': True, 'DATABASE': str(legacy)})
        create_app({'TESTING': True, 'DATABASE': str(legacy)})
        with sqlite3.connect(legacy) as db:
            self.assertEqual(db.execute('SELECT stock,cost_cents FROM products').fetchone(), (5, None))
            self.assertEqual(db.execute('SELECT total_cents,unit_cost_cents FROM sales').fetchone(), (100, None))
