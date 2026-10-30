# KNOWALL — Surya OCR 2 setup (October 2026)

Use `surya-ocr==0.22.1` with a Windows CPU `llama-server.exe` binary from llama.cpp.
This replaces the earlier `0.17.1` instructions and `scripts/ocr_smoke_test.py`.

## Preserve your Flask backend

From `KNOWALL\backend` in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip show surya-ocr
python -m pip freeze > requirements-before-surya2.txt
deactivate
py -3.11 -m venv .venv-surya
.\.venv-surya\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "surya-ocr==0.22.1"
python -m pip check
```

## Install llama.cpp binary (required; no Docker)

Download the **Windows x64 (CPU)** ZIP from https://github.com/ggml-org/llama.cpp/releases
Extract to e.g. `C:\tools\llama.cpp`, keeping all DLLs together.
Find `llama-server.exe` inside the extracted folder and set the exact path:

```powershell
$env:LLAMA_CPP_BINARY="C:\tools\llama.cpp\llama-server.exe"
$env:SURYA_INFERENCE_BACKEND="llamacpp"
$env:SURYA_INFERENCE_PARALLEL="1"
& $env:LLAMA_CPP_BINARY --version
```

If the exe is inside a nested subfolder, change `LLAMA_CPP_BINARY` accordingly.

## Test (while .venv-surya is active)

```powershell
python scripts\ocr_smoke_test_surya2.py ocr_samples\fictional_occupancy_letter.png
```

The first run may download model files; it needs internet, disk space, and adequate RAM. CPU processing can be slow. This kit has not been run against Surya model inference here.

To use the Surya CLI directly:

```powershell
surya_ocr .\ocr_samples\fictional_occupancy_letter.png --output_dir .\ocr_samples\v2_output
```

Surya 2 outputs `blocks` with `html`, unlike Surya 1's `text_lines`.

## Already installed 0.17.1?

Keep the Flask `.venv` unchanged while testing `.venv-surya`. The older download does not prevent installation in the new environment. If you installed 0.17.1 into a separate OCR environment that you explicitly want to replace, activate **that OCR environment only**, then run:

```powershell
python -m pip uninstall -y surya-ocr
python -m pip install "surya-ocr==0.22.1"
```

Do not install v2 over your known-good Flask backend environment until the OCR smoke test and dependency check pass. When integrated, rerun all Flask Pytest tests and test real extraction. Model output must be reviewed by an authorized admin; OCR alone does not verify authenticity.

Sources: https://pypi.org/project/surya-ocr/ ; https://github.com/datalab-to/surya ; https://github.com/ggml-org/llama.cpp/releases
