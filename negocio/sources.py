"""Adaptador HTML/JSON-LD independiente de Flask para fuentes externas."""
import http.client
import ipaddress
import json
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

SOURCE_URL = 'https://wavesoccer.x.yupoo.com/albums/70929351?uid=1'
MAX_BYTES = 6 * 1024 * 1024


def fetch_public(url, limit=MAX_BYTES):
    """Descarga limitada; valida cada redirección y fija la IP pública de conexión."""
    for _ in range(5):
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError('Utiliza una URL pública HTTP o HTTPS sin credenciales.')
        try:
            port = parts.port or (443 if parts.scheme == 'https' else 80)
            if port not in (80, 443):
                raise ValueError('Solo se admiten los puertos 80 y 443.')
            host = parts.hostname.encode('idna').decode('ascii')
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise ValueError('La fuente debe estar en Internet; no se permiten direcciones locales o privadas.')
            address = addresses[0][4][0]
            connection = http.client.HTTPConnection(host, port, timeout=12)

            def connect():
                sock = socket.create_connection((address, port), timeout=12)
                if parts.scheme == 'https':
                    try:
                        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                    except Exception:
                        sock.close()
                        raise
                connection.sock = sock

            connection.connect = connect
            try:
                path = parts.path or '/'
                if parts.query:
                    path += '?' + parts.query
                connection.request('GET', path, headers={'User-Agent': 'JerseyLocalImporter/1.0', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise ValueError('La fuente devolvió una redirección sin destino.')
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise ValueError(f'La fuente respondió HTTP {response.status}. Puedes capturar los datos manualmente.')
                content = response.read(limit + 1)
                if len(content) > limit:
                    raise ValueError('El archivo externo supera el tamaño permitido.')
                return content, response.getheader('Content-Type', ''), url
            finally:
                connection.close()
        except (OSError, http.client.HTTPException, UnicodeError) as exc:
            raise ValueError('No se pudo conectar con la fuente. Revisa la URL o captura los datos manualmente.') from exc
    raise ValueError('La fuente tiene demasiadas redirecciones.')


class ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = ''
        self.in_title = False
        self.in_json = False
        self.script = ''
        self.documents = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = attrs.get('property') or attrs.get('name') or attrs.get('itemprop', '')
            self.meta.setdefault(key.lower(), attrs.get('content', ''))
        if tag == 'title':
            self.in_title = True
        if tag == 'script':
            self.in_json = attrs.get('type', '').lower() == 'application/ld+json'
            self.script = ''

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_json:
            self.script += data

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_json:
            try:
                self.documents.append(json.loads(self.script))
            except (ValueError, RecursionError):
                pass
            self.in_json = False


def find_product(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(reversed(item))
        elif isinstance(item, dict):
            kind = item.get('@type', [])
            if kind == 'Product' or isinstance(kind, list) and 'Product' in kind:
                return item
            pending.extend(reversed(list(item.values())))
    return {}


def extract_product(content, base_url):
    parser = ProductHTML()
    parser.feed(content)
    product = find_product(parser.documents)
    meta = parser.meta
    offers = product.get('offers', {})
    if isinstance(offers, list):
        offers = next((o for o in offers if isinstance(o, dict)), {})
    if not isinstance(offers, dict):
        offers = {}
    image = product.get('image') or meta.get('og:image') or meta.get('twitter:image', '')
    if isinstance(image, list):
        image = image[0] if image else ''
    if isinstance(image, dict):
        image = image.get('url') or image.get('contentUrl', '')
    def scalar(value):
        return str(value).strip() if isinstance(value, (str, int, float)) else ''
    image = scalar(image)
    return {
        'name': scalar(product.get('name') or meta.get('og:title') or parser.title)[:100],
        'description': scalar(product.get('description') or meta.get('og:description') or meta.get('description'))[:5000],
        'category': scalar(product.get('category') or meta.get('product:category'))[:100],
        'price': scalar(offers.get('price') if offers.get('price') is not None else meta.get('product:price:amount', meta.get('og:price:amount', ''))),
        'currency': scalar(offers.get('priceCurrency') or meta.get('product:price:currency', '')),
        'image_url': urljoin(base_url, image) if image else '',
        'source_url': base_url,
    }
