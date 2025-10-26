# config.py
from pathlib import Path

DOCS_DIR = Path("docs")
SAMPLE_DIR = Path("sample_sources")  # put your sample PDFs here
PROCESADOS_FILE = Path("procesados.json")
OUTPUT_JSON = Path("salida_limpia.json")
OUTPUT_CSV = Path("results.csv")
DEBUG_DIR = Path("debug")
DOCS_DIR.mkdir(exist_ok=True)
SAMPLE_DIR.mkdir(exist_ok=True)
DEBUG_DIR.mkdir(exist_ok=True)
