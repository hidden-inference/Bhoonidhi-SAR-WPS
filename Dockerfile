FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgdal-dev gdal-bin g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-wps.txt ./
RUN pip install "GDAL==$(gdal-config --version)" -r requirements-wps.txt
RUN useradd --uid 1000 --create-home wps
COPY --chown=wps:wps processing ./processing
COPY --chown=wps:wps processes ./processes
COPY --chown=wps:wps templates ./templates
COPY --chown=wps:wps scripts ./scripts
COPY --chown=wps:wps requests ./requests
COPY --chown=wps:wps app.py pywps.cfg run_local.py fetch_bhoonidhi.py ./
RUN mkdir -p data work outputs logs && chown -R wps:wps /app
USER wps
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4)"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "300", "--access-logfile", "-", "app:application"]
