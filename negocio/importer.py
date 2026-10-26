"""Captura manual e importación CSV autorizada. No realiza solicitudes de red."""
import csv
import io
import sqlite3
from pathlib import Path
from werkzeug.datastructures import FileStorage
from flask import request, render_template, flash, redirect, url_for
from .media import save_product_image
from .categories import assign_product_category


def register_importer(app, get_db, parse_money, parse_integer):
    def show(values=None):
        return render_template('importer.html', values=values or {}, active='importer')

    @app.get('/importar')
    def import_page(): return show()

    @app.post('/importar/extraer')
    def extract_source():
        flash('Extracción automática desactivada. Primero se debe revisar la fuente y sus permisos. Usa carga manual o CSV.', 'error')
        return show({'source_url':request.form.get('source_url','')})

    def insert(db, values, image_path=None):
        if values.get('authorized')!='yes': raise ValueError('Confirma la autorización del contenido.')
        if values.get('confirm')!='yes': raise ValueError('Confirma que revisaste los datos y precio en MXN.')
        name = values.get('name','').strip()[:100]
        sku = values.get('sku','').strip().upper()[:40]
        if not name or not sku: raise ValueError('Completa nombre y SKU único.')
        price = parse_money(values.get('price',''))
        cost = parse_money(values['cost']) if values.get('cost','').strip() else None
        stock = parse_integer(values.get('stock','0'),'Stock')
        minimum = parse_integer(values.get('minimum_stock','3'),'Mínimo')
        category = values.get('category','').strip()[:100]

        pid = db.execute('''INSERT INTO products(sku,name,team,size,price_cents,cost_cents,stock,minimum_stock,description,category,selection,league,brand,source_url,image_path,image_url,image_credit,season,model_key)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(sku,name,values.get('team','').strip()[:100] or 'Sin equipo',values.get('size','U').strip()[:20] or 'U',price,cost,stock,minimum,values.get('description','')[:5000],category,*[values.get(f,'')[:100] for f in ('selection','league','brand')],values.get('source_url','')[:2000],image_path,values.get('image_url','')[:2000],values.get('credit','')[:500],values.get('season','')[:30],values.get('model_key','')[:100])).lastrowid
        assign_product_category(db,pid,values.get('category_id'),derive=not values.get('category_id'))
        if image_path or values.get('image_url'):
            db.execute('INSERT INTO product_photos(product_id,image_path,source_url,credit,authorized) VALUES(?,?,?,?,1)',(pid,image_path,values.get('image_url') or values.get('source_url',''),values.get('credit','')[:500]))
        return pid

    @app.post('/importar/guardar')
    def save_import():
        values = request.form.to_dict()
        image = None
        try:
            if values.get('authorized')!='yes': raise ValueError('Confirma la autorización del contenido.')
            with get_db() as db:
                pid = insert(db,values)
                image = save_product_image(request.files.get('image'),app.config['UPLOAD_FOLDER'],pid)
                if image:
                    db.execute('UPDATE products SET image_path=? WHERE id=?',(image,pid))
                    db.execute('INSERT INTO product_photos(product_id,image_path,source_url,credit,authorized) VALUES(?,?,?,?,1)',(pid,image,values.get('source_url','')[:2000],values.get('credit','')[:500]))
            flash('Producto importado correctamente. Las referencias remotas no se descargan automáticamente.','success')
            return redirect(url_for('catalog'))
        except (ValueError,sqlite3.IntegrityError) as exc:
            if image: (Path(app.config['UPLOAD_FOLDER'])/image).unlink(missing_ok=True)
            flash(str(exc) if isinstance(exc,ValueError) else 'El SKU ya existe. No se sobrescribió el producto.','error')
            return show(values)

    @app.post('/importar/csv')
    def import_csv():
        created_images = []
        try:
            if request.form.get('authorized')!='yes': raise ValueError('Confirma la autorización del CSV y sus referencias.')
            upload = request.files.get('csv')
            if not upload: raise ValueError('Selecciona un archivo CSV UTF-8.')
            data = upload.read(1024*1024+1)
            if len(data)>1024*1024: raise ValueError('El CSV no puede superar 1 MB.')
            reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
            if not {'sku','name','price'} <= set(reader.fieldnames or []): raise ValueError('Se requieren las columnas sku,name,price.')
            rows = []
            for number,row in enumerate(reader,2):
                if len(rows)>=500: raise ValueError('El máximo es 500 productos por CSV.')
                if None in row or any(v is None for v in row.values()): raise ValueError(f'Fila {number}: número de columnas inválido.')
                rows.append(row)
            if not rows: raise ValueError('El CSV está vacío.')
            with get_db() as db:
                for number,row in enumerate(rows,2):
                    try:
                        pid = insert(db,{**row,'authorized':'yes','confirm':'yes'})
                        filename = row.get('image_file','').strip()
                        if filename:
                            root = Path(app.config['IMPORT_FOLDER']).resolve()
                            path = (root/filename).resolve()
                            if not path.is_relative_to(root) or not path.is_file():
                                raise ValueError('La imagen local no existe en data/importaciones/.')
                            with path.open('rb') as handle:
                                image = save_product_image(FileStorage(stream=handle,filename=path.name),app.config['UPLOAD_FOLDER'],pid)
                            created_images.append(image)
                            db.execute('UPDATE products SET image_path=? WHERE id=?',(image,pid))
                            db.execute('INSERT INTO product_photos(product_id,image_path,source_url,credit,authorized) VALUES(?,?,?,?,1)',(pid,image,row.get('source_url','')[:2000],row.get('credit','')[:500]))
                    except (ValueError,OSError,sqlite3.IntegrityError) as exc: raise ValueError(f'Fila {number}: datos inválidos o SKU duplicado. No se importó ninguna fila.') from exc
            flash(f'{len(rows)} productos importados. Referencias guardadas sin descargar imágenes externas.','success')
            return redirect(url_for('products'))
        except (ValueError,UnicodeError,csv.Error) as exc:
            for image in created_images:
                (Path(app.config['UPLOAD_FOLDER'])/image).unlink(missing_ok=True)
            flash(str(exc),'error'); return redirect(url_for('import_page'))
