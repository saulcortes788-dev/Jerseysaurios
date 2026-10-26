import io
import os
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import create_app
from cargar_demo import load_demo


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.config={'TESTING':True,'PRODUCTION':True,'DATA_DIR':str(self.root/'datos'),'SECRET_KEY':'t'*64}

    def tearDown(self): self.temp.cleanup()

    def test_secret_required_data_persisted_and_web_setup_closed(self):
        with patch.dict(os.environ,{'SECRET_KEY':''}):
            with self.assertRaises(RuntimeError):create_app({**self.config,'SECRET_KEY':''})
        app=create_app(self.config)
        self.assertEqual(app.config['DATABASE'],str(self.root/'datos/tienda.sqlite3'))
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        client=app.test_client()
        self.assertEqual(client.get('/salud',base_url='https://tienda.example').status_code,200)
        self.assertEqual(client.get('/configurar',base_url='https://tienda.example').status_code,404)
        self.assertEqual(client.get('/admin',base_url='https://tienda.example').status_code,503)
        self.assertEqual(client.get('/',base_url='https://tienda.example').status_code,200)
        result=app.test_cli_runner().invoke(args=['create-admin','--username','propietario'],input='UnaClaveSegura123\nUnaClaveSegura123\n')
        self.assertEqual(result.exit_code,0,result.output)
        self.assertNotIn('UnaClaveSegura123',result.output)
        second=create_app(self.config)
        with sqlite3.connect(second.config['DATABASE']) as db:
            user=db.execute('SELECT username,password_hash FROM admins').fetchone()
            self.assertEqual(user[0],'propietario');self.assertNotEqual(user[1],'UnaClaveSegura123')
        self.assertNotEqual(second.test_client().get('/configurar',base_url='https://tienda.example').status_code,200)

    def test_proxy_secure_login_and_demo_hidden_without_deletion(self):
        app=create_app({**self.config,'TRUST_PROXY':True})
        app.test_cli_runner().invoke(args=['create-admin','--username','propietario'],input='UnaClaveSegura123\nUnaClaveSegura123\n')
        load_demo(app.config['DATABASE'])
        client=app.test_client()
        response=client.get('/ingresar',base_url='https://tienda.example')
        self.assertIn('Secure',response.headers.get('Set-Cookie',''))
        self.assertIn('max-age',response.headers.get('Strict-Transport-Security',''))
        with client.session_transaction(base_url='https://tienda.example') as session: token=session['csrf_token']
        response=client.post('/ingresar',base_url='https://tienda.example',data={'csrf_token':token,'username':'propietario','password':'UnaClaveSegura123'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(client.get('/admin',base_url='https://tienda.example').status_code,200)
        home=client.get('/',base_url='https://tienda.example')
        self.assertNotIn(b'[DEMOSTRACI',home.data)
        self.assertEqual(client.get('/tienda/jersey/1',base_url='https://tienda.example').status_code,404)
        with sqlite3.connect(app.config['DATABASE']) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0],5)
        result=app.test_cli_runner().invoke(args=['reset-admin-password'],input='OtraClaveSegura123\nOtraClaveSegura123\n')
        self.assertEqual(result.exit_code,0,result.output)

    def test_backup_includes_photos_and_database_not_code_or_customer_output(self):
        app=create_app(self.config)
        photos=Path(app.config['UPLOAD_FOLDER']);photos.mkdir()
        (photos/'prueba.txt').write_text('foto de prueba')
        result=app.test_cli_runner().invoke(args=['backup-data','--destination',str(self.root/'respaldos')])
        self.assertEqual(result.exit_code,0,result.output)
        archive=next((self.root/'respaldos').glob('*.tar.gz'))
        self.assertEqual(archive.stat().st_mode & 0o777,0o600)
        with tarfile.open(archive) as bundle:
            self.assertIn('tienda.sqlite3',bundle.getnames())
            self.assertIn('uploads/prueba.txt',bundle.getnames())
            self.assertNotIn('negocio',bundle.getnames())

    def test_trusted_hosts_reject_unknown_host(self):
        with patch.dict(os.environ,{'JERSEY_TRUSTED_HOSTS':'catalogo.example'}):
            app=create_app(self.config)
        self.assertEqual(app.test_client().get('/salud',base_url='https://otro.example').status_code,400)
        self.assertEqual(app.test_client().get('/salud',base_url='https://catalogo.example').status_code,200)
