"""Una instancia y un worker para SQLite y el límite local de acceso."""
import os
bind='0.0.0.0:'+os.environ.get('PORT','8000')
workers=1
threads=4
worker_class='gthread'
timeout=60
accesslog='-'
errorlog='-'
capture_output=True
