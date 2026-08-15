ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
WORKDIR /app
COPY offline/python-wheels/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl /tmp/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
RUN printf '%s  %s\n' \
      '80bab7bfc629882493af4aa31a4cfa43a4c57c83813253626916b8c7ada83476' \
      '/tmp/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl' | sha256sum -c - \
    && python -m pip install --no-index --no-deps /tmp/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
    && python -c 'import yaml; assert yaml.__version__ == "6.0.2", yaml.__version__' \
    && rm -f /tmp/PyYAML-6.0.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
COPY --chown=library:library api/ /app/
USER library
