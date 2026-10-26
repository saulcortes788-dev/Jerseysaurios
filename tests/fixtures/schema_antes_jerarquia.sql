
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


CREATE TABLE IF NOT EXISTS shop_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shop_categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', image_path TEXT, credit TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS product_photos (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), image_path TEXT, source_url TEXT NOT NULL DEFAULT '', credit TEXT NOT NULL DEFAULT '', authorized INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, token TEXT NOT NULL UNIQUE, checkout_key TEXT NOT NULL UNIQUE, client_id INTEGER NOT NULL REFERENCES clients(id), status TEXT NOT NULL DEFAULT 'pendiente', total_cents INTEGER NOT NULL CHECK(total_cents>=0), created_at TEXT NOT NULL DEFAULT(datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, sku TEXT NOT NULL, size TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), price_cents INTEGER NOT NULL, cost_cents INTEGER);
CREATE TABLE IF NOT EXISTS refunds (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0), reference TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT(datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0), method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT(datetime('now','localtime')));
