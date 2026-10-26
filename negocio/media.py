"""Validación de imágenes y almacenamiento independiente del catálogo."""
import secrets
import io
import warnings
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError


def save_image(upload, directory):
    if not upload or not upload.filename:
        return None
    raw = upload.stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('La imagen supera 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Utiliza una imagen JPG, PNG o WebP.')
                if image.width * image.height > 20_000_000:
                    raise ValueError('La imagen debe tener como máximo 20 megapíxeles.')
                image.load()
                credits = Image.Exif()
                for tag in (270, 315, 33432):
                    if tag in image.getexif():
                        credits[tag] = image.getexif()[tag]
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1400, 1400))
                filename = secrets.token_hex(20) + '.jpg'
                Path(directory).mkdir(parents=True, exist_ok=True)
                originals = Path(directory) / '.originales'
                originals.mkdir(exist_ok=True)
                (originals / (filename + '.original')).write_bytes(raw)
                image.save(Path(directory) / filename, 'JPEG', quality=88, exif=credits.tobytes())
                return filename
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('El archivo no es una imagen válida o es demasiado grande.') from exc


def save_product_image(upload, directory, product_id):
    """Las nuevas fotos de galería/importación se organizan por producto."""
    relative = f'productos/{product_id}'
    name = save_image(upload, Path(directory) / relative)
    return f'{relative}/{name}' if name else None
