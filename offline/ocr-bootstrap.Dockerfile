# Clean initial offline deployment. Build context contains ocr_service sources,
# requirements-linux.lock, wheels/ and models/. Assets are not committed to Git.
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-linux.lock /tmp/requirements-linux.lock
COPY wheels/ /tmp/wheels/
RUN pip install --no-index --find-links=/tmp/wheels pip==26.2.2 && pip install --no-index --find-links=/tmp/wheels --require-hashes -r /tmp/requirements-linux.lock && pip check && rm -rf /tmp/wheels
COPY models/ /opt/ocr-models/
COPY app.py rapid_models.py rapid_runtime.py toc_layout.py model_probe.py ./
RUN python -c "from rapid_models import verify_models; verify_models('/opt/ocr-models')"
COPY docker-entrypoint.sh /usr/local/bin/library-ocr-entrypoint
RUN addgroup --system ocr && adduser --system --ingroup ocr --home /nonexistent ocr && mkdir -p /models /tmp/ocr && chown -R ocr:ocr /models /tmp/ocr /app && chmod 0755 /usr/local/bin/library-ocr-entrypoint
USER ocr
ENV OCR_MODEL_DIR=/models
EXPOSE 8010
ENTRYPOINT ["/usr/local/bin/library-ocr-entrypoint"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
