"""Operación explícita sin crear Flask ni ejecutar migraciones al iniciar.

python -m negocio.wavesoccer_release --help
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .wavesoccer import MANIFEST, read_catalog, apply_catalog_in_transaction

PRODUCTION_DATABASE = Path('/var/data/jerseysaurios/tienda.sqlite3')
AUDIT = 'wavesoccer_import_runs'


def connect(path, writable=False):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Se requiere un archivo SQLite existente.')
    db = sqlite3.connect(path.as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=10)
    db.execute('PRAGMA foreign_keys=ON')
    return db


def integrity(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('SQLite no supera integrity_check.')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('SQLite tiene referencias inválidas.')


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def state(db):
    """Comparación completa de esquema y filas, sin imprimir datos privados."""
    result = {}
    for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        result[name] = (sql, tuple(sorted(repr(tuple(r)) for r in db.execute('SELECT * FROM ' + quote(name)))))
    result['__schema__'] = tuple(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall())
    return result


def categories(db):
    return {r[0]: list(r) for r in db.execute('SELECT * FROM shop_categories')}


def schema_check(db):
    required = {'shop_categories': {'id', 'name', 'slug', 'parent_id', 'active', 'sort_order'},
                'products': {'id', 'sku', 'stock', 'category_id'}, 'admins': {'id'},
                'orders': {'id'}, 'order_items': {'id'}, 'payments': {'id'}}
    for table, columns in required.items():
        found = {r[1] for r in db.execute('PRAGMA table_info(' + quote(table) + ')')}
        if not columns <= found:
            raise ValueError(f'Esquema inesperado en {table}; no se ejecutarán migraciones.')
    integrity(db)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def make_backup(database, destination):
    database = Path(database).resolve(strict=True)
    destination = Path(destination).absolute()
    # O_EXCL impide sobrescribir incluso enlaces simbólicos o respaldos existentes.
    with closing(connect(database)) as source:
        schema_check(source)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            integrity(target)
    return {'backup': str(destination), 'sha256': sha256(destination), 'verified': True}


def validate_backup(db, database, backup, expected_sha):
    if not backup or not expected_sha:
        raise ValueError('Se exige respaldo SQLite y su SHA-256 verificado.')
    backup = Path(backup).resolve(strict=True)
    if backup.samefile(database):
        raise ValueError('El respaldo debe ser otro archivo.')
    if sha256(backup) != expected_sha.lower():
        raise ValueError('SHA-256 del respaldo incorrecto.')
    with closing(connect(backup)) as copy:
        integrity(copy)
        if state(copy) != state(db):
            raise ValueError('El respaldo no coincide con la base actual. Pausa escrituras y genera uno reciente.')


def preserved(db, before, old_categories, recovery=False):
    after = state(db)
    allowed = {'shop_categories', 'category_sources', AUDIT, '__schema__'}
    for table in before.keys() | after.keys():
        if table not in allowed and before.get(table) != after.get(table):
            raise ValueError(f'La operación alteraría información ajena: {table}.')
    # Ni siquiera triggers/índices anteriores pueden cambiar silenciosamente.
    if not set(before['__schema__']) <= set(after['__schema__']):
        raise ValueError('La operación alteraría el esquema anterior.')
    if recovery and before.get('category_sources') != after.get('category_sources'):
        raise ValueError('La recuperación alteraría las procedencias.')
    if not recovery:
        current = categories(db)
        if any(current.get(key) != row for key, row in old_categories.items()):
            raise ValueError('Se modificó una categoría anterior.')
    integrity(db)


def recover_in_transaction(db, run_id):
    row = db.execute(f'SELECT created_json,status FROM {AUDIT} WHERE run_id=?', (run_id,)).fetchone()
    if not row:
        raise ValueError('No existe esa ejecución en esta base.')
    if row[1] == 'recovered':
        return 0
    created = json.loads(row[0])
    current = categories(db)
    ids = {int(key) for key in created}
    # No esconder un producto nuevo ni una rama modificada después de importar.
    for key in ids:
        if current.get(key) != created[str(key)]:
            raise ValueError('Una categoría importada fue modificada; recuperación cancelada.')
    for key, item in current.items():
        columns = [r[1] for r in db.execute('PRAGMA table_info(shop_categories)')]
        parent = item[columns.index('parent_id')]
        if parent in ids and key not in ids:
            raise ValueError('Hay subcategorías ajenas; recuperación cancelada.')
    # Cualquier tabla que referencie una categoría creada impide ocultarla.
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        if table == 'shop_categories':
            continue
        for fk in db.execute('PRAGMA foreign_key_list(' + quote(table) + ')'):
            if fk[2] != 'shop_categories':
                continue
            if table == 'category_sources':
                continue  # Se conservan todas las procedencias, incluso al recuperar.
            for key in ids:
                if db.execute('SELECT 1 FROM ' + quote(table) + ' WHERE ' + quote(fk[3]) + '=? LIMIT 1', (key,)).fetchone():
                    raise ValueError(f'Hay referencias en {table}; recuperación cancelada.')
    for key in ids:
        db.execute('UPDATE shop_categories SET active=0 WHERE id=?', (key,))
    expected = {key: list(item) for key, item in current.items()}
    active_index = [r[1] for r in db.execute('PRAGMA table_info(shop_categories)')].index('active')
    for key in ids:
        expected[key][active_index] = 0
    if categories(db) != expected:
        raise ValueError('La recuperación alteraría categorías ajenas; operación cancelada.')
    db.execute(f"UPDATE {AUDIT} SET status='recovered' WHERE run_id=?", (run_id,))
    return len(ids)


def run(database, *, apply=False, backup=None, backup_sha256=None, confirm_database=None,
        confirm=None, writes_paused=False, backup_verified=False, production=False,
        recover=None):
    database = Path(database).resolve(strict=True)
    if production:
        if database != PRODUCTION_DATABASE or os.environ.get('JERSEY_ENV') != 'production':
            raise ValueError('Producción requiere la ruta exacta de Render y JERSEY_ENV=production.')
    elif database.is_relative_to('/var/data') or os.environ.get('JERSEY_ENV') == 'production':
        raise ValueError('En Render se exige --production; no desactives JERSEY_ENV.')
    catalog = read_catalog()
    if len(catalog['entries']) != 505:
        raise ValueError('Se esperan exactamente 505 registros.')
    manifest_sha = sha256(MANIFEST)
    phrase = f'RECUPERAR {recover}' if recover else 'IMPORTAR 505'
    if apply and (confirm_database != str(database) or confirm != phrase or not writes_paused or not backup_verified):
        raise ValueError('Faltan confirmación de ruta/acción, --writes-paused o --backup-verified.')
    # La simulación trabaja solo en memoria; no abre el destino para escritura.
    with closing(connect(database, writable=apply)) as source:
        if apply:
            db = source
        else:
            db = sqlite3.connect(':memory:')
            source.backup(db)
            db.execute('PRAGMA foreign_keys=ON')
        try:
            db.execute('BEGIN IMMEDIATE')
            schema_check(db)
            if apply:
                validate_backup(db, database, backup, backup_sha256)
            before = state(db)
            old = categories(db)
            had_audit = AUDIT in before
            old_runs = {row[0]: row for row in db.execute(f'SELECT * FROM {AUDIT}')} if had_audit else {}
            old_sources = set(db.execute('SELECT category_id,source_url FROM category_sources')) if 'category_sources' in before else set()
            run_id = None
            if recover:
                count = recover_in_transaction(db, recover)
            else:
                count = apply_catalog_in_transaction(db, catalog)
                created = {str(key): row for key, row in categories(db).items() if key not in old}
                db.execute(f'''CREATE TABLE IF NOT EXISTS {AUDIT} (
                    run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
                    backup_sha256 TEXT NOT NULL, created_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('applied','recovered')))''')
                run_id = uuid.uuid4().hex
                db.execute(f'INSERT INTO {AUDIT} VALUES(?,?,?,?,?,?)',
                           (run_id, datetime.now(timezone.utc).isoformat(), manifest_sha,
                            backup_sha256 or '', json.dumps(created, ensure_ascii=False), 'applied'))
            new_runs = {row[0]: row for row in db.execute(f'SELECT * FROM {AUDIT}')}
            for key, value in old_runs.items():
                expected = (*value[:-1], 'recovered') if recover == key and value[-1] == 'applied' else value
                if new_runs.get(key) != expected:
                    raise ValueError('La operación alteraría la auditoría anterior.')
            if not old_sources <= set(db.execute('SELECT category_id,source_url FROM category_sources')):
                raise ValueError('La operación eliminaría procedencias anteriores.')
            preserved(db, before, old, recovery=bool(recover))
            result = {'mode': 'aplicado' if apply else 'simulación sin escrituras',
                      'database': str(database), 'records': 505, 'categories': count,
                      'action': 'desactivar categorías creadas' if recover else 'importar',
                      'run_id': run_id or recover, 'integrity': 'ok', 'business_data': 'intactos',
                      'manifest_sha256': manifest_sha}
            if apply:
                db.commit()
            else:
                db.rollback()
            return result
        except BaseException:
            db.rollback()
            raise
        finally:
            if db is not source:
                db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    backup_parser = sub.add_parser('backup', help='Crea y valida una copia SQLite; nunca sobrescribe.')
    backup_parser.add_argument('--database', required=True)
    backup_parser.add_argument('--output', required=True)
    for action in ('import', 'recover'):
        cmd = sub.add_parser(action, help='Simula por defecto; --apply exige respaldo y confirmaciones.')
        cmd.add_argument('--database', required=True)
        cmd.add_argument('--production', action='store_true')
        cmd.add_argument('--apply', action='store_true')
        cmd.add_argument('--backup')
        cmd.add_argument('--backup-sha256')
        cmd.add_argument('--confirm-database')
        cmd.add_argument('--confirm')
        cmd.add_argument('--writes-paused', action='store_true')
        cmd.add_argument('--backup-verified', action='store_true')
        if action == 'recover':
            cmd.add_argument('--run-id', required=True)
    args = vars(parser.parse_args(argv))
    action = args.pop('action')
    try:
        if action == 'backup':
            result = make_backup(args['database'], args['output'])
        else:
            if action == 'recover':
                args['recover'] = args.pop('run_id')
            result = run(**args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print('Operación cancelada: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
