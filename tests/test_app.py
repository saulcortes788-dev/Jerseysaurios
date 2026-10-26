import tempfile
import unittest
from pathlib import Path

from app import create_app


class BusinessAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite3"), "UPLOAD_FOLDER": str(Path(self.temp_dir.name) / "uploads")})
        self.client = self.app.test_client()
        self.client.get("/configurar")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.client.post('/configurar', data={'csrf_token': token, 'username': 'admin', 'password': 'UnaClave12345', 'confirm': 'UnaClave12345'})
        self.client.post('/ingresar', data={'csrf_token': token, 'username': 'admin', 'password': 'UnaClave12345'})
        with self.client.session_transaction() as session:
            self.csrf = session["csrf_token"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def product(self, **overrides):
        data = {
            "csrf_token": self.csrf, "sku": "AMERICA-M", "name": "Jersey local",
            "team": "América", "size": "M", "price": "599.90",
            "stock": "5", "minimum_stock": "2"
        }
        data.update(overrides)
        return self.client.post("/productos/agregar", data=data, follow_redirects=True)

    def test_dashboard_and_product_add(self):
        response = self.product()
        self.assertIn("Producto agregado correctamente".encode(), response.data)
        response = self.client.get("/admin")
        self.assertIn(b"Unidades disponibles", response.data)
        self.assertIn(b">5</strong>", response.data)

    def test_sale_decreases_stock_and_uses_historical_price(self):
        self.product()
        result = self.client.post("/ventas", data={"csrf_token": self.csrf,
                                                  "product_id": 1, "quantity": "2"}, follow_redirects=True)
        self.assertIn(b"Venta registrada", result.data)
        with self.app.app_context():
            import sqlite3
            con = sqlite3.connect(self.app.config["DATABASE"])
            product = con.execute("SELECT stock FROM products WHERE id=1").fetchone()
            sale = con.execute("SELECT quantity,total_cents FROM sales").fetchone()
            con.close()
        self.assertEqual(product[0], 3)
        self.assertEqual(sale, (2, 119980))

    def test_sale_rejects_insufficient_stock_without_changing_data(self):
        self.product()
        response = self.client.post("/ventas", data={"csrf_token": self.csrf,
                                                    "product_id": 1, "quantity": "8"}, follow_redirects=True)
        self.assertIn(b"No hay existencias suficientes", response.data)
        self.assertIn(b"No hay existencias suficientes", response.data)
        with self.app.app_context():
            import sqlite3
            con = sqlite3.connect(self.app.config["DATABASE"])
            self.assertEqual(con.execute("SELECT stock FROM products WHERE id=1").fetchone()[0], 5)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)
            con.close()

    def test_product_avoids_duplicate_sku(self):
        self.product()
        response = self.product()
        self.assertIn(b"SKU", response.data)

    def test_csrf_required(self):
        response = self.client.post("/productos/agregar", data={"sku": "HELLO"})
        self.assertEqual(response.status_code, 400)

    def test_csv_export(self):
        self.product()
        response = self.client.get("/exportar/productos.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("América".encode(), response.data)
        self.assertIn(b"599.90", response.data)

    def test_reject_invalid_money(self):
        response = self.product(price="99.999")
        self.assertIn(b"dos decimales", response.data)


if __name__ == "__main__":
    unittest.main()
