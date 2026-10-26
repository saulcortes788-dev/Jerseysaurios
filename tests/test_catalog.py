import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from app import create_app


class CatalogAndAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.app = create_app({'TESTING': True, 'DATABASE': str(self.path / 'test.db'), 'UPLOAD_FOLDER': str(self.path / 'uploads')})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def token(self):
        with self.client.session_transaction() as sess:
            return sess['csrf_token']

    def login(self):
        self.client.get('/configurar')
        self.client.post('/configurar', data={'csrf_token': self.token(), 'username': 'admin', 'password': 'SeguraClave123', 'confirm': 'SeguraClave123'})
        self.client.post('/ingresar', data={'csrf_token': self.token(), 'username': 'admin', 'password': 'SeguraClave123'})

    def test_initial_setup_login_logout_and_protected_data(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/admin').location, '/configurar')
        self.login()
        self.assertEqual(self.client.get('/configurar').location, '/ingresar')
        for url in ('/', '/catalogo', '/productos', '/inventario', '/ventas', '/clientes', '/gastos', '/reportes', '/integracion'):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.post('/salir', data={'csrf_token': self.token()})
        self.assertEqual(self.client.get('/exportar/productos.csv').location, '/ingresar')
        self.assertEqual(self.client.get('/catalogo').location, '/ingresar')
        self.client.get('/ingresar')
        self.client.post('/ingresar', data={'csrf_token': self.token(), 'username': 'admin', 'password': 'incorrecta'})
        self.assertEqual(self.client.get('/productos').location, '/ingresar')
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            stored = db.execute('SELECT password_hash FROM admins').fetchone()[0]
            self.assertNotEqual(stored, 'SeguraClave123')

    def product_data(self):
        return {'csrf_token': self.token(), 'sku': 'MEX-M', 'name': 'México local', 'team': 'México', 'size': 'M', 'selection': 'México', 'league': 'Selecciones', 'brand': 'Adidas', 'category': 'Local', 'price': '800', 'cost': '300', 'stock': '5', 'minimum_stock': '2'}

    def test_image_upload_filters_edit_and_sections(self):
        self.login()
        file = io.BytesIO()
        Image.new('RGB', (40, 40), 'blue').save(file, 'PNG')
        file.seek(0)
        data = self.product_data()
        data['image'] = (file, '../../foto.png')
        self.client.post('/productos/agregar', data=data, content_type='multipart/form-data')
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            image = db.execute('SELECT image_path FROM products').fetchone()[0]
        self.assertNotIn('/', image)
        with self.client.get('/imagenes/' + image) as response:
            self.assertEqual(response.status_code, 200)
        result = self.client.get('/catalogo?team=M%C3%A9xico&brand=Adidas&size=M&category=Local')
        self.assertIn('México local'.encode(), result.data)
        self.assertNotIn('México local'.encode(), self.client.get('/catalogo?brand=Nike').data)
        self.assertEqual(self.client.get('/productos/1/ficha').status_code, 200)
        self.client.post('/productos/1/ficha', data={**self.product_data(), 'name': 'México visitante'})
        self.assertIn('México visitante'.encode(), self.client.get('/catalogo').data)
        self.client.post('/integracion', data={'csrf_token': self.token(), 'title': 'Envíos', 'body': '<script>alert(1)</script>', 'source_url': 'https://example.org'})
        result = self.client.get('/catalogo')
        self.assertIn('Envíos'.encode(), result.data)
        self.assertNotIn(b'<script>', result.data)
        self.assertEqual(self.client.get('/imagenes/../../app.py').status_code, 404)

    def test_invalid_image_rolls_back_product_and_size_limit(self):
        self.login()
        data = self.product_data()
        data['image'] = (io.BytesIO(b'<svg>not a raster image</svg>'), 'foto.png')
        result = self.client.post('/productos/agregar', data=data, follow_redirects=True)
        self.assertIn('imagen válida'.encode(), result.data)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0], 0)
        self.assertEqual(self.app.config['MAX_CONTENT_LENGTH'], 8 * 1024 * 1024)
        self.app.config['MAX_CONTENT_LENGTH'] = 1024
        result = self.client.post('/productos/agregar', data={'csrf_token': self.token(), 'image': (io.BytesIO(b'x' * 2048), 'grande.jpg')})
        self.assertEqual(result.status_code, 413)
