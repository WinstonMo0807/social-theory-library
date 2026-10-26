FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip==26.2.2 \
    && pip install -r requirements.txt \
    && python -m pip check
COPY rapid_models.py .
RUN python rapid_models.py --root /opt/ocr-models --download
COPY app.py rapid_runtime.py model_probe.py ./
COPY docker-entrypoint.sh /usr/local/bin/library-ocr-entrypoint
RUN addgroup --system ocr && adduser --system --ingroup ocr ocr \
    && mkdir -p /models /tmp/ocr \
    && chown -R ocr:ocr /app /models /tmp/ocr \
    && chmod 0755 /usr/local/bin/library-ocr-entrypoint
USER ocr
ENV OCR_MODEL_DIR=/models
EXPOSE 8010
ENTRYPOINT ["/usr/local/bin/library-ocr-entrypoint"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
