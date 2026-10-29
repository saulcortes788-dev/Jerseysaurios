FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 \
    JERSEY_DATA_DIR=/var/data/jerseysaurios FLASK_APP=wsgi:app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -r -u 10001 app && mkdir -p /var/data/jerseysaurios && chown -R app /var/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/salud')"
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
