# extractor.py
from pathlib import Path
import pdfplumber

def extract_text(path: Path) -> str:
    """Extrae texto de PDF con pdfplumber. Si no extrae, devuelve ''."""
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(pages).strip()
    except Exception as e:
        print(f"[extractor] error leyendo {path.name}: {e}")
        return ""
