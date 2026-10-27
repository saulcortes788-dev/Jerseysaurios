import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from negocio.wavesoccer import read_catalog, read_listing, apply_catalog, LEAGUE_ALIASES
from negocio.categories import category_rows


class WaveSoccerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app({'TESTING': True, 'DATA_DIR': str(self.root)})

    def tearDown(self):
        self.temp.cleanup()

    def connect(self):
        db = sqlite3.connect(self.app.config['DATABASE'])
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def test_preview_apply_backup_and_repeat_preserve_existing_data(self):
        with self.connect() as db:
            db.execute("UPDATE shop_categories SET active=0,sort_order=99,credit='Crédito propio' WHERE slug='liga-mx'")
            db.execute("INSERT INTO products(sku,name,team,size,price_cents,stock) VALUES('REAL','Producto existente','Equipo propio','M',15000,8)")
            categories = db.execute('SELECT * FROM shop_categories ORDER BY id').fetchall()
            products = db.execute('SELECT * FROM products').fetchall()
        runner = self.app.test_cli_runner()
        preview = runner.invoke(args=['load-wavesoccer'])
        self.assertEqual(preview.exit_code, 0, preview.output)
        with self.connect() as db:
            self.assertEqual(categories, db.execute('SELECT * FROM shop_categories ORDER BY id').fetchall())
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='category_sources'").fetchall())
        result = runner.invoke(args=['load-wavesoccer', '--apply'])
        self.assertEqual(result.exit_code, 0, result.output)
        backup = next(self.root.glob('respaldo_antes_wavesoccer_*.sqlite3'))
        with sqlite3.connect(backup) as db:
            self.assertEqual(categories, db.execute('SELECT * FROM shop_categories ORDER BY id').fetchall())
            self.assertEqual(products, db.execute('SELECT * FROM products').fetchall())
        with self.connect() as db:
            self.assertEqual(apply_catalog(db, read_catalog()), 0)
            self.assertEqual(products, db.execute('SELECT * FROM products').fetchall())
            for row in categories:
                self.assertEqual(row, db.execute('SELECT * FROM shop_categories WHERE id=?', (row[0],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.app.test_client().get('/categorias/laliga/atletico-de-madrid/2024-25').status_code, 200)
        self.assertEqual(self.app.test_client().get('/categorias/liga-mx/necaxa').status_code, 404)

    def test_atomic_rollback(self):
        catalog = read_catalog()
        broken = copy.deepcopy(catalog)
        broken['entries'].append({**catalog['entries'][0], 'league': 'Rama de prueba', 'team': 42})
        with self.connect() as db:
            before = db.execute('SELECT COUNT(*) FROM shop_categories').fetchone()[0]
            with self.assertRaises((AttributeError, TypeError)):
                apply_catalog(db, broken)
            self.assertEqual(before, db.execute('SELECT COUNT(*) FROM shop_categories').fetchone()[0])

    def test_invalid_sources_and_names_rejected(self):
        for changes in ({'source_url': 'https://otro.example/albums/1'}, {'team': ''}):
            catalog = copy.deepcopy(read_catalog())
            catalog['entries'][0].update(changes)
            path = self.root/'invalid.json'
            path.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError):
                read_catalog(path)

    def test_all_505_rows_navigation_and_no_invented_seasons(self):
        catalog = read_catalog()
        listing = Path(__file__).resolve().parents[1]/'listado_wavesoccer_nuevo.txt'
        self.assertEqual(catalog, read_listing(listing))
        self.assertEqual(len(catalog['entries']), 505)
        self.assertEqual(len({(e['league'], e['team']) for e in catalog['entries']}), 172)
        with self.connect() as db:
            apply_catalog(db, catalog)
            db.row_factory = sqlite3.Row
            rows = category_rows(db, public=True)
            roots = [r for r in rows if r['depth'] == 0]
            groups = {LEAGUE_ALIASES.get(e['league'], e['league']) for e in catalog['entries']}
            self.assertEqual(len(groups), 10)
            self.assertTrue(groups.issubset({r['name'] for r in roots}))
            teams = [r for r in rows if r['depth'] == 1]
            self.assertEqual(len(teams), 172)
            seasons = [r['name'] for r in rows if r['name'][:4].isdigit()]
            self.assertEqual(seasons, ['2024-25'] * 3)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0], 0)
        client = self.app.test_client()
        # Cada equipo puede abrirse desde el menú y cada categoría desde su URL.
        navigation = client.get('/categorias').get_data(as_text=True)
        for row in teams:
            self.assertIn('/categorias/' + row['path'], navigation)
            self.assertEqual(client.get('/categorias/' + row['path']).status_code, 200, row['path'])
        for path in ('liga-mx/america/authentic', 'mls/inter-miami/infantil',
                     'laliga/atletico-de-madrid/2024-25', 'mundial-2026/iran/infantil'):
            self.assertEqual(client.get('/categorias/' + path).status_code, 200, path)

    def test_legacy_names_reused_and_types_without_season_not_lost(self):
        from negocio.categories import ensure_category
        with self.connect() as db:
            root = db.execute("SELECT id FROM shop_categories WHERE name='Premier League'").fetchone()[0]
            old = ensure_category(db, 'MAN CITY', root)
            db.commit()
            apply_catalog(db, read_catalog())
            self.assertEqual(db.execute('SELECT id FROM shop_categories WHERE parent_id=? AND name=?', (root, 'MAN CITY')).fetchone()[0], old)
            self.assertFalse(db.execute("SELECT id FROM shop_categories WHERE name='Manchester City'").fetchall())
            self.assertTrue(db.execute("SELECT id FROM shop_categories WHERE parent_id=? AND name='Infantil'", (old,)).fetchone())

    def test_production_cannot_apply_catalog(self):
        self.app.config['PRODUCTION'] = True
        result = self.app.test_cli_runner().invoke(args=['load-wavesoccer', '--apply'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertFalse(list(self.root.glob('respaldo_antes_wavesoccer_*')))
