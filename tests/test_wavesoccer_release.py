import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import create_app
from negocio.categories import ensure_category
from negocio.wavesoccer_release import run, make_backup, connect, state, integrity, main


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root/'data/tienda.sqlite3'
        self.app = create_app({'TESTING': True, 'DATA_DIR': str(self.root/'data')})
        with closing(connect(self.database, True)) as db, db:
            db.execute("INSERT INTO admins VALUES(1,'propietario','hash de prueba')")
            db.execute("INSERT INTO clients(id,name,phone) VALUES(1,'Cliente de prueba','000')")
            db.execute("INSERT INTO products(id,sku,name,team,size,price_cents,stock) VALUES(1,'EXISTENTE','Anterior','Propio','M',12300,19)")
            db.execute("INSERT INTO orders(id,token,checkout_key,client_id,status,total_cents) VALUES(1,'privado','checkout',1,'pendiente',12300)")
            db.execute("INSERT INTO order_items(id,order_id,product_id,name,sku,size,quantity,price_cents) VALUES(1,1,1,'Anterior','EXISTENTE','M',1,12300)")
            db.execute("INSERT INTO payments(order_id,amount_cents,method) VALUES(1,100,'efectivo')")
            db.execute("INSERT INTO expenses(description,category,amount_cents,spent_on) VALUES('Anterior','Gasto',10,'2026-10-26')")
        self.initial = self.snapshot()

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self):
        with closing(connect(self.database)) as db:
            return state(db)

    def options(self, **overrides):
        result = make_backup(self.database, self.root/(os.urandom(8).hex()+'.sqlite3'))
        options = dict(apply=True, backup=result['backup'], backup_sha256=result['sha256'],
                       confirm_database=str(self.database), confirm='IMPORTAR 505',
                       writes_paused=True, backup_verified=True)
        options.update(overrides)
        return options

    def test_simulation_is_read_only_and_no_flask_initialization(self):
        digest = self.database.read_bytes()
        with patch('negocio.create_app', side_effect=AssertionError('No iniciar Flask')):
            result = run(self.database)
        self.assertEqual(result['records'], 505)
        self.assertGreater(result['categories'], 0)
        self.assertEqual(self.initial, self.snapshot())
        self.assertEqual(digest, self.database.read_bytes())
        self.assertFalse((self.root/'data/importaciones').exists())

    def test_import_repeat_and_selective_recovery_preserve_business(self):
        options = self.options()
        self.assertEqual(Path(options['backup']).stat().st_mode & 0o777, 0o600)
        first = run(self.database, **options)
        after = self.snapshot()
        for table, rows in self.initial.items():
            if table not in ('shop_categories', '__schema__'):
                self.assertEqual(rows, after[table], table)
        with closing(connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT stock FROM products').fetchone()[0], 19)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM payments').fetchone()[0], 1)
            integrity(db)
        second = run(self.database, **self.options())
        self.assertEqual(second['categories'], 0)
        before_preview = self.snapshot()
        preview = run(self.database, recover=first['run_id'])
        self.assertEqual(preview['categories'], first['categories'])
        self.assertEqual(self.snapshot(), before_preview)
        recovered = run(self.database, recover=first['run_id'],
                        **self.options(confirm='RECUPERAR '+first['run_id']))
        self.assertEqual(recovered['categories'], first['categories'])
        with closing(connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM shop_categories WHERE active=0').fetchone()[0], first['categories'])
            integrity(db)
        for table, rows in self.initial.items():
            if table not in ('shop_categories', '__schema__'):
                self.assertEqual(rows, self.snapshot()[table], table)
        self.assertEqual(run(self.database, recover=first['run_id'])['categories'], 0)
        # Recuperar nunca elimina IDs; reimportar tampoco reactiva ramas recuperadas.
        self.assertEqual(run(self.database)['categories'], 0)

    def test_confirmation_and_missing_backup_rejected(self):
        for override in ({'confirm': None}, {'confirm_database': '/otra/base'},
                         {'writes_paused': False}, {'backup_verified': False},
                         {'backup': None}, {'backup_sha256': '0'*64}):
            options = self.options(**override)
            with self.assertRaises((ValueError, OSError)):
                run(self.database, **options)
            self.assertEqual(self.initial, self.snapshot())

    def test_stale_backup_rejected_after_new_payment(self):
        options = self.options()
        with closing(connect(self.database, True)) as db, db:
            db.execute("INSERT INTO payments(order_id,amount_cents,method) VALUES(1,50,'transferencia')")
        changed = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'no coincide'):
            run(self.database, **options)
        self.assertEqual(changed, self.snapshot())

    def test_backup_not_overwritten_and_invalid_schema_not_migrated(self):
        path = self.root/'copia.sqlite3'
        make_backup(self.database, path)
        with self.assertRaises(FileExistsError):
            make_backup(self.database, path)
        invalid = self.root/'otra.sqlite3'
        with sqlite3.connect(invalid) as db:
            db.execute('CREATE TABLE unrelated(id)')
        original = invalid.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Esquema'):
            run(invalid)
        self.assertEqual(original, invalid.read_bytes())
        with self.assertRaises(FileNotFoundError):
            run(self.root/'no-existe.sqlite3')
        self.assertFalse((self.root/'no-existe.sqlite3').exists())

    def test_corrupt_and_same_file_backups_rejected(self):
        options = self.options()
        Path(options['backup']).write_bytes(b'no es sqlite')
        from negocio.wavesoccer_release import sha256
        options['backup_sha256'] = sha256(options['backup'])
        with self.assertRaises(sqlite3.Error):
            run(self.database, **options)
        options = self.options(backup=str(self.database), backup_sha256=sha256(self.database))
        with self.assertRaisesRegex(ValueError, 'otro archivo'):
            run(self.database, **options)
        self.assertEqual(self.initial, self.snapshot())

    def test_mid_import_error_rolls_back_categories_sources_and_audit(self):
        with closing(connect(self.database, True)) as db, db:
            db.execute("""CREATE TRIGGER fail_import BEFORE INSERT ON shop_categories
                WHEN NEW.name='Inter Miami' BEGIN SELECT RAISE(ABORT,'fallo inyectado'); END""")
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            run(self.database, **self.options())
        self.assertEqual(before, self.snapshot())

    def test_unexpected_business_write_rolls_back(self):
        with closing(connect(self.database, True)) as db, db:
            db.execute("""CREATE TRIGGER touch_inventory AFTER INSERT ON shop_categories
                BEGIN UPDATE products SET stock=stock+1; END""")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'ajena'):
            run(self.database, **self.options())
        self.assertEqual(before, self.snapshot())

    def test_recovery_refuses_products_modified_categories_and_foreign_children(self):
        first = run(self.database, **self.options())
        with closing(connect(self.database)) as db:
            created = json.loads(db.execute('SELECT created_json FROM wavesoccer_import_runs WHERE run_id=?', (first['run_id'],)).fetchone()[0])
        key = int(next(iter(created)))
        for change in ('product', 'edit', 'child'):
            with closing(connect(self.database, True)) as db, db:
                if change == 'product':
                    db.execute('UPDATE products SET category_id=? WHERE id=1', (key,))
                elif change == 'edit':
                    db.execute("UPDATE shop_categories SET description='Edición posterior' WHERE id=?", (key,))
                else:
                    ensure_category(db, 'Hijo ajeno', key)
            before = self.snapshot()
            with self.assertRaises(ValueError):
                run(self.database, recover=first['run_id'], **self.options(confirm='RECUPERAR '+first['run_id']))
            self.assertEqual(before, self.snapshot())
            with closing(connect(self.database, True)) as db, db:
                if change == 'product':db.execute('UPDATE products SET category_id=NULL WHERE id=1')
                elif change == 'edit':db.execute("UPDATE shop_categories SET description='' WHERE id=?", (key,))

    def test_unknown_run_and_production_guards(self):
        with self.assertRaises(sqlite3.Error):
            run(self.database, recover='inexistente')
        with self.assertRaisesRegex(ValueError, 'Producción'):
            run(self.database, production=True)
        with patch.dict(os.environ, {'JERSEY_ENV': 'production'}):
            with self.assertRaisesRegex(ValueError, '--production'):
                run(self.database)
        self.assertEqual(self.initial, self.snapshot())

    def test_ambiguous_legacy_aliases_cancel_whole_import(self):
        with closing(connect(self.database, True)) as db, db:
            root = db.execute("SELECT id FROM shop_categories WHERE name='Premier League'").fetchone()[0]
            ensure_category(db, 'MAN CITY', root)
            ensure_category(db, 'Manchester City', root)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'ambigua'):
            run(self.database, **self.options())
        self.assertEqual(before, self.snapshot())

    def test_later_business_activity_survives_selective_recovery(self):
        first = run(self.database, **self.options())
        with closing(connect(self.database, True)) as db, db:
            db.execute("INSERT INTO payments(order_id,amount_cents,method) VALUES(1,200,'efectivo')")
            db.execute('UPDATE products SET stock=18 WHERE id=1')
        before = self.snapshot()
        run(self.database, recover=first['run_id'], **self.options(confirm='RECUPERAR '+first['run_id']))
        after = self.snapshot()
        for table in ('products','payments','orders','order_items','admins','clients'):
            self.assertEqual(before[table], after[table], table)

    def test_production_mode_on_isolated_copy_and_cli_confirmation_failure(self):
        with patch('negocio.wavesoccer_release.PRODUCTION_DATABASE', self.database), patch.dict(os.environ, {'JERSEY_ENV': 'production'}):
            preview = run(self.database, production=True)
            self.assertEqual(self.initial, self.snapshot())
            result = run(self.database, production=True, **self.options())
            self.assertEqual(result['categories'], preview['categories'])
            self.assertEqual(main(['import', '--database', str(self.database), '--production', '--apply']), 1)
