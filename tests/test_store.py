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

    def test_multiple_sizes_delivery_server_prices_and_whatsapp(self):
        import html
        import re
        from urllib.parse import urlparse, parse_qs
        self.product()
        self.client.post('/productos/1/variante', data={'csrf_token':self.csrf,'sku':'JERSEY-L','size':'L','stock':'4'})
        self.product(sku='OTRO-S', name='Otro jersey', size='S', price='350.25')
        self.client.post('/admin/tienda', data={'csrf_token':self.csrf,'whatsapp':'525512345678','title':'Jerseysaurios'})
        buyer,token=self.buyer()
        for pid,qty in [('1','2'),('2','1'),('3','1')]:
            buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':pid,'quantity':qty})
        buyer.post('/carrito/actualizar',data={'csrf_token':token,'product_id':'3','quantity':'0'})
        buyer.post('/carrito/actualizar',data={'csrf_token':token,'product_id':'1','quantity':'3'})
        self.assertIn(b'$2,399.60',buyer.get('/carrito').data)
        with buyer.session_transaction() as s:
            key=s['checkout_key']
            self.assertEqual(s['cart'],{'1':3,'2':1})
        # Change the authoritative price after the cart was viewed.
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.execute('UPDATE products SET price_cents=60000 WHERE id=1')
        payload={'csrf_token':token,'checkout_key':key,'name':'Cliente sintético','phone':'5512345678',
                 'delivery_method':'envio','delivery_details':'Destinatario de prueba, Calle Ficticia 123, Centro, Ciudad de México, CDMX, 06000',
                 'total':'1','price_cents':'1'}
        result=buyer.post('/pedir',data=payload)
        self.assertTrue(result.location.startswith('/pedido/'))
        self.assertEqual(buyer.post('/pedir',data=payload).location,result.location)
        order=self.dbrow('SELECT * FROM orders')
        self.assertEqual(order['total_cents'],239990)
        self.assertEqual(order['delivery_details'],payload['delivery_details'])
        self.assertEqual(order['seller_decision'],'pendiente')
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],1)
        self.assertEqual(self.dbrow('SELECT stock FROM products WHERE id=1')[0],2)
        receipt=buyer.get(result.location).data.decode()
        self.assertIn('Folio #1',receipt)
        link=html.unescape(re.search(r'href="(https://wa.me/[^\"]+)"',receipt).group(1))
        self.assertEqual(urlparse(link).path,'/525512345678')
        message=parse_qs(urlparse(link).query)['text'][0]
        for expected in ('pedido #1','3 × Jersey local (M)','1 × Jersey local (L)','2399.90'):
            self.assertIn(expected,message)
        buyer.get(result.location)
        self.assertEqual(self.dbrow('SELECT seller_decision FROM orders')[0],'pendiente')
        self.assertIn(b'Cliente',self.client.get('/admin/pedidos').data)
        self.assertIn(payload['delivery_details'].encode(),self.client.get('/admin/pedidos/1').data)
        self.assertEqual(buyer.get('/admin/pedidos/1').status_code,302)
        self.assertEqual(buyer.post('/admin/pedidos/1',data={'csrf_token':token,'action':'confirm'}).status_code,302)
        self.assertEqual(self.dbrow('SELECT seller_decision FROM orders')[0],'pendiente')
        for _ in range(2):
            self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'confirm'})
        self.assertEqual(self.dbrow('SELECT seller_decision FROM orders')[0],'confirmado')
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'pendiente')
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM sales')[0],0)

    def test_reject_releases_inventory_once(self):
        self.product()
        self.order()
        for _ in range(2):
            self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'reject'})
        self.assertEqual(self.dbrow('SELECT status,seller_decision FROM orders')[:],('cancelado','rechazado'))
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],5)
        self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'confirm'})
        self.assertEqual(self.dbrow('SELECT seller_decision FROM orders')[0],'rechazado')

    def test_delivery_validation_and_atomic_multiple_stock(self):
        self.product()
        self.product(sku='OTRO-L',size='L')
        buyer,token=self.buyer()
        for pid in ('1','2'):
            buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':pid,'quantity':'2'})
        with buyer.session_transaction() as s:key=s['checkout_key']
        payload={'csrf_token':token,'checkout_key':key,'name':'Prueba','phone':'5512345678','delivery_method':'envio'}
        buyer.post('/pedir',data=payload)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],0)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.execute('UPDATE products SET stock=1 WHERE id=2')
        buyer.post('/pedir',data={**payload,'delivery_details':'Dirección sintética'})
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],0)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM clients')[0],0)
        self.assertEqual(self.dbrow('SELECT stock FROM products WHERE id=1')[0],5)

    def test_additive_order_schema_preserves_legacy_data(self):
        from pathlib import Path
        from negocio.store import initialize_store
        # Entirely synthetic legacy database, held in memory.
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.executescript(Path('tests/fixtures/schema_antes_jerarquia.sql').read_text())
            db.execute("INSERT INTO clients(id,name,phone,email) VALUES(1,'Prueba','5512345678','')")
            db.execute("INSERT INTO orders(id,token,checkout_key,client_id,total_cents) VALUES(1,'token-prueba','clave-prueba',1,12345)")
            before=dict(db.execute('SELECT * FROM orders').fetchone())
            initialize_store(db)
            initialize_store(db)
            after=dict(db.execute('SELECT * FROM orders').fetchone())
            self.assertEqual({k:after[k] for k in before},before)
            self.assertEqual([after[k] for k in ('delivery_method','delivery_details','seller_decision')],['','',''])

    def test_seller_can_confirm_after_payment(self):
        self.product()
        self.order()
        self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'payment','amount':'1199.80','method':'Efectivo'})
        self.assertEqual(self.dbrow('SELECT status FROM orders')[0],'pagado')
        self.assertIn(b'Confirmar pedido',self.client.get('/admin/pedidos/1').data)
        self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'confirm'})
        self.assertEqual(self.dbrow('SELECT seller_decision FROM orders')[0],'confirmado')
        self.client.post('/admin/pedidos/1',data={'csrf_token':self.csrf,'action':'reject'})
        self.assertEqual(self.dbrow('SELECT status,seller_decision FROM orders')[:],('pagado','confirmado'))
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],3)

    def test_simultaneous_checkout_creates_one_order(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.product()
        buyer,token=self.buyer()
        buyer.post('/carrito/agregar',data={'csrf_token':token,'product_id':'1','quantity':'2'})
        with buyer.session_transaction() as session:key=session['checkout_key']
        cookie=buyer.get_cookie(self.app.config['SESSION_COOKIE_NAME'])
        barrier=Barrier(2)
        def submit():
            client=self.app.test_client()
            client.set_cookie(self.app.config['SESSION_COOKIE_NAME'],cookie.value)
            barrier.wait(timeout=5)
            return client.post('/pedir',data={'csrf_token':token,'checkout_key':key,'name':'Prueba concurrente','phone':'5512345678'}).location
        with ThreadPoolExecutor(max_workers=2) as executor:
            receipts=list(executor.map(lambda _:submit(),range(2)))
        self.assertTrue(receipts[0].startswith('/pedido/'))
        self.assertEqual(receipts[0],receipts[1])
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],1)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM clients')[0],1)
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],3)

    def test_admin_confirmation_form_submits_action_without_button_value(self):
        from html.parser import HTMLParser

        class Forms(HTMLParser):
            def __init__(self):
                super().__init__()
                self.forms=[]
                self.current=None
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag=='form': self.current={}
                if tag=='input' and self.current is not None and attrs.get('name'):
                    self.current[attrs['name']]=attrs.get('value','')
            def handle_endtag(self,tag):
                if tag=='form' and self.current is not None:
                    self.forms.append(self.current)
                    self.current=None

        self.product(price='500.00')
        self.order(quantity=1)
        self.order(quantity=1)
        # Synthetic paid order, matching the reported $500 payment / $0 balance.
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.execute("INSERT INTO payments(order_id,amount_cents,method) VALUES(1,50000,'Efectivo')")
            db.execute("UPDATE orders SET status='pagado',seller_decision='',delivery_method='',delivery_details='' WHERE id=1")
        def snapshot():
            with sqlite3.connect(self.app.config['DATABASE']) as db:
                return {table:db.execute('SELECT * FROM '+table+' ORDER BY id').fetchall()
                        for table in ('payments','products','sales','order_items')}
        before=snapshot()
        for order_id in (1,2):
            parser=Forms()
            page=self.client.get(f'/admin/pedidos/{order_id}').data.decode()
            parser.feed(page)
            forms=[form for form in parser.forms if form.get('action')=='confirm']
            self.assertEqual(len(forms),1,'Confirmation must carry action as a hidden input')
            for _ in range(2):
                response=self.client.post(f'/admin/pedidos/{order_id}',data=forms[0],follow_redirects=True)
                self.assertNotIn('Acción inválida'.encode(),response.data)
            self.assertEqual(self.dbrow('SELECT seller_decision FROM orders WHERE id=?',(order_id,))[0],'confirmado')
        self.assertEqual(snapshot(),before)
        self.assertEqual(self.dbrow('SELECT status FROM orders WHERE id=1')[0],'pagado')
        self.assertEqual(self.dbrow('SELECT status FROM orders WHERE id=2')[0],'pendiente')
        self.assertIn(b'Sin datos registrados',self.client.get('/admin/pedidos/1').data)
        self.assertEqual(self.dbrow('SELECT delivery_method,delivery_details FROM orders WHERE id=1')[:],('',''))

    def test_checkout_rate_limit_per_ip(self):
        self.product(stock='50')
        codes=[self.order(1)[3].status_code for _ in range(6)]
        self.assertEqual(codes[:5],[302]*5)
        self.assertEqual(codes[5],429)
        self.assertEqual(self.dbrow('SELECT COUNT(*) FROM orders')[0],5)

    def test_stale_unpaid_orders_are_released_once(self):
        self.product()
        self.order(2);self.order(1)
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.execute("INSERT INTO payments(order_id,amount_cents,method) VALUES(2,100,'Efectivo')")
            db.execute("UPDATE orders SET created_at=datetime('now','localtime','-49 hours')")
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],2)
        self.app.extensions['stale_cleanup']['next']=0.0
        self.client.get('/admin/pedidos')
        self.assertEqual(self.dbrow('SELECT status FROM orders WHERE id=1')[0],'cancelado')
        self.assertEqual(self.dbrow('SELECT status FROM orders WHERE id=2')[0],'pendiente')
        self.assertEqual(self.dbrow('SELECT stock FROM products')[0],4)

    def test_cache_headers_and_inactive_category_image(self):
        self.product()
        anon,_=self.buyer()
        self.assertEqual(anon.get('/tienda/catalogo').headers['Cache-Control'],'no-cache')
        self.assertEqual(anon.get('/carrito').headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.get('/admin/pedidos').headers['Cache-Control'],'no-store')
        self.assertEqual(anon.get('/static/shop.css').headers['Cache-Control'],'public, max-age=604800')
        with sqlite3.connect(self.app.config['DATABASE']) as db:
            db.execute("INSERT INTO shop_categories(name,slug,image_path,active) VALUES('Inactiva','inactiva','x.jpg',0)")
        self.assertEqual(anon.get('/imagenes/x.jpg').status_code,404)
