"""Private, bounded DOCX conversion over a Unix socket; no network or credentials."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import signal
import shutil
import socketserver
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAX_INPUT = 12 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
TIMEOUT = 75
SOCKET = Path("/run/docx-preview/preview.sock")
SLOT = threading.BoundedSemaphore(1)
BUILD = Path("/app/converter-build.json")


class ConversionError(ValueError):
    pass


class PackageXML(ElementTree.TreeBuilder):
    def doctype(self, *_args):
        raise ConversionError("active_content")


def validate_docx(blob):
    """Reject active / externally linked packages before the isolated renderer opens them."""
    if not 0 < len(blob) <= MAX_INPUT:
        raise ConversionError("input_size")
    try:
        with ZipFile(io.BytesIO(blob)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (len(entries) > 3000 or len(names) != len(set(names)) or "word/document.xml" not in names
                    or sum(entry.file_size for entry in entries) > MAX_EXPANDED):
                raise ConversionError("invalid_package")
            for entry in entries:
                name = entry.filename.lower()
                if (entry.flag_bits & 1 or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                        or "\\" in name or name.startswith(("word/embeddings/", "word/activex/"))
                        or "vba" in name):
                    raise ConversionError("active_content")
                if not name.endswith((".xml", ".rels")):
                    continue
                xml = archive.read(entry)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ConversionError("active_content")
                root = ElementTree.fromstring(xml, parser=ElementTree.XMLParser(target=PackageXML()))
                fields = []
                for element in root.iter():
                    content_type = element.attrib.get("ContentType", "").lower()
                    relationship_type = element.attrib.get("Type", "").lower().rsplit("/", 1)[-1]
                    if (any(value in content_type for value in ("macroenabled", "vbaproject", "oleobject", "activex"))
                            or relationship_type in {"oleobject", "package", "control", "activexcontrol"}):
                        raise ConversionError("active_content")
                    if (element.attrib.get("TargetMode") == "External"
                            and not element.attrib.get("Type", "").endswith("/hyperlink")):
                        raise ConversionError("external_content")
                    instruction = element.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instr", "")
                    if element.tag.endswith("}fldChar"):
                        marker = element.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fldCharType")
                        if marker == "begin":
                            fields.append("")
                        elif marker == "end" and fields:
                            instruction += fields.pop()
                    if element.tag.endswith("}instrText"):
                        instruction += element.text or ""
                        if fields:
                            fields[-1] += element.text or ""
                    if any(token in instruction.upper().split() for token in ("DDE", "DDEAUTO", "INCLUDETEXT", "INCLUDEPICTURE")):
                        raise ConversionError("active_content")
                if any(token in field.upper().split() for field in fields for token in ("DDE", "DDEAUTO", "INCLUDETEXT", "INCLUDEPICTURE")):
                    raise ConversionError("active_content")
    except (BadZipFile, ElementTree.ParseError, KeyError, RuntimeError) as exc:
        raise ConversionError("invalid_package") from exc


def convert(blob):
    validate_docx(blob)
    with tempfile.TemporaryDirectory(prefix="docx-", dir="/tmp") as directory:
        root = Path(directory)
        source, output, profile = root / "input.docx", root / "output", root / "profile"
        source.write_bytes(blob)
        output.mkdir()
        (profile / "user").mkdir(parents=True)
        (profile / "user" / "registrymodifications.xcu").write_text(
            '<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" '
            'oor:op="fuse"><value>3</value></prop></item></oor:items>', encoding="utf-8")
        command = ["/usr/bin/libreoffice", "-env:UserInstallation=" + profile.as_uri(), "--headless", "--nologo",
                   "--nodefault", "--norestore", "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(output), str(source)]
        # Output may contain document text or paths, so discard it instead of logging it.
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, cwd=root, env={"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root),
                                                "LANG": "C.UTF-8", "SAL_USE_VCLPLUGIN": "svp"})
        try:
            if process.wait(timeout=TIMEOUT) != 0:
                raise ConversionError("conversion_failed")
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("conversion_timeout") from exc
        finally:
            # Terminate the complete per-request process group, including descendants.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        pdf = output / "input.pdf"
        if not pdf.is_file() or not 0 < pdf.stat().st_size <= MAX_OUTPUT:
            raise ConversionError("output_size")
        result = pdf.read_bytes()
        if not result.startswith(b"%PDF-"):
            raise ConversionError("invalid_output")
        return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "PrivateDocumentPreview/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_args):
        pass  # No filenames, original text, paths, or request bodies in logs.

    def send(self, status, body, content_type="application/json", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            return self.send(404, b'{"code":"not_found"}')
        self.send(200, json.dumps({"ready": BUILD.exists(), "transport": "unix_socket"}).encode())

    def do_POST(self):
        if self.path != "/convert" or self.headers.get("Transfer-Encoding"):
            return self.send(400, b'{"code":"invalid_request"}')
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_INPUT:
            return self.send(413, b'{"code":"input_size"}')
        if not SLOT.acquire(blocking=False):
            return self.send(503, b'{"code":"busy"}')
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ConversionError("invalid_request")
            pdf = convert(body)
            build = json.loads(BUILD.read_text(encoding="utf-8"))
            self.send(200, pdf, "application/pdf", {"X-Source-SHA256": hashlib.sha256(body).hexdigest(),
                "X-Output-SHA256": hashlib.sha256(pdf).hexdigest(), "X-Converter-Version": build["converter"],
                "X-Fonts-Version": build["fonts"], "X-Preview-Protocol": "1"})
        except ConversionError as exc:
            self.send(422, json.dumps({"code": str(exc)}).encode())
        except (OSError, ValueError, KeyError):
            self.send(503, b'{"code":"conversion_unavailable"}')
        finally:
            SLOT.release()


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    request_queue_size = 4

    def handle_error(self, *_args):
        pass


if __name__ == "__main__":
    # This dedicated volume contains only a socket; uploaded bytes live in tmpfs.
    for leftover in Path("/tmp").glob("docx-*"):
        if leftover.is_symlink() or not leftover.is_dir():
            leftover.unlink(missing_ok=True)
        else:
            shutil.rmtree(leftover)
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        SOCKET.chmod(0o666)
        server.serve_forever()
