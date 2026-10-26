import io
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import test_app


class ImporterTests(unittest.TestCase):
    setUp = test_app.BusinessAppTests.setUp
    tearDown = test_app.BusinessAppTests.tearDown

    def rows(self):
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.row_factory=sqlite3.Row
            return db.execute('SELECT * FROM products').fetchall()

    def test_manual_import_and_no_remote_requests(self):
        data={'csrf_token':self.csrf,'authorized':'yes','confirm':'yes','sku':'IMP-M','name':'Prueba importación','price':'650.50','stock':'2','description':'Texto autorizado','image_url':'https://example.org/foto.png','credit':'Autor original'}
        with patch('negocio.sources.fetch_public', side_effect=AssertionError('No debe acceder a red')):
            self.client.post('/importar/guardar',data=data)
            self.assertEqual(self.rows()[0]['image_credit'],'Autor original')
            self.assertIsNone(self.rows()[0]['image_path'])
            self.client.post('/importar/extraer',data={'csrf_token':self.csrf,'source_url':'https://example.org'})
        self.assertEqual(len(self.rows()),1)
        self.client.post('/importar/guardar',data=data)
        self.assertEqual(len(self.rows()),1)
        self.client.post('/importar/guardar',data={**data,'sku':'NO','authorized':''})
        self.assertEqual(len(self.rows()),1)

    def test_csv_is_atomic_and_imports_local_images_with_credits(self):
        root=Path(self.temp_dir.name)/'importaciones'; root.mkdir()
        self.app.config['IMPORT_FOLDER']=str(root)
        Image.new('RGB',(20,20),'blue').save(root/'foto.png')
        csv='sku,name,price,image_file,credit,category\nCSV-M,Prueba CSV,100.00,foto.png,Autor original,Liga MX\n'
        self.client.post('/importar/csv',data={'csrf_token':self.csrf,'authorized':'yes','csv':(io.BytesIO(csv.encode()),'datos.csv')})
        product=self.rows()[0]
        self.assertTrue(product['image_path'].startswith('productos/'))
        self.assertEqual(product['image_credit'],'Autor original')
        bad='sku,name,price\nNUEVO,Prueba,10\nCSV-M,Duplicado,10\n'
        self.client.post('/importar/csv',data={'csrf_token':self.csrf,'authorized':'yes','csv':(io.BytesIO(bad.encode()),'datos.csv')})
        self.assertEqual(len(self.rows()),1)
        traversal='sku,name,price,image_file\nMAL,Prueba,10,../foto.png\n'
        self.client.post('/importar/csv',data={'csrf_token':self.csrf,'authorized':'yes','csv':(io.BytesIO(traversal.encode()),'datos.csv')})
        self.assertEqual(len(self.rows()),1)
