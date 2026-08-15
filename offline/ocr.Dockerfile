ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV OPENBLAS_CORETYPE=ATOM \
    PADDLE_PDX_MODEL_SOURCE=modelscope

USER root
WORKDIR /app
COPY ocr_service/vendor/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl /tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl
RUN printf '%s  %s\n' \
      '80d0ed4ce96859395cf634d4c3e06df4527ea2abdffc826f24b8f6bc68656f39' \
      '/tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl' | sha256sum -c - \
    && (python -m pip uninstall -y paddlepaddle >/dev/null 2>&1 || true) \
    && python -m pip install --no-index --force-reinstall --no-deps /tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl \
    && python -c 'import numpy as np, paddle; assert paddle.__version__ == "3.3.1", paddle.__version__; actual = paddle.matmul(paddle.to_tensor([[1.0, 2.0], [3.0, 4.0]], dtype="float32"), paddle.to_tensor([[2.0], [1.0]], dtype="float32")).numpy(); np.testing.assert_allclose(actual, np.array([[4.0], [10.0]], dtype=np.float32), rtol=0, atol=0)' \
    && rm -f /tmp/paddlepaddle-3.3.1-cp311-cp311-manylinux_2_35_x86_64.manylinux_2_36_x86_64.whl
COPY --chown=ocr:ocr ocr_service/app.py /app/app.py
COPY --chown=ocr:ocr ocr_service/model_probe.py /app/model_probe.py
COPY ocr_service/docker-entrypoint.sh /usr/local/bin/library-ocr-entrypoint
RUN chmod 0755 /usr/local/bin/library-ocr-entrypoint
USER ocr
ENTRYPOINT ["/usr/local/bin/library-ocr-entrypoint"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
