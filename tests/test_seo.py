import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from app import create_app


class SeoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({'TESTING': True, 'PRODUCTION': True,
                               'DATA_DIR': str(Path(self.temp.name)),
                               'SECRET_KEY': 's' * 64, 'TRUST_PROXY': True})
        self.client = self.app.test_client()
        self.origin = 'https://jerseysaurios.onrender.com'

    def test_public_xml_visibility_and_no_writes(self):
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            parent = db.execute("INSERT INTO shop_categories(name,slug,active) VALUES('Oculta','oculta',0)").lastrowid
            child = db.execute("INSERT INTO shop_categories(name,slug,parent_id) VALUES('Hija','hija',?)", (parent,)).lastrowid
            for sku, active, category in [('PUBLIC', 1, None), ('INACTIVE', 0, None),
                                           ('HIDDEN', 1, child), ('DEMO-SEO', 1, None)]:
                db.execute("INSERT INTO products(sku,name,team,size,price_cents,stock,active,category_id) VALUES(?,?,'Equipo','M',100,0,?,?)",
                           (sku, sku, active, category))
            db.commit()
            before = list(db.iterdump())
        response = self.client.get('/sitemap.xml', base_url=self.origin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/xml')
        root = ElementTree.fromstring(response.data)
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        self.assertEqual(root.tag, ns + 'urlset')
        locations = [node.text for node in root.findall(ns + 'url/' + ns + 'loc')]
        self.assertEqual(locations[0], self.origin + '/')
        self.assertEqual(len(locations), len(set(locations)))
        self.assertIn(self.origin + '/tienda/jersey/1', locations)
        for product_id in (2, 3, 4):
            self.assertNotIn(self.origin + f'/tienda/jersey/{product_id}', locations)
        self.assertFalse(any('/oculta' in url for url in locations))
        for url in locations:
            self.assertEqual(self.client.get(urlsplit(url).path, base_url=self.origin).status_code, 200, url)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            self.assertEqual(list(db.iterdump()), before)

    def test_robots_public_allowlist_and_admin_protection(self):
        response = self.client.get('/robots.txt', base_url=self.origin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/plain')
        text = response.get_data(as_text=True)
        self.assertNotIn('/admin', text)
        self.assertNotIn('/ingresar', text)
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        self.assertEqual(parser.site_maps(), [self.origin + '/sitemap.xml'])
        # Check wildcard/end-anchor rules with the same longest-match convention
        # used by search crawlers (stdlib RobotFileParser lacks this support).
        import re
        rules = [line.split(': ', 1) for line in text.splitlines() if line.startswith(('Allow:', 'Disallow:'))]
        def allowed(path):
            matches = [(len(pattern), kind == 'Allow') for kind, pattern in rules
                       if re.match(re.escape(pattern).replace(r'\$', '$'), path)]
            return max(matches)[1]
        for path in ('/', '/tienda/catalogo', '/tienda/catalogo?q=jersey', '/tienda/jersey/1',
                     '/categorias', '/categorias/liga-mx', '/static/style.css', '/imagenes/public.jpg', '/sitemap.xml'):
            self.assertTrue(allowed(path), path)
        for path in ('/admin', '/productos', '/inventario', '/reportes', '/ingresar', '/carrito', '/pedido/token'):
            self.assertFalse(allowed(path), path)
        for path in ('/admin', '/productos', '/admin/pedidos'):
            self.assertEqual(self.client.get(path, base_url=self.origin).status_code, 503)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.execute("INSERT INTO admins VALUES(1,'admin','unused')")
        for path in ('/sitemap.xml', '/robots.txt'):
            self.assertEqual(self.client.get(path, base_url=self.origin).status_code, 200)
        self.assertEqual(self.client.get('/admin', base_url=self.origin).location, '/ingresar')

    def test_proxy_https_links(self):
        headers = {'X-Forwarded-Proto': 'https'}
        response = self.client.get('/sitemap.xml', base_url='http://jerseysaurios.onrender.com', headers=headers)
        self.assertIn((self.origin + '/</loc>').encode(), response.data)
        response = self.client.get('/robots.txt', base_url='http://jerseysaurios.onrender.com', headers=headers)
        self.assertIn('Sitemap: ' + self.origin + '/sitemap.xml', response.text)
