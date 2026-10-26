"""Operaciones de servidor: cuentas con contraseña oculta y respaldo consistente."""
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import click
from werkzeug.security import generate_password_hash


def register_commands(app,get_db):
    def new_password():
        password=click.prompt('Contraseña (mínimo 12 caracteres)',hide_input=True,confirmation_prompt=True)
        if len(password)<12:
            raise click.ClickException('La contraseña debe tener al menos 12 caracteres.')
        return generate_password_hash(password)

    @app.cli.command('create-admin')
    @click.option('--username',prompt='Usuario administrador')
    def create_admin(username):
        """Crea el único administrador sin una pantalla pública de configuración."""
        username=username.strip()
        if not username or len(username)>80:
            raise click.ClickException('Introduce un usuario de 1 a 80 caracteres.')
        db=get_db()
        if db.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
            raise click.ClickException('Ya existe un administrador. Usa reset-admin-password si necesitas cambiar su contraseña.')
        password_hash=new_password()
        try:
            with db:
                db.execute('INSERT INTO admins(id,username,password_hash) VALUES(1,?,?)',(username,password_hash))
        except sqlite3.IntegrityError as exc:
            raise click.ClickException('Ya existe un administrador.') from exc
        click.echo('Administrador creado. Puedes ingresar en /admin.')

    @app.cli.command('reset-admin-password')
    def reset_admin_password():
        """Cambia la contraseña desde una consola autorizada del servidor."""
        db=get_db()
        if not db.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
            raise click.ClickException('Primero ejecuta create-admin.')
        password_hash=new_password()
        with db:
            db.execute('UPDATE admins SET password_hash=? WHERE id=1',(password_hash,))
        click.echo('Contraseña actualizada.')

    @app.cli.command('backup-data')
    @click.option('--destination',type=click.Path(path_type=Path),default=None,help='Carpeta de destino. Por defecto: DATA_DIR/respaldos.')
    def backup_data(destination):
        """Respalda SQLite con su API de backup y todas las fotografías."""
        root=Path(app.config['DATA_DIR'])
        destination=destination or root/'respaldos'
        destination.mkdir(parents=True,exist_ok=True)
        filename='jerseysaurios-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.tar.gz'
        archive=destination/filename
        with tempfile.TemporaryDirectory() as temp:
            staging=Path(temp)
            with sqlite3.connect(staging/'tienda.sqlite3') as target:
                get_db().backup(target)
            uploads=Path(app.config['UPLOAD_FOLDER'])
            if uploads.exists():
                shutil.copytree(uploads,staging/'uploads')
            if (root/'.secret_key').exists():
                shutil.copy2(root/'.secret_key',staging/'.secret_key')
            fd=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as handle, tarfile.open(fileobj=handle,mode='w:gz') as bundle:
                for path in staging.iterdir():
                    bundle.add(path,arcname=path.name)
        click.echo(f'Respaldo creado: {archive}')
