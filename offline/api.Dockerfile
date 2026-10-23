ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
WORKDIR /app
COPY offline/security-20261024/api-runtime/requirements-linux.lock /tmp/stl-requirements.txt
COPY offline/security-20261024/api-runtime/wheels/ /tmp/stl-security-wheels/
RUN python -m pip install --no-index --find-links=/tmp/stl-security-wheels pip==26.2.2 \
    && python -m pip install --no-index --find-links=/tmp/stl-security-wheels --require-hashes --no-deps -r /tmp/stl-requirements.txt \
    && python -m pip check \
    && rm -rf /tmp/stl-security-wheels /tmp/stl-requirements.txt
COPY --chown=library:library api/ /app/
USER library
