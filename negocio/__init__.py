"""Control de Negocio: panel local para inventario y ventas.

Ejecutar: python app.py
"""
from __future__ import annotations

import csv
import io
import os
import secrets
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import (
    Flask, Response, abort, flash, g, redirect, render_template,
    request, session, url_for, send_from_directory,
)

from .store import initialize_store, register_store
from werkzeug.exceptions import SecurityError
from .commands import register_commands
from .categories import assign_product_category
from .media import save_image
from .importer import register_importer
from .access import register_access

BASE_DIR = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
 id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS site_sections (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', image_path TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    team TEXT NOT NULL,
    size TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
    stock INTEGER NOT NULL CHECK(stock >= 0),
    minimum_stock INTEGER NOT NULL DEFAULT 3 CHECK(minimum_stock >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
    total_cents INTEGER NOT NULL CHECK(total_cents >= 0),
    sold_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS clients (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY, description TEXT NOT NULL, category TEXT NOT NULL,
 amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), spent_on TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sold_at DESC);
"""


def parse_nonnegative_integer(value: str, label: str, upper: int = 1_000_000) -> int:
    value = (value or "").strip()
    if not value.isdigit():
        raise ValueError(f"{label}: introduce un número entero válido.")
    number = int(value)
    if number > upper:
        raise ValueError(f"{label}: el número es demasiado grande.")
    return number


def parse_money(value: str) -> int:
    try:
        money = Decimal((value or "").strip())
        if not money.is_finite() or money < 0 or money > 10_000_000:
            raise ValueError("Introduce un precio entre $0 y $10,000,000 MXN.")
        cents = money * 100
        if cents != cents.to_integral_value():
            raise ValueError("El precio debe tener máximo dos decimales.")
        return int(cents)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(str(exc) if isinstance(exc, ValueError) else "Introduce un precio válido, por ejemplo 499.90.") from exc


def peso(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
    overrides = test_config or {}
    production = overrides.get('PRODUCTION', os.environ.get('JERSEY_ENV','').strip().lower() == 'production')
    data_dir = Path(overrides.get('DATA_DIR') or os.environ.get('JERSEY_DATA_DIR') or BASE_DIR / 'data').expanduser().resolve()
    data_dir.mkdir(parents=True,exist_ok=True)
    secret = overrides.get('SECRET_KEY') or os.environ.get('SECRET_KEY')
    if production and (not secret or len(secret)<32):
        raise RuntimeError('En producción configura SECRET_KEY con al menos 32 caracteres aleatorios.')
    if not secret:
        key_file = data_dir / '.secret_key'
        if not key_file.exists():
            try:
                fd = os.open(key_file,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as handle:
                    handle.write(secrets.token_hex(32))
            except FileExistsError:
                pass
        secret = key_file.read_text(encoding='utf-8').strip()
    app.config.update(
        SECRET_KEY=secret,
        DATA_DIR=str(data_dir),
        PRODUCTION=production,
        DATABASE=str(data_dir / 'tienda.sqlite3'),
        MAX_CONTENT_LENGTH=8*1024*1024,
        UPLOAD_FOLDER=str(data_dir / 'uploads'),
        IMPORT_FOLDER=str(data_dir / 'importaciones'),
        SESSION_COOKIE_SECURE=production,
        HIDE_DEMO=production,
        TRUST_PROXY=os.environ.get('JERSEY_TRUST_PROXY','') == '1',
    )
    app.config.update(overrides)
    if app.config['TRUST_PROXY']:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
    hosts = os.environ.get('JERSEY_TRUSTED_HOSTS','').split(',')
    render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME','')
    trusted = [h.strip() for h in hosts if h.strip()] + ([render_host] if render_host else [])
    if trusted:
        app.config['TRUSTED_HOSTS'] = trusted

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"], timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        existing = {r[1] for r in db.execute("PRAGMA table_info(products)")}
        if existing and ('image_path' not in existing or 'description' not in existing or 'model_key' not in existing or 'category_id' not in existing):
            backup_path = Path(app.config['DATABASE']).with_name('respaldo_antes_jerarquia_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
            with sqlite3.connect(backup_path) as backup:
                db.backup(backup)
        db.executescript(SCHEMA)
        # Migración aditiva: conserva todos los productos y ventas existentes.
        for table, column, definition in [
            *[('products', field, "TEXT NOT NULL DEFAULT ''") for field in ('selection', 'league', 'brand', 'category', 'source_url', 'description')],
            ('products', 'image_path', 'TEXT'),
            ("products", "cost_cents", "INTEGER CHECK(cost_cents >= 0)"),
            ("sales", "unit_cost_cents", "INTEGER CHECK(unit_cost_cents >= 0)"),
            ("sales", "client_id", "INTEGER REFERENCES clients(id)")]:
            if column not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        db.commit()
        initialize_store(db)

    @app.context_processor
    def add_context():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"], "peso": peso}

    @app.before_request
    def csrf_protection():
        if isinstance(request.routing_exception,SecurityError):
            raise request.routing_exception
        if request.method == "POST":
            sent = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not secrets.compare_digest(sent, expected):
                abort(400, description="Formulario inválido. Recarga la página e inténtalo nuevamente.")

    register_commands(app,get_db)
    register_access(app, get_db)
    register_importer(app, get_db, parse_money, parse_nonnegative_integer)
    register_store(app, get_db, parse_money, parse_nonnegative_integer)

    @app.get('/salud')
    def health():
        try:
            get_db().execute('SELECT 1').fetchone()
            return {'status':'ok'},200
        except sqlite3.Error:
            return {'status':'unavailable'},503

    PUBLIC_PAGES = {'sitemap', 'robots', 'shop_home', 'shop_catalog', 'shop_product', 'category_index', 'category_page'}

    def cache_policy(response):
        """no-store para admin, carrito, checkout, recibos y sesiones de admin; caché larga solo para archivos públicos."""
        if session.get('admin_id'):
            return 'no-store'
        if request.endpoint in ('static', 'product_image') and response.status_code in (200, 304):
            return 'public, max-age=604800'
        if request.endpoint in PUBLIC_PAGES and response.status_code == 200:
            return 'no-cache'
        return 'no-store'

    @app.after_request
    def protect_response(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = cache_policy(response)
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if app.config['PRODUCTION']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000' 
        return response

    @app.errorhandler(400)
    def invalid_request(error):
        if isinstance(error,SecurityError):
            return 'Solicitud no válida.',400
        return render_template('shop/error.html',title='Revisa el formulario',message='La solicitud no es válida o el formulario expiró. Recarga la página e inténtalo de nuevo.'), 400

    @app.errorhandler(404)
    def missing_page(error):
        return render_template('shop/error.html',title='No encontramos esta página',message='El producto o enlace no está disponible.'), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template('shop/error.html',title='No pudimos completar la operación',message='Inténtalo nuevamente y revisa el estado del pedido antes de repetir un pago.'), 500

    @app.get("/admin")
    def dashboard():
        db = get_db()
        stats = db.execute("""
            SELECT COUNT(*) AS products, COALESCE(SUM(stock), 0) AS units,
            COALESCE(SUM(CASE WHEN stock <= minimum_stock THEN 1 ELSE 0 END), 0) AS low
            FROM products WHERE active=1
        """).fetchone()
        sales = db.execute("""
            SELECT COUNT(*) AS operations, COALESCE(SUM(quantity),0) AS units_sold,
                   COALESCE(SUM(total_cents),0) AS revenue FROM sales WHERE voided=0
        """).fetchone()
        low_stock = db.execute("""
            SELECT * FROM products WHERE active=1 AND stock <= minimum_stock ORDER BY stock ASC, name LIMIT 6
        """).fetchall()
        recent = db.execute("SELECT * FROM sales WHERE voided=0 ORDER BY id DESC LIMIT 6").fetchall()
        return render_template("dashboard.html", stats=stats, sales=sales,
                               low_stock=low_stock, recent=recent, active="dashboard",
                               finance=db.execute("SELECT COALESCE(SUM(total_cents),0) revenue, COALESCE(SUM(quantity*unit_cost_cents),0) cost, SUM(CASE WHEN unit_cost_cents IS NULL THEN 1 ELSE 0 END) missing FROM sales WHERE voided=0").fetchone(),
                               expenses=db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM expenses").fetchone()[0],
                               best=db.execute("SELECT product_name,SUM(quantity) units FROM sales WHERE voided=0 GROUP BY product_name ORDER BY units DESC LIMIT 5").fetchall())

    @app.get("/productos")
    def products():
        q = request.args.get("q", "").strip()[:80]
        db = get_db()
        if q:
            matches = db.execute("""
                SELECT * FROM products WHERE name LIKE ? OR team LIKE ? OR sku LIKE ?
                ORDER BY name, size
            """, [f"%{q}%"] * 3).fetchall()
        else:
            matches = db.execute("SELECT * FROM products ORDER BY name, size").fetchall()
        return render_template("products.html", items=matches, q=q, active="products")

    @app.post("/productos/agregar")
    def add_product():
        sku = request.form.get("sku", "").strip().upper()[:40]
        name = request.form.get("name", "").strip()[:100]
        team = request.form.get("team", "").strip()[:100]
        size = request.form.get("size", "").strip().upper()[:20]
        try:
            if not all([sku, name, team, size]):
                raise ValueError("Completa SKU, nombre, equipo y talla.")
            cost = parse_money(request.form["cost"]) if request.form.get("cost", "").strip() else None
            price = parse_money(request.form.get("price", ""))
            stock = parse_nonnegative_integer(request.form.get("stock", ""), "Existencias")
            minimum = parse_nonnegative_integer(request.form.get("minimum_stock", ""), "Mínimo")
            db = get_db()
            image_path = None
            with db:
                cursor = db.execute("""
                    INSERT INTO products(sku,name,team,size,price_cents,stock,minimum_stock,cost_cents)
                    VALUES(?,?,?,?,?,?,?,?)
                """, (sku, name, team, size, price, stock, minimum, cost))
                db.execute('UPDATE products SET description=?,season=?,version=?,kit=?,model_key=?,featured=?,is_new=?,on_sale=?,image_credit=? WHERE id=?',
                    (request.form.get('description','')[:5000], request.form.get('season','')[:30], request.form.get('version','Aficionado')[:30],request.form.get('kit','Local')[:30],request.form.get('model_key','')[:100],int('featured' in request.form),int('is_new' in request.form),int('on_sale' in request.form),request.form.get('image_credit','')[:500],cursor.lastrowid))
                image_path = save_image(request.files.get('image'), app.config['UPLOAD_FOLDER'])
                db.execute("UPDATE products SET selection=?,league=?,brand=?,category=?,source_url=?,image_path=? WHERE id=?", (
                    *[request.form.get(f, '').strip()[:200] for f in ('selection', 'league', 'brand', 'category', 'source_url')], image_path, cursor.lastrowid))
                assign_product_category(db,cursor.lastrowid,request.form.get('category_id'),derive=not request.form.get('category_id'))
            flash("Producto agregado correctamente.", "success")
        except sqlite3.IntegrityError:
            flash("Ya existe un producto con ese SKU. Utiliza uno diferente.", "error")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("products"))

    @app.post("/productos/<int:product_id>/actualizar")
    def update_product(product_id: int):
        try:
            cost = parse_money(request.form["cost"]) if request.form.get("cost", "").strip() else None
            price = parse_money(request.form.get("price", ""))
            stock = parse_nonnegative_integer(request.form.get("stock", ""), "Existencias")
            minimum = parse_nonnegative_integer(request.form.get("minimum_stock", ""), "Mínimo")
            db = get_db()
            with db:
                affected = db.execute("""
                    UPDATE products SET price_cents=?, stock=?, minimum_stock=?, cost_cents=? WHERE id=?
                """, (price, stock, minimum, cost, product_id)).rowcount
            flash("Producto actualizado." if affected else "El producto no existe.",
                  "success" if affected else "error")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("products"))

    @app.route("/ventas", methods=["GET", "POST"])
    def sales_page():
        db = get_db()
        if request.method == "POST":
            try:
                product_id = parse_nonnegative_integer(request.form.get("product_id", ""), "Producto")
                quantity = parse_nonnegative_integer(request.form.get("quantity", ""), "Cantidad", 100_000)
                if quantity == 0:
                    raise ValueError("La cantidad debe ser mayor que cero.")
                client_id = request.form.get("client_id", "")
                client_id = parse_nonnegative_integer(client_id, "Cliente") if client_id else None
                if client_id is not None and not db.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone():
                    raise ValueError("El cliente no existe.")
                with db:
                    # Descuento condicionado para evitar vender más existencias de las disponibles.
                    result = db.execute("""
                        UPDATE products SET stock=stock-?
                        WHERE id=? AND active=1 AND stock>=?
                    """, (quantity, product_id, quantity))
                    if result.rowcount != 1:
                        raise ValueError("No hay existencias suficientes o el producto no existe.")
                    p = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    db.execute("""
                        INSERT INTO sales(product_id,sku,product_name,quantity,unit_price_cents,total_cents,unit_cost_cents,client_id)
                        VALUES(?,?,?,?,?,?,?,?)
                    """, (product_id, p["sku"], p["name"], quantity, p["price_cents"],
                          quantity * p["price_cents"], p["cost_cents"], client_id))
                flash(f"Venta registrada: {quantity} pieza(s), total {peso(quantity * p['price_cents'])}.", "success")
                return redirect(url_for("sales_page"))
            except ValueError as exc:
                flash(str(exc), "error")
        items = db.execute("SELECT * FROM products WHERE active=1 AND stock>0 ORDER BY name, size").fetchall()
        history = db.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 100").fetchall()
        return render_template("sales.html", items=items, history=history, clients=db.execute("SELECT * FROM clients ORDER BY name").fetchall(), active="sales")

    @app.get("/exportar/<kind>.csv")
    def export_csv(kind: str):
        db = get_db()
        if kind == "productos":
            headers = ["SKU", "Nombre", "Equipo", "Talla", "Precio MXN", "Existencias", "Mínimo"]
            rows = db.execute("""SELECT sku,name,team,size,price_cents,stock,minimum_stock
                                 FROM products ORDER BY name, size""").fetchall()
            content = [[r[0], r[1], r[2], r[3], f"{r[4] / 100:.2f}", r[5], r[6]] for r in rows]
        elif kind == "ventas":
            headers = ["Folio", "Fecha", "SKU", "Producto", "Cantidad", "Precio MXN", "Total MXN", "Estado", "Pedido"]
            rows = db.execute("""SELECT id,sold_at,sku,product_name,quantity,unit_price_cents,total_cents,voided,order_id
                                 FROM sales ORDER BY id""").fetchall()
            content = [[r[0], r[1], r[2], r[3], r[4], f"{r[5]/100:.2f}", f"{r[6]/100:.2f}", "Anulada" if r[7] else "Vigente", r[8] or ""] for r in rows]
        else:
            abort(404)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        # Neutralizar fórmulas al abrir CSV en hojas de cálculo.
        for row in content:
            writer.writerow(["'" + cell if isinstance(cell, str) and cell.startswith(("=", "+", "-", "@"))
                             else cell for cell in row])
        return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={kind}.csv"})

    @app.errorhandler(413)
    def upload_too_large(error):
        return render_template("message.html", message="El formulario supera 8 MB. Reduce el tamaño de la imagen."), 413

    @app.get('/imagenes/<path:filename>')
    def product_image(filename):
        db = get_db()
        public = (db.execute('SELECT 1 FROM products WHERE active=1 AND image_path=?',(filename,)).fetchone()
            or db.execute('SELECT 1 FROM product_photos ph JOIN products p ON p.id=ph.product_id WHERE p.active=1 AND ph.image_path=?',(filename,)).fetchone()
            or db.execute('SELECT 1 FROM shop_categories WHERE active=1 AND image_path=?',(filename,)).fetchone()
            or db.execute('SELECT 1 FROM site_sections WHERE image_path=?',(filename,)).fetchone())
        if not public and not session.get('admin_id'): abort(404)
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.get('/catalogo')
    def catalog():
        fields = ('team', 'selection', 'league', 'size', 'brand', 'category')
        filters = {field: request.args.get(field, '').strip()[:100] for field in fields}
        query = request.args.get('q', '').strip()[:100]
        clauses, values = [], []
        for field, value in filters.items():
            if value:
                clauses.append(f"{field}=?")
                values.append(value)
        if query:
            clauses.append('(name LIKE ? OR sku LIKE ?)')
            values.extend([f'%{query}%'] * 2)
        sql = 'SELECT * FROM products' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY name,size'
        db = get_db()
        options = {field: [r[0] for r in db.execute(f"SELECT DISTINCT {field} FROM products WHERE {field} != '' ORDER BY {field}")] for field in fields}
        return render_template('catalog.html', items=db.execute(sql, values).fetchall(), filters=filters, options=options, q=query,
            sections=db.execute('SELECT * FROM site_sections ORDER BY id').fetchall(), active='catalog')

    @app.route('/productos/<int:product_id>/ficha', methods=['GET', 'POST'])
    def product_details(product_id):
        db = get_db()
        product = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        if not product:
            abort(404)
        if request.method == 'POST':
            try:
                fields = ('name', 'team', 'size', 'selection', 'league', 'brand', 'category', 'source_url')
                values = [request.form.get(f, '').strip()[:200] for f in fields]
                if not all(values[:3]):
                    raise ValueError('Completa nombre, equipo y talla.')
                image = save_image(request.files.get('image'), app.config['UPLOAD_FOLDER']) or product['image_path']
                with db:
                    db.execute('UPDATE products SET description=? WHERE id=?', (request.form.get('description', product['description']).strip()[:5000], product_id))
                    db.execute('UPDATE products SET season=?,version=?,kit=?,model_key=?,featured=?,is_new=?,on_sale=?,image_credit=? WHERE id=?',
                        (request.form.get('season','')[:30],request.form.get('version','Aficionado')[:30],request.form.get('kit','Local')[:30],request.form.get('model_key','')[:100],int('featured' in request.form),int('is_new' in request.form),int('on_sale' in request.form),request.form.get('image_credit','')[:500],product_id))
                    db.execute('UPDATE products SET name=?,team=?,size=?,selection=?,league=?,brand=?,category=?,source_url=?,image_path=? WHERE id=?', (*values, image, product_id))
                    if 'category_id' in request.form:
                        assign_product_category(db,product_id,request.form.get('category_id'),derive=not request.form.get('category_id'))
                flash('Ficha actualizada.', 'success')
                return redirect(url_for('catalog'))
            except ValueError as exc:
                flash(str(exc), 'error')
        return render_template('details.html', product=product, photos=db.execute('SELECT * FROM product_photos WHERE product_id=?',(product_id,)).fetchall(), active='products')

    @app.route('/integracion', methods=['GET', 'POST'])
    def integration():
        if request.method == 'POST':
            try:
                title = request.form.get('title', '').strip()[:100]
                body = request.form.get('body', '').strip()[:5000]
                if not title or not body:
                    raise ValueError('Completa título y contenido.')
                image = save_image(request.files.get('image'), app.config['UPLOAD_FOLDER'])
                with get_db() as db:
                    db.execute('INSERT INTO site_sections(title,body,source_url,image_path) VALUES(?,?,?,?)',
                        (title, body, request.form.get('source_url', '').strip()[:500], image))
                flash('Sección incorporada al catálogo.', 'success')
                return redirect(url_for('catalog'))
            except ValueError as exc:
                flash(str(exc), 'error')
        return render_template('integration.html', active='integration')

    @app.get("/inventario")
    def inventory():
        items = get_db().execute("SELECT * FROM products ORDER BY stock, name").fetchall()
        return render_template("inventory.html", items=items, active="inventory")

    @app.route("/clientes", methods=["GET", "POST"])
    def clients_page():
        db = get_db()
        if request.method == "POST":
            name = request.form.get("name", "").strip()[:100]
            if not name:
                flash("Introduce el nombre del cliente.", "error")
            else:
                with db:
                    db.execute("INSERT INTO clients(name,phone,email) VALUES(?,?,?)", (
                        name, request.form.get("phone", "").strip()[:40], request.form.get("email", "").strip()[:120]))
                flash("Cliente registrado.", "success")
            return redirect(url_for("clients_page"))
        q = request.args.get("q", "").strip()[:100]
        items = db.execute("SELECT c.*, COUNT(s.id) operations, COALESCE(SUM(s.total_cents),0) total FROM clients c LEFT JOIN sales s ON s.client_id=c.id AND s.voided=0 WHERE c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? GROUP BY c.id ORDER BY c.name", [f"%{q}%"]*3).fetchall()
        return render_template("clients.html", items=items, q=q, active="clients")

    @app.route("/gastos", methods=["GET", "POST"])
    def expenses_page():
        db = get_db()
        if request.method == "POST":
            try:
                description = request.form.get("description", "").strip()[:200]
                category = request.form.get("category", "").strip()[:80]
                spent_on = datetime.strptime(request.form.get("spent_on", ""), "%Y-%m-%d").date().isoformat()
                amount = parse_money(request.form.get("amount", ""))
                if not description or not category or amount <= 0:
                    raise ValueError("Completa el concepto, categoría y un importe mayor a cero.")
                with db:
                    db.execute("INSERT INTO expenses(description,category,amount_cents,spent_on) VALUES(?,?,?,?)", (description, category, amount, spent_on))
                flash("Gasto registrado.", "success")
                return redirect(url_for("expenses_page"))
            except ValueError:
                flash("Revisa el concepto, categoría, importe y fecha del gasto.", "error")
        return render_template("expenses.html", items=db.execute("SELECT * FROM expenses ORDER BY spent_on DESC,id DESC").fetchall(), today=datetime.now().date().isoformat(), active="expenses")

    @app.get("/reportes")
    def reports():
        start = request.args.get("desde", "")
        end = request.args.get("hasta", "")
        try:
            for value in (start, end):
                if value:
                    datetime.strptime(value, "%Y-%m-%d")
            if start and end and start > end:
                raise ValueError()
        except ValueError:
            flash("Selecciona un intervalo de fechas válido.", "error")
            return redirect(url_for("reports"))
        args = (start or "0001-01-01", end or "9999-12-31")
        result = get_db().execute("""SELECT COALESCE(SUM(total_cents),0) revenue,
            COALESCE(SUM(quantity * unit_cost_cents),0) cost,
            COALESCE(SUM(CASE WHEN unit_cost_cents IS NULL THEN 1 ELSE 0 END),0) missing,
            COUNT(*) operations FROM sales WHERE voided=0 AND date(sold_at) BETWEEN ? AND ?""", args).fetchone()
        expense = get_db().execute("SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE spent_on BETWEEN ? AND ?", args).fetchone()[0]
        return render_template("reports.html", result=result, expense=expense, start=start, end=end, active="reports")

    return app

