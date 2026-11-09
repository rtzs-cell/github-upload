ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.10-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG APP_VERSION=2.0.1
LABEL org.opencontainers.image.title="Radar Workbench" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="Sionna RT radar propagation and signal processing workbench"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    RADAR_API_HOST=0.0.0.0 \
    RADAR_API_PORT=8000 \
    RADAR_UI_MODE=embedded \
    RADAR_OUTPUT_ROOT=/data \
    RADAR_SIONNA_PYTHON=/usr/local/bin/python \
    RADAR_SIONNA_PYTHONNOUSERSITE=1 \
    HOME=/tmp/radar-home

RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY services/radar_api/requirements-api.txt /tmp/requirements-api.txt
COPY experiments/sionna_radar/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --upgrade pip wheel \
    && python -m pip install -r /tmp/requirements-api.txt -r /tmp/requirements-runtime.txt \
    && rm -f /tmp/requirements-api.txt /tmp/requirements-runtime.txt

WORKDIR /opt/radar
COPY services ./services
COPY experiments/sionna_radar ./experiments/sionna_radar
COPY apps/radar-workbench/dist ./apps/radar-workbench/dist
COPY README.md ./README.md

ENV HOME=/tmp \
    XDG_CACHE_HOME=/tmp/cache \
    MPLCONFIGDIR=/tmp/matplotlib

RUN mkdir -p /data \
    && python -c "import fastapi, matplotlib, numpy, pandas, pyarrow, scipy, uvicorn, yaml; from sionna.rt import PathSolver, load_scene; print('Runtime imports: OK')" \
    && rm -rf /tmp/cache /tmp/matplotlib

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

WORKDIR /opt/radar/services/radar_api
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
