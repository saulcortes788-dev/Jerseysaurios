"""Carga explícita y aditiva de metadatos revisados; nunca realiza solicitudes de red."""
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .categories import ensure_category, slugify

MANIFEST = Path(__file__).with_name('wavesoccer_catalog.json')

# Reutilizar las ramas locales sin renombrar ni mover categorías existentes.
LEAGUE_ALIASES = {
    'Liga MX / Expansión MX': 'Liga MX', 'LaLiga / Hypermotion': 'LaLiga',
    'Premier League / Championship': 'Premier League',
    'J1 League': 'Liga de Japón', 'LPF Argentina': 'Liga Argentina',
}
TEAM_ALIASES = {
    'Manchester City': ('MAN CITY',), 'Manchester United': ('MANU', 'MAN U'),
    'Liverpool': ('LWP',), 'Osasuna': ('O-SASUNA',),
    'San Diego FC': ('SAN DIEGO',), 'Austin FC': ('AUSTIN',),
    'Vancouver Whitecaps': ('VANCOUVER WHITECAP',),
    'Real Salt Lake': ('REAL SALK LAKE',), 'Sporting Kansas City': ('KANSAS CITY',),
    'CF Montréal': ('MONTREAL IMPACT',), 'FC Tokyo': ('TOKYO FC',),
    'Kyoto Sanga': ('TOKYO SANGA',), 'Argentinos Juniors': ('ARGENTINA JUNIORS',),
    'Lanús': ('LUNUS',), 'Tigre': ('ATLETICO TIGRE',),
    'Vélez Sarsfield': ('SARSFIELD',), 'Estudiantes de La Plata': ('LA PLATA',),
    'Independiente': ('ATLETICO INDEPENDIENTE',), 'Racing Club': ('RACING',),
    'Huracán': ('ATLETICO HURACAN',), 'Boca Juniors': ('BOCA',),
    'Athletico Paranaense': ('PARANAENSE',),
}
TYPE_ALIASES = {'Portero infantil': 'Infantil portero',
                'Short de portero': 'Short portero', 'Portero short': 'Short portero'}


def read_listing(path):
    """Lee todas las filas; las temporadas vacías permanecen vacías."""
    lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    if not lines or [v.strip() for v in lines[0].split('|')] != ['Liga', 'Equipo', 'Temporada', 'Tipo de jersey', 'URL de WaveSoccer']:
        raise ValueError('Encabezado de listado inválido.')
    entries = []
    for number, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        values = [v.strip() for v in line.split('|')]
        if len(values) != 5:
            raise ValueError(f'Fila {number}: se requieren cinco columnas.')
        entry = dict(zip(('league', 'team', 'season', 'jersey_type', 'source_url'), values))
        entry['checked_on'] = '2026-10-26'
        entries.append(entry)
    return {'schema_version': 1, 'coverage': f'{len(entries)} registros proporcionados por el propietario; no acredita disponibilidad actual',
            'source_file': Path(path).name, 'entries': entries}


def existing_or_create(db, name, parent=None, aliases=()):
    keys = {slugify(value) for value in (name, *aliases)}
    matches = []
    for row in db.execute('SELECT id,name,slug FROM shop_categories WHERE parent_id IS ? ORDER BY id', (parent,)):
        if slugify(row[1]) in keys or row[2] in keys:
            matches.append(row[0])
    if len(matches) > 1:
        raise ValueError(f'Equivalencia ambigua para {name}; revisa las categorías existentes.')
    if matches:
        return matches[0]
    return ensure_category(db, name, parent)


def read_catalog(path=MANIFEST):
    catalog = json.loads(Path(path).read_text(encoding='utf-8'))
    if catalog.get('schema_version') != 1 or not isinstance(catalog.get('entries'), list):
        raise ValueError('Formato de catálogo inválido.')
    for entry in catalog['entries']:
        for field in ('league', 'team', 'source_url', 'checked_on'):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f'Falta {field} en el catálogo.')
        for field in ('league', 'team', 'season', 'jersey_type'):
            value = entry.get(field, '')
            if not isinstance(value, str) or value != value.strip() or len(value) > 100:
                raise ValueError(f'Valor inválido: {field}.')
        url = urlsplit(entry['source_url'])
        if url.scheme != 'https' or url.netloc != 'wavesoccer.x.yupoo.com' or not url.path.startswith(('/albums', '/categories')):
            raise ValueError('La fuente debe ser una lista pública de WaveSoccer.')
        date.fromisoformat(entry['checked_on'])
    return catalog


def apply_catalog(db, catalog):
    """Transacción completa; no modifica categorías existentes ni productos.

    La procedencia queda en una tabla independiente. No se carga al iniciar Flask.
    """
    with db:
        db.execute('BEGIN IMMEDIATE')
        return apply_catalog_in_transaction(db, catalog)


def apply_catalog_in_transaction(db, catalog):
    """El llamador controla commit/rollback; permite auditoría atómica."""
    if not db.in_transaction:
        raise ValueError('Se requiere una transacción activa.')
    db.execute('''CREATE TABLE IF NOT EXISTS category_sources (
        category_id INTEGER NOT NULL REFERENCES shop_categories(id) ON DELETE CASCADE,
        source_url TEXT NOT NULL, checked_on TEXT NOT NULL,
        PRIMARY KEY(category_id, source_url))''')
    before = db.execute('SELECT COUNT(*) FROM shop_categories').fetchone()[0]
    for entry in catalog['entries']:
        league = LEAGUE_ALIASES.get(entry['league'], entry['league'])
        parent = existing_or_create(db, league, aliases=(entry['league'],))
        db.execute('''INSERT INTO category_sources VALUES(?,?,?)
            ON CONFLICT(category_id,source_url) DO UPDATE SET checked_on=excluded.checked_on''',
            (parent, entry['source_url'], entry['checked_on']))
        for field in ('team', 'season', 'jersey_type'):
            if not entry.get(field):
                continue
            value = entry[field]
            if field == 'team':
                parent = existing_or_create(db, value, parent, TEAM_ALIASES.get(value, ()))
            else:
                value = TYPE_ALIASES.get(value, value) if field == 'jersey_type' else value
                parent = existing_or_create(db, value, parent)
            db.execute('''INSERT INTO category_sources VALUES(?,?,?)
                ON CONFLICT(category_id,source_url) DO UPDATE SET checked_on=excluded.checked_on''',
                (parent, entry['source_url'], entry['checked_on']))
    created = db.execute('SELECT COUNT(*) FROM shop_categories').fetchone()[0] - before
    return created


def backup_database(db, database):
    path = Path(database)
    backup = path.with_name('respaldo_antes_wavesoccer_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    with sqlite3.connect(backup) as target:
        db.backup(target)
    backup.chmod(0o600)
    return backup
