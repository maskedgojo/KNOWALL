"""Smoke test for Surya OCR 2 (surya-ocr==0.22.1). Windows CPU via llama.cpp."""
import argparse
from pathlib import Path
from html.parser import HTMLParser
from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.recognition import RecognitionPredictor

class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
    def handle_data(self, text):
        self.parts.append(text)

def main():
    p=argparse.ArgumentParser(description="Run Surya OCR 2 on an image")
    p.add_argument('image',type=Path)
    a=p.parse_args()
    if not a.image.is_file():
        raise SystemExit(f"Image file not found: {a.image}")
    manager=SuryaInferenceManager(method="llamacpp")
    recognition=RecognitionPredictor(manager)
    with Image.open(a.image) as original:
        img=original.convert("RGB")
    results=recognition([img])
    for page_no,page in enumerate(results,1):
        print(f"\n=== PAGE {page_no} ===")
        for block in page.blocks:
            parser=TextOnly()
            parser.feed(block.html or "")
            text=' '.join(' '.join(parser.parts).split())
            if text:
                print(text)
    print("\nSurya 2 inference completed. Compare extracted fields manually.")

if __name__=='__main__':
    main()
