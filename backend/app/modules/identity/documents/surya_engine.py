"""Surya 2 adapter: lazy-loaded once per Flask worker; no eager model loading."""
import os
import threading
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

from .storage import MAX_PDF_PAGES

_lock = threading.Lock()
_predictor = None


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")


def _get_predictor():
    global _predictor
    with _lock:
        if _predictor is None:
            # IMPORTANT: set before importing Surya settings, to bypass its
            # unreliable Windows atexit process termination routine.
            os.environ.setdefault("SURYA_INFERENCE_KEEP_ALIVE", "1")
            os.environ.setdefault("SURYA_INFERENCE_BACKEND", "llamacpp")
            os.environ.setdefault("SURYA_INFERENCE_PARALLEL", "1")
            from surya.inference import SuryaInferenceManager
            from surya.recognition import RecognitionPredictor
            _predictor = RecognitionPredictor(SuryaInferenceManager(method="llamacpp"))
        return _predictor


def _pages(path: Path, mime: str):
    if mime == "application/pdf":
        import pymupdf
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass or not 1 <= len(pdf) <= MAX_PDF_PAGES:
                raise ValueError("Unsupported PDF page count or password protection.")
            for page in pdf:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                if pix.width * pix.height > 12_000_000:
                    raise ValueError("Rendered PDF page is too large.")
                yield Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    else:
        with Image.open(path) as img:
            yield img.convert("RGB")


def extract_text(path: Path, mime: str) -> str:
    predictor = _get_predictor()
    text_parts = []
    with _inference_lock:
        for page in _pages(path, mime):
            predictions = predictor([page])
            for result in predictions:
                for block in result.blocks:
                    p = _PlainText()
                    p.feed(block.html or "")
                    text_parts.append("".join(p.parts).strip())
    return "\n".join(p for p in text_parts if p).strip()


_inference_lock = threading.Lock()
