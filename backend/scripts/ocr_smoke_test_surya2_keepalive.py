"""Smoke test without Surya's automatic atexit server shutdown on Windows."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SURYA_INFERENCE_KEEP_ALIVE", "1")
os.environ.setdefault("SURYA_INFERENCE_BACKEND", "llamacpp")
os.environ.setdefault("SURYA_INFERENCE_PARALLEL", "1")

from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.recognition import RecognitionPredictor

if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/ocr_smoke_test_surya2_keepalive.py path/to/sample.png")
path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"File not found: {path}")
with Image.open(path) as im:
    page = im.convert("RGB")
manager = SuryaInferenceManager(method="llamacpp")
rec = RecognitionPredictor(manager)
for result in rec([page]):
    for block in result.blocks:
        print(block.html)
print("Surya 2 OCR completed; inference server remains running for reuse.")
