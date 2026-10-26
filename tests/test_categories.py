import sqlite3
import unittest
from pathlib import Path
import test_app
from app import create_app
from negocio.categories import INITIAL_CATEGORIES, category_rows, ensure_category, seed_categories


class CategoryTests(unittest.TestCase):
    setUp=test_app.BusinessAppTests.setUp
    tearDown=test_app.BusinessAppTests.tearDown
    product=test_app.BusinessAppTests.product

    def query(self,sql,args=()):
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.row_factory=sqlite3.Row
            return db.execute(sql,args).fetchall()

    def create(self,name,parent=None,**kwargs):
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'name':name,'parent_id':str(parent) if parent else '', 'sort_order':'0',**kwargs})
        return self.query('SELECT * FROM shop_categories WHERE name=? AND parent_id IS ?',(name,parent))[0]

    def buyer(self):
        buyer=self.app.test_client();buyer.get('/')
        with buyer.session_transaction() as session: token=session['csrf_token']
        return buyer,token

    def test_seed_idempotent_and_preserves_admin_edits(self):
        self.assertEqual(len(INITIAL_CATEGORIES),30)
        for name in INITIAL_CATEGORIES:
            self.assertEqual(len(self.query('SELECT id FROM shop_categories WHERE name=? AND parent_id IS NULL',(name,))),1)
        count=len(self.query('SELECT id FROM shop_categories'))
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.row_factory=sqlite3.Row
            self.assertEqual(seed_categories(db),0)
            self.assertEqual(seed_categories(db),0)
            db.execute("UPDATE shop_categories SET active=0,sort_order=99,name='Liga personalizada' WHERE slug='laliga'")
            seed_categories(db)
        self.assertEqual(len(self.query('SELECT id FROM shop_categories')),count)
        row=self.query("SELECT * FROM shop_categories WHERE slug='laliga'")[0]
        self.assertEqual((row['name'],row['active'],row['sort_order']),('Liga personalizada',0,99))
        create_app({'TESTING':True,'DATABASE':self.app.config['DATABASE']})
        self.assertEqual(len(self.query('SELECT id FROM shop_categories')),count)

    def test_repeated_names_deep_tree_and_breadcrumbs(self):
        liga=self.query("SELECT id FROM shop_categories WHERE name='LaLiga'")[0][0]
        a=self.create('Equipo A de prueba',liga)
        b=self.create('Equipo B de prueba',liga)
        season_a=self.create('2026-27',a['id'])
        season_b=self.create('2026-27',b['id'])
        self.assertNotEqual(season_a['id'],season_b['id'])
        self.create('2026-27',a['id'])
        self.assertEqual(len(self.query('SELECT id FROM shop_categories WHERE parent_id=?',(a['id'],))),1)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.row_factory=sqlite3.Row
            parent=season_a['id']
            for index in range(20):
                parent=ensure_category(db,f'Nivel local de prueba {index}',parent)
            leaf=next(r for r in category_rows(db) if r['id']==parent)
        response=self.client.get('/categorias/'+leaf['path'])
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Equipo A de prueba',response.data)
        self.assertEqual(self.client.get('/tienda/catalogo',query_string={'category_path':leaf['path']}).status_code,200)
        self.assertEqual(self.client.get('/admin/categorias').status_code,200)

    def test_cycle_prevention_move_order_and_delete_rules(self):
        root=self.create('Organización de prueba')
        child=self.create('Equipo de prueba',root['id'])
        other=self.create('Otra rama de prueba')
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':root['id'],'name':root['name'],'parent_id':child['id'],'sort_order':'0'})
        self.assertIsNone(self.query('SELECT parent_id FROM shop_categories WHERE id=?',(root['id'],))[0][0])
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE shop_categories SET parent_id=? WHERE id=?',(child['id'],root['id']))
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':root['id'],'action':'delete'})
        self.assertEqual(len(self.query('SELECT id FROM shop_categories WHERE id=?',(root['id'],))),1)
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':child['id'],'name':child['name'],'parent_id':other['id'],'sort_order':'7'})
        self.assertEqual(self.query('SELECT parent_id FROM shop_categories WHERE id=?',(child['id'],))[0][0],other['id'])
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':root['id'],'action':'delete'})
        self.assertEqual(self.query('SELECT id FROM shop_categories WHERE id=?',(root['id'],)),[])
        second=self.create('Segundo equipo',other['id'],sort_order='8')
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':second['id'],'action':'up'})
        first=self.query('SELECT id FROM shop_categories WHERE parent_id=? ORDER BY sort_order,id',(other['id'],))[0][0]
        self.assertEqual(first,second['id'])

    def test_product_descendants_hidden_branches_and_search(self):
        root=self.create('Colección de prueba')
        team=self.create('Equipo local de prueba',root['id'])
        season=self.create('2026-27',team['id'])
        jersey=self.create('Visitante',season['id'])
        self.product(category_id=str(jersey['id']),name='Jersey verificable',league='Liga de prueba',season='2026-27',version='Jugador',kit='Visitante')
        buyer,token=self.buyer()
        for path in ('/categorias','/categorias/coleccion-de-prueba','/categorias/coleccion-de-prueba/equipo-local-de-prueba/2026-27/visitante'):
            response=buyer.get(path)
            self.assertEqual(response.status_code,200,path)
        self.assertIn(b'Jersey verificable',buyer.get('/categorias/coleccion-de-prueba').data)
        for query in ({'q':'2026-27'},{'q':'Jugador'},{'league':'Liga de prueba','season':'2026-27','version':'Jugador'}):
            self.assertIn(b'Jersey verificable',buyer.get('/tienda/catalogo',query_string=query).data)
        self.assertNotIn(b'Jersey verificable',buyer.get('/tienda/catalogo?version=Aficionado').data)
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':root['id'],'action':'toggle'})
        self.assertEqual(buyer.get('/categorias/coleccion-de-prueba').status_code,404)
        self.assertEqual(buyer.get('/tienda/jersey/1').status_code,404)
        self.assertNotIn(b'Jersey verificable',buyer.get('/tienda/catalogo').data)
        buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':'1','quantity':'1'})
        with buyer.session_transaction() as sess:self.assertFalse(sess.get('cart'))
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':root['id'],'action':'toggle'})
        self.assertEqual(buyer.get('/tienda/jersey/1').status_code,200)
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':jersey['id'],'action':'delete'})
        self.assertTrue(self.query('SELECT id FROM shop_categories WHERE id=?',(jersey['id'],)))
        self.assertEqual(buyer.get('/admin/categorias').status_code,302)
        self.assertEqual(buyer.post('/admin/categorias',data={'name':'Sin CSRF'}).status_code,400)

    def test_flat_schema_migration_preserves_ids_and_product_metadata(self):
        path=Path(self.temp_dir.name)/'anterior.sqlite3'
        with sqlite3.connect(path) as db:
            db.executescript((Path(__file__).parent/'fixtures/schema_antes_jerarquia.sql').read_text())
            db.execute("ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE products ADD COLUMN league TEXT NOT NULL DEFAULT ''")
            db.execute("INSERT INTO shop_categories(id,name,image_path,credit) VALUES(42,'LaLiga','original.jpg','Autor original')")
            db.execute("INSERT INTO products(sku,name,team,size,price_cents,stock,category,league) VALUES('LEGADO','Legado','Equipo existente','M',12345,7,'LaLiga','LaLiga')")
        migrated=create_app({'TESTING':True,'DATABASE':str(path)})
        create_app({'TESTING':True,'DATABASE':str(path)})
        with sqlite3.connect(path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT * FROM shop_categories WHERE id=42').fetchone()
            self.assertEqual((row['name'],row['image_path'],row['credit']),('LaLiga','original.jpg','Autor original'))
            product=db.execute('SELECT * FROM products').fetchone()
            self.assertEqual((product['id'],product['stock'],product['price_cents'],product['category']),(1,7,12345,'LaLiga'))
            self.assertIsNotNone(product['category_id'])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(migrated.test_client().get('/categorias/laliga').status_code,200)

    def test_inactive_category_is_rechecked_at_checkout_and_legacy_selection_survives(self):
        root=self.create('Rama temporal de prueba')
        self.product(category_id=str(root['id']),selection='Selección local de prueba')
        buyer,token=self.buyer()
        self.assertIn(b'Jersey local',buyer.get('/tienda/catalogo?category=Selecciones+nacionales').data)
        buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':'1','quantity':'1'})
        buyer.get('/carrito')
        with buyer.session_transaction() as sess:key=sess['checkout_key']
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'category_id':root['id'],'action':'toggle'})
        buyer.post('/pedir',data={'csrf_token':token,'checkout_key':key,'name':'Prueba','phone':'5512345678'})
        self.assertEqual(self.query('SELECT COUNT(*) FROM orders')[0][0],0)
        self.assertEqual(self.query('SELECT stock FROM products')[0][0],5)
