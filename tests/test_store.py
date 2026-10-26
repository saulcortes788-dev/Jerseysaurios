import sqlite3
import unittest
import test_app


class StoreTests(unittest.TestCase):
    setUp=test_app.BusinessAppTests.setUp
    tearDown=test_app.BusinessAppTests.tearDown
    product=test_app.BusinessAppTests.product

    def dbrow(self,sql,args=()):
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.row_factory=sqlite3.Row
            return db.execute(sql,args).fetchone()

    def buyer(self):
        client=self.app.test_client();client.get('/')
        with client.session_transaction() as s: token=s['csrf_token']
        return client,token

    def order(self,quantity=2):
        buyer,token=self.buyer()
        buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':'1','quantity':str(quantity)})
        buyer.get('/carrito')
        with buyer.session_transaction() as s:key=s['checkout_key']
        payload={'csrf_token':token,'checkout_key':key,'name':'Cliente de prueba','phone':'5512345678'}
        result=buyer.post('/pedir',data=payload)
        return buyer,token,payload,result

    def test_public_store_admin_protection_and_filters(self):
        self.product(cost='200')
        buyer,token=self.buyer()
        for page in ['/','/tienda/catalogo','/tienda/jersey/1','/carrito']:
            self.assertEqual(buyer.get(page).status_code,200)
        for page in ['/admin','/admin/pedidos','/admin/categorias','/admin/tienda','/productos','/exportar/ventas.csv']:
            self.assertEqual(buyer.get(page).status_code,302)
        self.assertNotIn(b'Jersey local',buyer.get('/tienda/catalogo?min=800').data)
        self.assertIn(b'Jersey local',buyer.get('/tienda/catalogo?max=600&size=M').data)
        self.assertEqual(buyer.post('/carrito/agregar',data={'product_id':'1'}).status_code,400)

    def test_checkout_atomic_idempotent_and_second_order(self):
        self.product(cost='200')
        buyer,token,payload,result=self.order()
        self.assertEqual(result.status_code,302)
        self.assertTrue(result.location.startswith('/pedido/'))
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],3)
        self.assertEqual(self.dbrow('SELECT total_cents FROM orders')[0],119980)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM sales')[0],0)
        self.assertEqual(buyer.post('/pedir',data=payload).location,result.location)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],1)
        buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':'1','quantity':'1'})
        buyer.get('/carrito')
        with buyer.session_transaction() as s:key=s['checkout_key']
        buyer.post('/pedir',data={**payload,'checkout_key':key})
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],2)
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],2)

    def test_stock_race_rolls_back_order_and_customer(self):
        self.product()
        buyer,token=self.buyer()
        buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':'1','quantity':'5'})
        buyer.get('/carrito')
        with buyer.session_transaction() as s:key=s['checkout_key']
        self.client.post('/ventas',data={'csrf_token':self.csrf,'product_id':'1','quantity':'1'})
        buyer.post('/pedir',data={'csrf_token':token,'checkout_key':key,'name':'Cliente','phone':'5512345678'})
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],0)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM clients')[0],0)
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],4)

    def test_payments_states_refunds_and_reporting(self):
        self.product(cost='200')
        self.order()
        def post(**data):return self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,**data})
        post(action='payment',amount='500',method='Transferencia')
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'pendiente')
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM sales')[0],0)
        post(action='payment',amount='699.80',method='Efectivo')
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'pagado')
        self.assertEqual(self.dbrow('SELECT SUM(total_cents) FROM sales')[0],119980)
        self.assertIn(b'$799.80',self.client.get('/reportes').data)
        post(action='payment',amount='1',method='Efectivo')
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM payments')[0],2)
        post(action='status',status='enviado');post(action='status',status='entregado')
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'entregado')
        post(action='status',status='cancelado')
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'entregado')
        post(action='status',status='cancelado',refund_confirm='yes',refund_reference='Prueba devolución recibida')
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'cancelado')
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],5)
        self.assertEqual(self.dbrow('SELECT amount_cents FROM refunds')[0],119980)
        self.assertIn(b'$0.00',self.client.get('/reportes').data)
        post(action='status',status='cancelado',refund_confirm='yes',refund_reference='Duplicado')
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],5)

    def test_pending_cancellation_restocks_once(self):
        self.product()
        self.order()
        for _ in range(2):self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'status','status':'cancelado'})
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],5)

    def test_variants_archive_and_settings(self):
        self.product()
        self.client.post('/productos/1/variante',data={'csrf_token':self.csrf,'sku':'OTRA-L','size':'L','stock':'3'})
        key=self.dbrow('SELECT model_key FROM products WHERE id=1')[0]
        self.assertTrue(key)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM products WHERE model_key=?',(key,))[0],2)
        self.assertIn(b'L',self.client.get('/tienda/jersey/1').data)
        self.client.post('/productos/1/eliminar',data={'csrf_token':self.csrf})
        self.assertEqual(self.client.get('/tienda/jersey/1').status_code,404)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM products')[0],2)
        self.client.post('/admin/tienda',data={'csrf_token':self.csrf,'title':'Tienda prueba','whatsapp':'525512345678','banner':'Texto de prueba'})
        self.assertIn(b'Tienda prueba',self.client.get('/').data)
        for page in ['/admin','/admin/categorias','/admin/tienda','/admin/pedidos','/productos/2/ficha']:
            self.assertEqual(self.client.get(page).status_code,200,page)

    def test_category_image_credits_and_customer_history(self):
        import io
        from pathlib import Path
        from PIL import Image
        photo=io.BytesIO();exif=Image.Exif();exif[33432]='Copyright de prueba'
        Image.new('RGB',(20,20),'blue').save(photo,'JPEG',exif=exif);photo.seek(0)
        self.client.post('/admin/categorias',data={'csrf_token':self.csrf,'name':'Categoría de prueba','credit':'Autor visible','image':(photo,'foto.jpg')})
        category=self.dbrow('SELECT * FROM shop_categories WHERE name=?',('Categoría de prueba',))
        self.assertEqual(category['credit'],'Autor visible')
        with Image.open(Path(self.app.config['UPLOAD_FOLDER'])/category['image_path']) as image:
            self.assertEqual(image.getexif()[33432],'Copyright de prueba')
        self.assertTrue((Path(self.app.config['UPLOAD_FOLDER'])/'.originales'/(category['image_path']+'.original')).exists())
        self.product();self.order()
        self.assertEqual(self.client.get('/clientes/1').status_code,200)
        buyer,token=self.buyer()
        self.assertEqual(buyer.get('/clientes/1').status_code,302)
        self.assertEqual(buyer.get('/imagenes/.originales/'+category['image_path']+'.original').status_code,404)

    def test_demo_loader_is_explicit_and_idempotent(self):
        from cargar_demo import load_demo
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM products')[0],0)
        load_demo(self.app.config['DATABASE']);load_demo(self.app.config['DATABASE'])
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM products')[0],5)
        self.assertIn(b'[DEMOSTRACI',self.client.get('/').data)
