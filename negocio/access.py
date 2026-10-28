"""Administrador local: alta inicial, sesión y cierre con CSRF."""
import secrets
import sqlite3
from datetime import timedelta
from time import monotonic
from flask import request, session, redirect, url_for, render_template, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash


def register_access(app, get_db):
    failures = {}
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

    @app.before_request
    def require_admin():
        if request.endpoint in {'sitemap','robots','static','shop_home','shop_catalog','shop_product','cart_add','cart_update','cart_page','checkout','order_receipt','product_image','category_index','category_page','health'}:
            return
        admin = get_db().execute('SELECT * FROM admins LIMIT 1').fetchone()
        if not admin and app.config['PRODUCTION']:
            if request.endpoint=='setup':
                abort(404)
            return render_template('shop/error.html',title='Administración pendiente de configuración',
                message='El propietario debe configurar su cuenta desde el servidor. El catálogo público sigue disponible.'),503
        if not admin and request.endpoint != 'setup':
            return redirect(url_for('setup'))
        if admin and request.endpoint == 'setup':
            return redirect(url_for('login'))
        if request.endpoint not in {'login', 'setup'} and not session.get('admin_id'):
            return redirect(url_for('login'))

    @app.route('/configurar', methods=['GET', 'POST'])
    def setup():
        if app.config['PRODUCTION']:
            abort(404)
        if request.method == 'POST':
            username = request.form.get('username', '').strip()[:80]
            password = request.form.get('password', '')
            if not username or len(password) < 10 or password != request.form.get('confirm'):
                flash('Introduce un usuario y confirma una contraseña de al menos 10 caracteres.', 'error')
            else:
                try:
                    with get_db() as db:
                        db.execute('INSERT INTO admins(id,username,password_hash) VALUES(1,?,?)', (username, generate_password_hash(password)))
                    flash('Administrador creado. Inicia sesión.', 'success')
                    return redirect(url_for('login'))
                except sqlite3.IntegrityError:
                    return redirect(url_for('login'))
        return render_template('auth.html', setup=True)

    @app.route('/ingresar', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            key = request.remote_addr or 'local'
            count, until = failures.get(key,(0,0))
            if count >= 8 and monotonic() < until:
                flash('Demasiados intentos. Espera un minuto e inténtalo de nuevo.','error')
                return render_template('auth.html', setup=False), 429
            admin = get_db().execute('SELECT * FROM admins WHERE username=?', (request.form.get('username', ''),)).fetchone()
            if admin and check_password_hash(admin['password_hash'], request.form.get('password', '')):
                failures.pop(key,None)
                session.clear()
                session['admin_id'] = admin['id']
                session['csrf_token'] = secrets.token_urlsafe(32)
                session.permanent = True
                return redirect(url_for('dashboard'))
            failures[key] = ((count if monotonic()<until else 0)+1, monotonic()+60)
            flash('Usuario o contraseña incorrectos.', 'error')
        return render_template('auth.html', setup=False)

    @app.post('/salir')
    def logout():
        session.clear()
        return redirect(url_for('login'))
