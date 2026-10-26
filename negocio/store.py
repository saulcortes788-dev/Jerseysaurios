"""Tienda pública, variantes, pedidos y administración comercial."""
import secrets
import sqlite3
from urllib.parse import urlencode
from flask import request, session, render_template, redirect, url_for, flash, abort
from .media import save_image, save_product_image
from .categories import (initialize_categories, register_category_admin, category_rows, visibility_sql, descendants, assign_product_category)

CATEGORIES = ['Liga MX', 'Premier League', 'LaLiga', 'Serie A', 'Bundesliga', 'Ligue 1',
              'Selecciones nacionales', 'Jerseys retro', 'Nuevos lanzamientos', 'Ofertas']
SIZES = ('S', 'M', 'L', 'XL', 'XXL')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS shop_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shop_categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', image_path TEXT, credit TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS product_photos (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), image_path TEXT, source_url TEXT NOT NULL DEFAULT '', credit TEXT NOT NULL DEFAULT '', authorized INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, token TEXT NOT NULL UNIQUE, checkout_key TEXT NOT NULL UNIQUE, client_id INTEGER NOT NULL REFERENCES clients(id), status TEXT NOT NULL DEFAULT 'pendiente', total_cents INTEGER NOT NULL CHECK(total_cents>=0), created_at TEXT NOT NULL DEFAULT(datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, sku TEXT NOT NULL, size TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), price_cents INTEGER NOT NULL, cost_cents INTEGER);
CREATE TABLE IF NOT EXISTS refunds (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0), reference TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT(datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0), method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT(datetime('now','localtime')));
'''


def initialize_store(db):
    db.executescript(SCHEMA)
    columns = [('shop_categories', 'kind', "TEXT NOT NULL DEFAULT ''"), ('products', 'model_key', "TEXT NOT NULL DEFAULT ''"), ('products', 'season', "TEXT NOT NULL DEFAULT ''"),
               ('products', 'version', "TEXT NOT NULL DEFAULT 'Aficionado'"), ('products', 'kit', "TEXT NOT NULL DEFAULT 'Local'"),
               ('products', 'active', 'INTEGER NOT NULL DEFAULT 1'), ('products', 'featured', 'INTEGER NOT NULL DEFAULT 0'),
               ('products', 'is_new', 'INTEGER NOT NULL DEFAULT 0'), ('products', 'on_sale', 'INTEGER NOT NULL DEFAULT 0'),
               ('products', 'image_credit', "TEXT NOT NULL DEFAULT ''"), ('products', 'image_url', "TEXT NOT NULL DEFAULT ''"),
               ('sales', 'order_id', 'INTEGER REFERENCES orders(id)'), ('sales', 'voided', 'INTEGER NOT NULL DEFAULT 0')]
    for table, column, definition in columns:
        if column not in {r[1] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    for name in CATEGORIES:
        db.execute("UPDATE shop_categories SET kind=? WHERE name=? AND kind=''",(name,name))
    if not db.execute("SELECT 1 FROM shop_settings WHERE key='initialized'").fetchone():
        for name in CATEGORIES:
            db.execute('INSERT OR IGNORE INTO shop_categories(name,kind) VALUES(?,?)', (name,name))
        db.execute("INSERT INTO shop_settings VALUES('initialized','1')")
    db.commit()
    initialize_categories(db)


def register_store(app, get_db, money, integer):
    register_category_admin(app,get_db,integer)
    def settings():
        return dict(get_db().execute('SELECT key,value FROM shop_settings').fetchall())

    @app.context_processor
    def store_context():
        return {'shop': settings(), 'cart_count': sum(session.get('cart', {}).values())}

    def variants(p):
        if p['model_key']:
            visible,ids = visibility_sql(get_db())
            return get_db().execute('SELECT * FROM products WHERE active=1 AND model_key=? AND '+visible+' ORDER BY id', [p['model_key'],*ids]).fetchall()
        return [p]

    def cards(rows):
        groups = {}
        for p in rows:
            key = p['model_key'] or f"sku:{p['id']}"
            if key not in groups:
                groups[key] = {'product': p, 'variants': [], 'price': p['price_cents']}
            groups[key]['variants'].append(p)
            groups[key]['price'] = min(groups[key]['price'], p['price_cents'])
        return list(groups.values())

    @app.get('/')
    def shop_home():
        visible,ids = visibility_sql(get_db())
        rows = get_db().execute('SELECT * FROM products WHERE active=1 AND '+visible+' ORDER BY id DESC',ids).fetchall()
        return render_template('shop/home.html', cards=cards(rows), categories=[r for r in category_rows(get_db(),public=True) if r['parent_id'] is None], sections=get_db().execute('SELECT * FROM site_sections ORDER BY id').fetchall())

    @app.get('/categorias')
    def category_index():
        roots = [r for r in category_rows(get_db(),public=True) if r['parent_id'] is None]
        return render_template('shop/category_index.html',categories=roots)

    @app.get('/categorias/<path:category_path>')
    def category_page(category_path):
        category = next((r for r in category_rows(get_db(),public=True) if r['path']==category_path),None)
        if not category: abort(404)
        return catalog_response(category)

    @app.get('/tienda/catalogo')
    def shop_catalog():
        return catalog_response()

    def catalog_response(current=None):
        db = get_db()
        visible,ids = visibility_sql(db)
        clauses, args = ['active=1',visible], list(ids)
        filters = {f: (request.args.get(f, '').strip() if f=='category_path' else request.args.get(f, '').strip()[:200]) for f in ('q','league','team','selection','size','season','version','category','category_path','min','max')}
        public_rows = category_rows(db,public=True)
        if current:
            selected = current
        elif filters['category_path']:
            selected = next((r for r in public_rows if r['path']==filters['category_path']),None)
            if not selected: abort(404)
        elif filters['category']:
            selected = next((r for r in public_rows if r['parent_id'] is None and (r['name']==filters['category'] or r['kind']==filters['category'])),None)
            if not selected: abort(404)
        else:
            selected = None
        try:
            for f in ('league','team','selection','size','season','version'):
                if filters[f]: clauses.append(f'{f}=?'); args.append(filters[f])
            if selected:
                current = selected
                filters['category_path'] = selected['path']
                branch_ids = descendants(db,selected['id'],public=True)
                branch_clause = 'category_id IN ('+','.join('?' for _ in branch_ids)+')'
                if selected['kind']=='Ofertas':
                    clauses.append('('+branch_clause+' OR on_sale=1)')
                elif selected['kind']=='Nuevos lanzamientos':
                    clauses.append('('+branch_clause+' OR is_new=1)')
                elif selected['kind']=='Selecciones nacionales':
                    clauses.append('('+branch_clause+" OR selection!='')")
                else:
                    clauses.append(branch_clause)
                args.extend(branch_ids)
            if filters['q']:
                fields = ('name','sku','team','selection','league','season','version')
                clauses.append('('+' OR '.join(f'{f} LIKE ?' for f in fields)+')')
                args.extend([f"%{filters['q']}%"]*len(fields))
            for f,op in (('min','>='),('max','<=')):
                if filters[f]: clauses.append(f'price_cents{op}?'); args.append(money(filters[f]))
            if filters['min'] and filters['max'] and money(filters['min'])>money(filters['max']):
                raise ValueError('El precio mínimo supera al máximo.')
        except ValueError as exc:
            flash(str(exc),'error')
            return redirect(url_for('category_page',category_path=current['path']) if current else url_for('shop_catalog'))
        rows = db.execute('SELECT * FROM products WHERE '+' AND '.join(clauses)+' ORDER BY name,id',args).fetchall()
        options = {f:[r[0] for r in db.execute(f"SELECT DISTINCT {f} FROM products WHERE active=1 AND {visible} AND {f}!='' ORDER BY {f}",ids)] for f in ('league','team','selection','size','season','version')}
        crumbs = [r for r in public_rows if current and (current['path']==r['path'] or current['path'].startswith(r['path']+'/'))]
        children = [r for r in public_rows if current and r['parent_id']==current['id']]
        return render_template('shop/catalog.html',cards=cards(rows),filters=filters,options=options,categories=public_rows,current=current,breadcrumbs=crumbs,children=children)

    def public_product(product_id):
        visible,ids = visibility_sql(get_db())
        return get_db().execute('SELECT * FROM products WHERE id=? AND active=1 AND '+visible,[product_id,*ids]).fetchone()

    @app.get('/tienda/jersey/<int:product_id>')
    def shop_product(product_id):
        p = public_product(product_id)
        if not p: abort(404)
        v = variants(p)
        ids = [row['id'] for row in v]
        photos = get_db().execute('SELECT * FROM product_photos WHERE product_id IN ('+','.join('?' for _ in ids)+') AND image_path IS NOT NULL ORDER BY id', ids).fetchall()
        return render_template('shop/product.html', product=p, variants=v, photos=photos)

    def cart_rows():
        rows = []
        for pid, qty in session.get('cart', {}).items():
            p = get_db().execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
            if p: rows.append({'product': p, 'quantity': qty, 'total': qty*p['price_cents']})
        return rows

    @app.post('/carrito/agregar')
    def cart_add():
        try:
            pid = integer(request.form.get('product_id',''), 'Producto')
            qty = integer(request.form.get('quantity','1'), 'Cantidad', 100)
            p = public_product(pid)
            cart = dict(session.get('cart', {}))
            new = cart.get(str(pid), 0) + qty
            if not p or qty < 1 or new > p['stock'] or new > 100 or (str(pid) not in cart and len(cart)>=30):
                raise ValueError('No hay stock suficiente o se superó el límite del carrito.')
            if not cart: session['checkout_key'] = secrets.token_urlsafe(24)
            cart[str(pid)] = new; session['cart'] = cart
            flash('Jersey agregado al carrito.', 'success')
        except ValueError as exc: flash(str(exc), 'error')
        return redirect(url_for('cart_page'))

    @app.post('/carrito/actualizar')
    def cart_update():
        try:
            pid = str(integer(request.form.get('product_id',''), 'Producto'))
            qty = integer(request.form.get('quantity','0'), 'Cantidad', 100)
            cart = dict(session.get('cart', {}))
            if qty == 0: cart.pop(pid, None)
            elif pid in cart:
                p = get_db().execute('SELECT stock FROM products WHERE id=? AND active=1', (pid,)).fetchone()
                if not p or qty > p['stock']: raise ValueError('No hay stock suficiente.')
                cart[pid] = qty
            session['cart'] = cart
        except ValueError as exc: flash(str(exc), 'error')
        return redirect(url_for('cart_page'))

    @app.get('/carrito')
    def cart_page():
        session.setdefault('checkout_key', secrets.token_urlsafe(24))
        rows = cart_rows()
        return render_template('shop/cart.html', rows=rows, total=sum(r['total'] for r in rows))

    @app.post('/pedir')
    def checkout():
        db = get_db()
        key = request.form.get('checkout_key','')
        if not key or key != session.get('checkout_key'): abort(400)
        existing = db.execute('SELECT token FROM orders WHERE checkout_key=?', (key,)).fetchone()
        if existing: return redirect(url_for('order_receipt', token=existing['token']))
        try:
            name = request.form.get('name','').strip()[:100]
            phone = request.form.get('phone','').strip()[:40]
            email = request.form.get('email','').strip()[:120]
            if not name or len(phone)<7: raise ValueError('Completa tu nombre y teléfono de contacto.')
            if not session.get('cart'): raise ValueError('El carrito está vacío.')
            token = secrets.token_urlsafe(32)
            with db:
                db.execute('BEGIN IMMEDIATE')
                client = db.execute('SELECT id FROM clients WHERE phone=? AND name=?', (phone,name)).fetchone()
                client_id = client['id'] if client else db.execute('INSERT INTO clients(name,phone,email) VALUES(?,?,?)', (name,phone,email)).lastrowid
                order_id = db.execute('INSERT INTO orders(token,checkout_key,client_id,total_cents) VALUES(?,?,?,0)', (token,key,client_id)).lastrowid
                total = 0
                for pid, qty in session['cart'].items():
                    p = public_product(pid)
                    if not p or db.execute('UPDATE products SET stock=stock-? WHERE id=? AND stock>=? AND active=1', (qty,pid,qty)).rowcount != 1:
                        raise ValueError('El stock cambió. Revisa las cantidades del carrito.')
                    total += p['price_cents']*qty
                    db.execute('INSERT INTO order_items(order_id,product_id,name,sku,size,quantity,price_cents,cost_cents) VALUES(?,?,?,?,?,?,?,?)',
                               (order_id,pid,p['name'],p['sku'],p['size'],qty,p['price_cents'],p['cost_cents']))
                db.execute('UPDATE orders SET total_cents=? WHERE id=?', (total,order_id))
            session['cart'] = {}
            return redirect(url_for('order_receipt', token=token))
        except (ValueError, sqlite3.IntegrityError) as exc:
            flash(str(exc) if isinstance(exc,ValueError) else 'El pedido ya fue recibido. Revisa tu carrito.', 'error')
            return redirect(url_for('cart_page'))

    @app.get('/pedido/<token>')
    def order_receipt(token):
        order = get_db().execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
        if not order: abort(404)
        items = get_db().execute('SELECT * FROM order_items WHERE order_id=?', (order['id'],)).fetchall()
        text = f"Hola, quiero confirmar el pedido #{order['id']}:\n" + '\n'.join(f"{i['quantity']} × {i['name']} ({i['size']})" for i in items) + f"\nTotal MXN: ${order['total_cents']/100:.2f}"
        number = settings().get('whatsapp','')
        whatsapp = f'https://wa.me/{number}?' + urlencode({'text':text}) if number else None
        return render_template('shop/receipt.html', order=order, items=items, whatsapp=whatsapp)

    @app.get('/clientes/<int:client_id>')
    def client_history(client_id):
        client = get_db().execute('SELECT * FROM clients WHERE id=?',(client_id,)).fetchone()
        if not client: abort(404)
        sales = get_db().execute('SELECT * FROM sales WHERE client_id=? ORDER BY id DESC',(client_id,)).fetchall()
        orders = get_db().execute('SELECT * FROM orders WHERE client_id=? ORDER BY id DESC',(client_id,)).fetchall()
        return render_template('shop/client_history.html',client=client,sales=sales,orders=orders,active='clients')

    @app.get('/admin/pedidos')
    def orders_admin():
        rows = get_db().execute('SELECT o.*,c.name,c.phone,COALESCE((SELECT SUM(amount_cents) FROM payments WHERE order_id=o.id),0) paid FROM orders o JOIN clients c ON c.id=o.client_id ORDER BY o.id DESC').fetchall()
        return render_template('shop/orders.html', orders=rows, active='orders')

    @app.route('/admin/pedidos/<int:order_id>', methods=['GET','POST'])
    def order_admin(order_id):
        db = get_db()
        if request.method == 'POST':
            try:
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    order = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
                    if not order: abort(404)
                    paid = db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE order_id=?', (order_id,)).fetchone()[0]
                    action = request.form.get('action')
                    if action == 'payment':
                        amount = money(request.form.get('amount',''))
                        method = request.form.get('method','')
                        if order['status']!='pendiente' or amount<=0 or amount>order['total_cents']-paid or method not in ('Efectivo','Transferencia','Otro'):
                            raise ValueError('Pago inválido: revisa el saldo, importe y método.')
                        db.execute('INSERT INTO payments(order_id,amount_cents,method,reference) VALUES(?,?,?,?)', (order_id,amount,method,request.form.get('reference','')[:200]))
                        paid += amount
                        if paid == order['total_cents']:
                            recognize_sale(db, order)
                    elif action == 'status':
                        target = request.form.get('status')
                        if target == 'cancelado' and order['status']!='cancelado':
                            if paid:
                                reference = request.form.get('refund_reference','').strip()[:200]
                                if request.form.get('refund_confirm')!='yes' or not reference:
                                    raise ValueError('Confirma el reembolso manual y registra su referencia antes de cancelar un pedido con pagos.')
                                db.execute('INSERT INTO refunds(order_id,amount_cents,reference) VALUES(?,?,?)',(order_id,paid,reference))
                            db.execute('UPDATE sales SET voided=1 WHERE order_id=?',(order_id,))
                            for i in db.execute('SELECT * FROM order_items WHERE order_id=?', (order_id,)).fetchall():
                                db.execute('UPDATE products SET stock=stock+? WHERE id=?', (i['quantity'],i['product_id']))
                            db.execute("UPDATE orders SET status='cancelado' WHERE id=?", (order_id,))
                        elif (order['status'],target) in (('pagado','enviado'),('enviado','entregado')):
                            db.execute('UPDATE orders SET status=? WHERE id=?', (target,order_id))
                        elif target=='pagado' and order['status']=='pendiente' and order['total_cents']==0:
                            recognize_sale(db,order)
                        else: raise ValueError('Transición inválida: revisa el estado actual y los pagos del pedido.')
                    else: raise ValueError('Acción inválida.')
                flash('Pedido actualizado.', 'success')
            except ValueError as exc: flash(str(exc),'error')
            return redirect(url_for('order_admin', order_id=order_id))
        order = db.execute('SELECT o.*,c.name,c.phone FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.id=?', (order_id,)).fetchone()
        if not order: abort(404)
        items = db.execute('SELECT * FROM order_items WHERE order_id=?', (order_id,)).fetchall()
        payments = db.execute('SELECT * FROM payments WHERE order_id=? ORDER BY id', (order_id,)).fetchall()
        return render_template('shop/order_admin.html', order=order, items=items, payments=payments, paid=sum(p['amount_cents'] for p in payments), refund=db.execute('SELECT * FROM refunds WHERE order_id=?',(order_id,)).fetchone(), active='orders')

    def recognize_sale(db, order):
        for i in db.execute('SELECT * FROM order_items WHERE order_id=?', (order['id'],)).fetchall():
            db.execute('INSERT INTO sales(product_id,sku,product_name,quantity,unit_price_cents,total_cents,unit_cost_cents,client_id,order_id) VALUES(?,?,?,?,?,?,?,?,?)',
                       (i['product_id'],i['sku'],i['name'],i['quantity'],i['price_cents'],i['quantity']*i['price_cents'],i['cost_cents'],order['client_id'],order['id']))
        db.execute("UPDATE orders SET status='pagado' WHERE id=?", (order['id'],))

    @app.route('/admin/tienda', methods=['GET','POST'])
    def shop_settings():
        if request.method=='POST':
            try:
                phone = request.form.get('whatsapp','').strip()
                if phone and (not phone.isascii() or not phone.isdigit() or not 8<=len(phone)<=15):
                    raise ValueError('WhatsApp: usa de 8 a 15 dígitos con código de país, sin + ni espacios.')
                with get_db() as db:
                    for k,v in [('whatsapp',phone),('title',request.form.get('title','').strip()[:100]),('banner',request.form.get('banner','').strip()[:250])]:
                        db.execute('INSERT INTO shop_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
                flash('Configuración guardada.','success')
            except ValueError as exc: flash(str(exc),'error')
            return redirect(url_for('shop_settings'))
        return render_template('shop/settings.html', active='settings')

    @app.post('/productos/<int:product_id>/eliminar')
    def archive_product(product_id):
        with get_db() as db: db.execute('UPDATE products SET active=0 WHERE id=?',(product_id,))
        flash('Producto retirado de la tienda. Su historial se conserva.','success')
        return redirect(url_for('products'))

    @app.post('/productos/<int:product_id>/reactivar')
    def restore_product(product_id):
        with get_db() as db: db.execute('UPDATE products SET active=1 WHERE id=?',(product_id,))
        return redirect(url_for('products'))

    @app.post('/productos/<int:product_id>/variante')
    def add_variant(product_id):
        db = get_db()
        p = db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
        if not p: abort(404)
        try:
            size = request.form.get('size','')
            sku = request.form.get('sku','').strip().upper()[:40]
            stock = integer(request.form.get('stock','0'),'Stock')
            if size not in SIZES or not sku: raise ValueError('Selecciona talla y SKU único.')
            with db:
                key = p['model_key'] or f"modelo-{p['id']}"
                if db.execute('SELECT id FROM products WHERE model_key=? AND size=? AND active=1',(key,size)).fetchone() or (p['size']==size and p['active']):
                    raise ValueError('Ya existe esa talla para este modelo.')
                db.execute('UPDATE products SET model_key=? WHERE id=?',(key,p['id']))
                fields = ['name','team','price_cents','minimum_stock','cost_cents','description','category','selection','league','brand','source_url','image_path','season','version','kit','featured','is_new','on_sale','image_credit','category_id']
                cols = ','.join(fields+['sku','size','stock','model_key'])
                db.execute(f"INSERT INTO products({cols}) VALUES({','.join('?' for _ in range(len(fields)+4))})", (*[p[f] for f in fields],sku,size,stock,key))
            flash('Variante creada con precio y costo del modelo.','success')
        except (ValueError,sqlite3.IntegrityError) as exc: flash(str(exc) if isinstance(exc,ValueError) else 'El SKU ya existe.','error')
        return redirect(url_for('product_details',product_id=product_id))

    @app.post('/productos/<int:product_id>/galeria')
    def add_photo(product_id):
        db = get_db()
        if not db.execute('SELECT id FROM products WHERE id=?',(product_id,)).fetchone(): abort(404)
        try:
            if request.form.get('authorized')!='yes': raise ValueError('Confirma que tienes autorización para usar esta imagen.')
            image = save_product_image(request.files.get('image'), app.config['UPLOAD_FOLDER'], product_id)
            if not image: raise ValueError('Selecciona una imagen local.')
            with db: db.execute('INSERT INTO product_photos(product_id,image_path,source_url,credit,authorized) VALUES(?,?,?,?,1)',(product_id,image,request.form.get('source_url','')[:2000],request.form.get('credit','')[:500]))
            flash('Fotografía añadida con sus referencias.','success')
        except ValueError as exc: flash(str(exc),'error')
        return redirect(url_for('product_details',product_id=product_id))
