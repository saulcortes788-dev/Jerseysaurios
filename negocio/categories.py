"""Taxonomía jerárquica local, migración y administración sin fuentes remotas."""
import re
import sqlite3
import unicodedata
from collections import defaultdict
from flask import current_app, request, render_template, redirect, url_for, flash, abort
from .media import save_image

# Lista solicitada por el propietario. No representa un árbol extraído de Yupoo.
INITIAL_CATEGORIES = (
    'Mundial 2026', 'Retro clubes', 'Retro selecciones', 'LaLiga', 'Premier League',
    'Serie A', 'Bundesliga', 'Ligue 1', 'Liga Portugal', 'Eredivisie',
    'Liga de Arabia Saudita', 'Liga Argentina', 'Brasileirão', 'Liga MX', 'MLS',
    'Liga de Japón', 'UEFA', 'CONMEBOL y CONCACAF', 'CAF', 'AFC',
    'Jerseys infantiles', 'Ediciones especiales', 'Ediciones de finales',
    'Entrenamiento de clubes', 'Entrenamiento de selecciones', 'Chándales',
    'Chamarras', 'Polos', 'Shorts y medias', 'Accesorios',
)


def slugify(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')[:120] or 'categoria'


def ensure_category(db, name, parent_id=None, order=None):
    name = name.strip()[:100]
    if not name:
        raise ValueError('La categoría necesita un nombre.')
    existing = db.execute('SELECT id FROM shop_categories WHERE parent_id IS ? AND name=? COLLATE NOCASE', (parent_id, name)).fetchone()
    if existing:
        return existing[0]
    base = slugify(name)
    slug, suffix = base, 2
    while db.execute('SELECT id FROM shop_categories WHERE parent_id IS ? AND slug=?', (parent_id, slug)).fetchone():
        slug = f'{base}-{suffix}'; suffix += 1
    if order is None:
        order = db.execute('SELECT COALESCE(MAX(sort_order),-1)+1 FROM shop_categories WHERE parent_id IS ?', (parent_id,)).fetchone()[0]
    return db.execute('INSERT INTO shop_categories(name,slug,parent_id,sort_order) VALUES(?,?,?,?)', (name,slug,parent_id,order)).lastrowid


def seed_categories(db):
    """Idempotente: no modifica nombres, orden ni estado de registros existentes."""
    created = 0
    for i,name in enumerate(INITIAL_CATEGORIES):
        found = db.execute('SELECT id FROM shop_categories WHERE parent_id IS NULL AND (slug=? OR name=? COLLATE NOCASE)', (slugify(name), name)).fetchone()
        if not found:
            ensure_category(db, name, order=i)
            created += 1
    return created


def category_rows(db, public=False):
    """Recorrido iterativo, sin un número fijo de niveles y con estado heredado."""
    rows = [dict(r) for r in db.execute('SELECT * FROM shop_categories ORDER BY sort_order,id')]
    children = defaultdict(list)
    for row in rows:
        children[row['parent_id']].append(row)
    stack = [(r,0,'','',True) for r in reversed(children[None])]
    result, seen = [], set()
    while stack:
        row,depth,path,label,parent_active = stack.pop()
        if row['id'] in seen:
            continue
        seen.add(row['id'])
        effective = bool(row['active']) and parent_active
        path = f"{path}/{row['slug']}" if path else row['slug']
        label = f"{label} > {row['name']}" if label else row['name']
        item = {**row,'depth':depth,'path':path,'label':label,'effective_active':effective}
        if not public or effective:
            result.append(item)
        if not public or effective:
            stack.extend((r,depth+1,path,label,effective) for r in reversed(children[row['id']]))
    return result


def category_tree_events(rows):
    """Etiquetas de apertura/cierre para un menú HTML sin recursión de plantillas."""
    events, opened = [], []
    for index,row in enumerate(rows):
        while opened and opened[-1] >= row['depth']:
            events.append(('close',None)); opened.pop()
        branch = index+1 < len(rows) and rows[index+1]['depth'] > row['depth']
        events.append(('open' if branch else 'leaf',row))
        if branch:
            opened.append(row['depth'])
    while opened:
        events.append(('close',None)); opened.pop()
    return events


def descendants(db, category_id, public=False):
    children = defaultdict(list)
    for row in category_rows(db,public=public):
        children[row['parent_id']].append(row['id'])
    allowed = {r['id'] for r in category_rows(db,public=public)}
    if category_id not in allowed:
        return []
    found, stack = set(), [category_id]
    while stack:
        current = stack.pop()
        if current not in found:
            found.add(current); stack.extend(children[current])
    return sorted(found)


def visibility_sql(db):
    ids = [r['id'] for r in category_rows(db,public=True)]
    clause = '(category_id IS NULL OR category_id IN (' + ','.join('?' for _ in ids) + '))'
    if current_app.config.get('HIDE_DEMO'):
        clause = '('+clause+" AND sku NOT LIKE 'DEMO-%')"
    return clause, ids


def assign_product_category(db, product_id, category_id=None, derive=False):
    """Vincula explícitamente o deriva solo de datos locales; no inventa equipos."""
    product = db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
    if not product:
        raise ValueError('El producto no existe.')
    if category_id:
        try:
            category_id = int(category_id)
        except (TypeError,ValueError) as exc:
            raise ValueError('Selecciona una categoría válida.') from exc
        category = db.execute('SELECT * FROM shop_categories WHERE id=?',(category_id,)).fetchone()
        if not category:
            raise ValueError('La categoría no existe.')
    elif derive:
        roots = {r['name'].casefold():r['id'] for r in db.execute('SELECT id,name FROM shop_categories WHERE parent_id IS NULL')}
        legacy, league = product['category'].strip(), product['league'].strip()
        category_id = roots.get(legacy.casefold()) or roots.get(league.casefold())
        if not category_id:
            name = legacy or league
            if not name:
                return None
            category_id = ensure_category(db,name)
        # Se conservan las etiquetas originales; solo se usan sus datos existentes.
        for value in (product['selection'].strip() or product['team'].strip(), product['season'].strip(), product['kit'].strip()):
            if value and value not in ('Sin equipo','General','U'):
                category_id = ensure_category(db,value,category_id)
    else:
        db.execute('UPDATE products SET category_id=NULL WHERE id=?',(product_id,))
        return None
    db.execute('UPDATE products SET category_id=? WHERE id=?',(category_id,product_id))
    return category_id


def initialize_categories(db):
    fields = {r[1] for r in db.execute('PRAGMA table_info(shop_categories)')}
    if 'slug' not in fields:
        # Se preservan IDs, imágenes, créditos y las asociaciones anteriores.
        old = [dict(r) for r in db.execute('SELECT * FROM shop_categories ORDER BY id')]
        with db:
            db.execute('''CREATE TABLE shop_categories_tree (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL,
                parent_id INTEGER REFERENCES shop_categories_tree(id) ON DELETE RESTRICT,
                sort_order INTEGER NOT NULL DEFAULT 0 CHECK(sort_order>=0),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                description TEXT NOT NULL DEFAULT '', image_path TEXT, credit TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT '',
                CHECK(parent_id IS NULL OR parent_id != id))''')
            slugs = set()
            for i,row in enumerate(old):
                slug = slugify(row['name'])
                if slug in slugs: slug += f"-{row['id']}"
                slugs.add(slug)
                db.execute('INSERT INTO shop_categories_tree(id,name,slug,sort_order,description,image_path,credit,kind) VALUES(?,?,?,?,?,?,?,?)',
                           (row['id'],row['name'],slug,i,row['description'],row['image_path'],row['credit'],row.get('kind','')))
            db.execute('DROP TABLE shop_categories')
            db.execute('ALTER TABLE shop_categories_tree RENAME TO shop_categories')
            db.execute('CREATE UNIQUE INDEX category_slug_siblings ON shop_categories(COALESCE(parent_id,0),slug)')
            db.execute('CREATE UNIQUE INDEX category_name_siblings ON shop_categories(COALESCE(parent_id,0),name COLLATE NOCASE)')
            db.execute('CREATE INDEX category_parent_order ON shop_categories(parent_id,sort_order,id)')
    db.execute('''CREATE TRIGGER IF NOT EXISTS category_no_cycles
        BEFORE UPDATE OF parent_id ON shop_categories WHEN NEW.parent_id IS NOT NULL
        BEGIN
          SELECT CASE WHEN EXISTS (
            WITH RECURSIVE ancestors(id,parent_id) AS (
              SELECT id,parent_id FROM shop_categories WHERE id=NEW.parent_id
              UNION SELECT c.id,c.parent_id FROM shop_categories c JOIN ancestors a ON c.id=a.parent_id
            ) SELECT 1 FROM ancestors WHERE id=NEW.id
          ) THEN RAISE(ABORT,'category_cycle') END;
        END''')
    if 'category_id' not in {r[1] for r in db.execute('PRAGMA table_info(products)')}:
        db.execute('ALTER TABLE products ADD COLUMN category_id INTEGER REFERENCES shop_categories(id) ON DELETE SET NULL')
        db.execute('CREATE INDEX product_category ON products(category_id)')
    if not db.execute("SELECT 1 FROM shop_settings WHERE key='hierarchy_seeded'").fetchone():
        with db:
            # Coloca primero la lista solicitada solo en la migración inicial.
            db.execute('UPDATE shop_categories SET sort_order=sort_order+100 WHERE parent_id IS NULL')
            seed_categories(db)
            for i,name in enumerate(INITIAL_CATEGORIES):
                db.execute('UPDATE shop_categories SET sort_order=? WHERE parent_id IS NULL AND name=?',(i,name))
            for p in db.execute('SELECT id FROM products WHERE category_id IS NULL').fetchall():
                assign_product_category(db,p['id'],derive=True)
            db.execute("INSERT INTO shop_settings VALUES('hierarchy_seeded','1')")
    db.commit()


def register_category_admin(app,get_db,integer):
    @app.context_processor
    def category_context():
        public = category_rows(get_db(),public=True)
        return {'category_choices':category_rows(get_db()), 'all_category_paths':{r['id']:r for r in category_rows(get_db())}, 'category_navigation':category_tree_events(public), 'public_category_paths':{r['id']:r for r in public}}

    @app.route('/admin/categorias',methods=['GET','POST'])
    def categories_admin():
        db = get_db()
        if request.method=='POST':
            try:
                category_id = integer(request.form.get('category_id','0') or '0','Categoría') or None
                old = db.execute('SELECT * FROM shop_categories WHERE id=?',(category_id,)).fetchone() if category_id else None
                if category_id and not old:
                    raise ValueError('La categoría no existe.')
                action = request.form.get('action','save')
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    if action=='delete':
                        if not old: raise ValueError('Selecciona la categoría a eliminar.')
                        if db.execute('SELECT id FROM shop_categories WHERE parent_id=?',(category_id,)).fetchone():
                            raise ValueError('Mueve o elimina las subcategorías antes de eliminar esta categoría.')
                        if db.execute('SELECT id FROM products WHERE category_id=?',(category_id,)).fetchone():
                            raise ValueError('Reasigna sus productos antes de eliminar la categoría. También puedes desactivarla.')
                        db.execute('DELETE FROM shop_categories WHERE id=?',(category_id,))
                    elif action=='toggle':
                        if not old: raise ValueError('Selecciona una categoría.')
                        db.execute('UPDATE shop_categories SET active=1-active WHERE id=?',(category_id,))
                    elif action in ('up','down'):
                        if not old: raise ValueError('Selecciona una categoría.')
                        siblings = db.execute('SELECT id FROM shop_categories WHERE parent_id IS ? ORDER BY sort_order,id',(old['parent_id'],)).fetchall()
                        ids = [r['id'] for r in siblings]
                        pos = ids.index(category_id); target = pos+(-1 if action=='up' else 1)
                        if 0<=target<len(ids): ids[pos],ids[target]=ids[target],ids[pos]
                        for i,pid in enumerate(ids): db.execute('UPDATE shop_categories SET sort_order=? WHERE id=?',(i,pid))
                    elif action=='save':
                        name = request.form.get('name','').strip()[:100]
                        if not name: raise ValueError('Introduce el nombre de la categoría.')
                        slug = request.form.get('slug','').strip() or (old['slug'] if old else slugify(name))
                        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug) or len(slug)>120:
                            raise ValueError('Slug: utiliza letras minúsculas sin acentos, números y guiones.')
                        parent_id = integer(request.form.get('parent_id','0') or '0','Categoría superior') or None
                        if parent_id:
                            if not db.execute('SELECT id FROM shop_categories WHERE id=?',(parent_id,)).fetchone(): raise ValueError('La categoría superior no existe.')
                            if category_id and parent_id in descendants(db,category_id): raise ValueError('No puedes mover una categoría dentro de sí misma o de sus descendientes.')
                        order = integer(request.form.get('sort_order','0'),'Orden')
                        active = int(request.form.get('active','1')=='1')
                        image = save_image(request.files.get('image'),app.config['UPLOAD_FOLDER'])
                        values = (name,slug,parent_id,order,active,request.form.get('description','')[:1000], image or (old['image_path'] if old else None),request.form.get('credit',old['credit'] if old else '')[:500])
                        if old:
                            db.execute('UPDATE shop_categories SET name=?,slug=?,parent_id=?,sort_order=?,active=?,description=?,image_path=?,credit=? WHERE id=?',(*values,category_id))
                        else:
                            db.execute('INSERT INTO shop_categories(name,slug,parent_id,sort_order,active,description,image_path,credit) VALUES(?,?,?,?,?,?,?,?)',values)
                    else: raise ValueError('Acción desconocida.')
                flash('Categorías actualizadas.','success')
            except (ValueError,sqlite3.IntegrityError) as exc:
                flash(str(exc) if isinstance(exc,ValueError) else 'Ya existe ese nombre o slug dentro de la misma categoría superior.','error')
            return redirect(url_for('categories_admin'))
        edit = None
        if request.args.get('edit'):
            edit = db.execute('SELECT * FROM shop_categories WHERE id=?',(request.args['edit'],)).fetchone()
            if not edit: abort(404)
        excluded = set(descendants(db,edit['id'])) if edit else set()
        rows = category_rows(db)
        return render_template('shop/categories.html',categories=rows,edit=edit,parent_choices=[r for r in rows if r['id'] not in excluded],active='categories')
