FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PESU_DATA_DIR=/srv/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# A13: run as an unprivileged user; only /srv/data is writable (see docker-compose.yml read_only).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin pesu \
 && mkdir -p /srv/data && chown -R 10001:10001 /srv/data
USER 10001

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--proxy-headers"]
