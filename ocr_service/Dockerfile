FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    PADDLE_PDX_MODEL_SOURCE=modelscope \
    OPENBLAS_CORETYPE=ATOM

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY vendor/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl /tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl
RUN printf '%s  %s\n' \
      '80d0ed4ce96859395cf634d4c3e06df4527ea2abdffc826f24b8f6bc68656f39' \
      '/tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl' | sha256sum -c - \
    && python -m pip install --no-index --no-deps /tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl \
    && rm -f /tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -c 'import numpy as np, paddle; assert paddle.__version__ == "3.3.1", paddle.__version__; actual = paddle.matmul(paddle.to_tensor([[1.0, 2.0], [3.0, 4.0]], dtype="float32"), paddle.to_tensor([[2.0], [1.0]], dtype="float32")).numpy(); np.testing.assert_allclose(actual, np.array([[4.0], [10.0]], dtype=np.float32), rtol=0, atol=0)'

COPY app.py .
COPY model_probe.py .
COPY docker-entrypoint.sh /usr/local/bin/library-ocr-entrypoint

RUN addgroup --system ocr && adduser --system --ingroup ocr ocr \
    && mkdir -p /models /tmp/ocr \
    && chown -R ocr:ocr /app /models /tmp/ocr \
    && chmod 0755 /usr/local/bin/library-ocr-entrypoint

USER ocr
ENV PADDLE_HOME=/models

EXPOSE 8010
ENTRYPOINT ["/usr/local/bin/library-ocr-entrypoint"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
