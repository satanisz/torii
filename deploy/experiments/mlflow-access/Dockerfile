# SPEC-0020 AC-01/02: code in image; no host workspace mount.
FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/trial
COPY requirements.lock .
RUN uv pip install --system --no-cache --require-hashes -r requirements.lock \
    && useradd --uid 1000 --create-home trial
COPY *.py ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    MLFLOW_DISABLE_TELEMETRY=true DO_NOT_TRACK=true \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
USER 1000:1000
CMD ["python", "server.py"]
