# downloader.py
import os
import shutil
import time
from pathlib import Path
from config import DOCS_DIR, SAMPLE_DIR

MANIFEST_FILE = Path("manifest.txt")


def get_manifest_entries():
    """
    Lee manifest.txt y retorna set de nombres de archivos ya registrados.
    Si no existe, retorna set vacío.
    """
    if not MANIFEST_FILE.exists():
        return set()
    
    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception as e:
        print(f"  [manifest] Error leyendo manifest.txt: {e}")
        return set()


def add_to_manifest(filename: str):
    """
    Añade filename al manifest.txt si no existe ya.
    Crea el archivo si no existe.
    """
    current_entries = get_manifest_entries()
    
    if filename in current_entries:
        return  # Ya está en el manifest
    
    try:
        with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
            f.write(f"{filename}\n")
        print(f"  [manifest] ✅ Añadido: {filename}")
    except Exception as e:
        print(f"  [manifest] ❌ Error añadiendo {filename}: {e}")


def discover_new_files_in_sample():
    """
    Escanea sample_sources/ y retorna lista de archivos PDF que NO están en manifest.txt
    """
    if not SAMPLE_DIR.exists():
        return []
    
    manifest_entries = get_manifest_entries()
    all_pdfs = list(SAMPLE_DIR.glob("*.pdf"))
    
    # ✅ CORRECCIÓN: Comparar contra manifest, NO contra docs/
    new_files = [
        pdf for pdf in all_pdfs 
        if pdf.name not in manifest_entries
    ]
    
    return new_files


def simulate_download_from_sample(filename: str, update_manifest: bool = True):
    """
    Simula la "descarga" copiando filename desde sample_sources -> docs.
    Si update_manifest=True, añade al manifest.txt automáticamente.
    Retorna Path destino o None si no existe el archivo fuente.
    """
    src = SAMPLE_DIR / filename
    dst = DOCS_DIR / filename
    
    try:
        if not src.exists():
            print(f"  [download] ⚠️  Fuente no existe: {src}")
            return None
        
        # Copia atómica a archivo temporal + rename
        tmp = DOCS_DIR / (filename + ".tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        
        print(f"  [download] ✅ {filename} → docs/")
        
        # Actualizar manifest automáticamente
        if update_manifest:
            add_to_manifest(filename)
        
        return dst
        
    except Exception as e:
        print(f"  [download] ❌ Error copiando {src}: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except:
            pass
        return None


def check_and_download_new_files():
    """
    Busca archivos nuevos en sample_sources/ que NO estén en manifest.txt,
    los descarga y actualiza el manifest.
    Retorna lista de nuevos archivos descargados.
    """
    new_files = discover_new_files_in_sample()
    
    if not new_files:
        return []
    
    print(f"\n🆕 Detectados {len(new_files)} archivo(s) nuevo(s) en sample_sources/")
    
    downloaded = []
    for pdf in new_files:
        print(f"  📥 Descargando: {pdf.name}")
        p = simulate_download_from_sample(pdf.name, update_manifest=True)
        if p:
            downloaded.append(p)
        time.sleep(0.2)
    
    return downloaded


def download_batch_simulated():
    """
    Descarga todos los archivos que ya están en manifest.txt
    (para procesamiento inicial de archivos existentes).
    Retorna lista de Paths en docs/.
    """
    copied = []
    
    if not MANIFEST_FILE.exists():
        print("  [download] 📝 No hay manifest.txt, creando uno nuevo...")
        return []
    
    manifest_entries = get_manifest_entries()
    
    if not manifest_entries:
        print("  [download] 📝 Manifest vacío")
        return []
    
    print(f"  [download] 📋 Procesando {len(manifest_entries)} archivo(s) del manifest...")
    
    for filename in manifest_entries:
        src = SAMPLE_DIR / filename
        dst = DOCS_DIR / filename
        
        # Si ya existe en docs/, no copiar de nuevo
        if dst.exists():
            copied.append(dst)
            continue
        
        # Si existe en sample_sources/, copiarlo
        if src.exists():
            p = simulate_download_from_sample(filename, update_manifest=False)
            if p:
                copied.append(p)
            time.sleep(0.1)
    
    return copied