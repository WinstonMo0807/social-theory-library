# Import the clean image built with ocr_service/Dockerfile, exported with docker save.
# Retired Paddle images cannot be used as an offline base.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
WORKDIR /app
RUN python -c "from importlib.metadata import version, packages_distributions; assert version('rapidocr') == '3.10.0'; assert version('onnxruntime') == '1.31.0'; assert 'paddle' not in packages_distributions()"
COPY --chown=ocr:ocr ocr_service/app.py ocr_service/model_probe.py ocr_service/rapid_models.py ocr_service/rapid_runtime.py /app/
COPY ocr_service/docker-entrypoint.sh /usr/local/bin/library-ocr-entrypoint
RUN chmod 0755 /usr/local/bin/library-ocr-entrypoint
USER ocr
ENTRYPOINT ["/usr/local/bin/library-ocr-entrypoint"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
