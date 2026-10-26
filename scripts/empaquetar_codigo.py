"""Crea un ZIP de código sin datos, contraseñas, imágenes subidas ni respaldos."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent.parent
FILES=('app.py','wsgi.py','gunicorn.conf.py','requirements.txt','render.yaml','.env.example','.gitignore','README.md','PUBLICAR_EN_RENDER.md','iniciar.sh','seed_categorias.py','cargar_demo.py')
FOLDERS=('negocio','templates','static','tests','scripts','docs')


def package_code(destination=None):
    destination=Path(destination) if destination else ROOT/'dist/jerseysaurios-codigo.zip'
    destination.parent.mkdir(parents=True,exist_ok=True)
    paths=[ROOT/name for name in FILES if (ROOT/name).is_file()]
    for folder in FOLDERS:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log','.sqlite3','.zip'))
    with ZipFile(destination,'w',ZIP_DEFLATED) as bundle:
        for path in sorted(set(paths)):
            bundle.write(path,path.relative_to(ROOT))
    return destination

if __name__=='__main__':
    print(package_code())
