"""Private local storage for demonstration documents; never write under /static."""
import hashlib
import os
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import BadRequest

try:
    import pymupdf
except ImportError:
    pymupdf = None

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 3
IMAGE_MAX_PIXELS = 12_000_000
Image.MAX_IMAGE_PIXELS = IMAGE_MAX_PIXELS

MIME_BY_EXTENSION = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
EXT_BY_MIME = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


def validate_document(name: str, data: bytes) -> str:
    extension = Path(name or "").suffix.lower()
    if extension not in MIME_BY_EXTENSION:
        raise ValueError("Only PDF, JPG and PNG documents are allowed.")
    if not 0 < len(data) <= MAX_FILE_BYTES:
        raise ValueError("Document must be between 1 byte and 5 MB.")
    mime = MIME_BY_EXTENSION[extension]
    if mime == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF contents.")
        if pymupdf is None:
            raise RuntimeError("PyMuPDF is required to validate PDF uploads.")
        try:
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if pdf.needs_pass or not 1 <= len(pdf) <= MAX_PDF_PAGES:
                    raise ValueError("Only unencrypted PDFs of up to three pages are supported.")
                for page in pdf:
                    if page.rect.width <= 0 or page.rect.height <= 0:
                        raise ValueError("PDF contains an invalid page.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Invalid or damaged PDF.") from exc
    else:
        import io
        try:
            with Image.open(io.BytesIO(data)) as im:
                if (mime == "image/png" and im.format != "PNG") or (mime == "image/jpeg" and im.format != "JPEG"):
                    raise ValueError("Image bytes do not match its filename extension.")
                if im.width * im.height > IMAGE_MAX_PIXELS:
                    raise ValueError("Image dimensions are too large.")
                im.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Invalid or damaged image.") from exc
    return mime


def storage_root(config) -> Path:
    root = Path(config["OCR_PRIVATE_DIR"]).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def write_private(config, data: bytes, mime: str) -> tuple[str, str]:
    key = f"{uuid.uuid4().hex}{EXT_BY_MIME[mime]}"
    target = storage_root(config) / key
    # Exclusive creation; filenames are random and never taken from users.
    with open(target, "xb") as stream:
        stream.write(data)
    if os.name != "nt":
        os.chmod(target, 0o600)
    return key, hashlib.sha256(data).hexdigest()


def private_path(config, key: str) -> Path:
    if not isinstance(key, str) or Path(key).name != key or key.startswith("."):
        raise ValueError("Invalid document storage key.")
    root = storage_root(config)
    target = (root / key).resolve()
    if target.parent != root:
        raise ValueError("Unsafe document storage path.")
    return target
