FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-noto-cjk fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home preview \
    && mkdir -p /app /run/docx-preview && chmod 0777 /run/docx-preview
WORKDIR /app
# Record the actual converter and installed font packages, not a guessed version.
RUN python -c 'import hashlib,json,pathlib,subprocess; root=pathlib.Path("/usr/share/fonts"); p=b"".join(str(f.relative_to(root)).encode()+hashlib.sha256(f.read_bytes()).digest() for f in sorted(root.rglob("*")) if f.is_file()); v=subprocess.check_output(["/usr/bin/libreoffice","--version"],text=True).strip(); pathlib.Path("/app/converter-build.json").write_text(json.dumps({"converter":v,"fonts":hashlib.sha256(p).hexdigest()}))'
COPY app.py /app/app.py
USER 10001:10001
CMD ["python", "/app/app.py"]
