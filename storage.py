# storage.py
import json
import csv
from pathlib import Path
from config import OUTPUT_JSON, OUTPUT_CSV, PROCESADOS_FILE

def load_procesados():
    if PROCESADOS_FILE.exists():
        try:
            return json.loads(PROCESADOS_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_procesados(data):
    PROCESADOS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def append_record_json(record: dict):
    existing = []
    if OUTPUT_JSON.exists():
        try:
            existing = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except:
            existing = []
    existing.append(record)
    OUTPUT_JSON.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

def append_record_csv(record: dict):
    fieldnames = ["nombre","sector","doc_fuente","presupuesto_total_mxn","anio_inicio","anio_fin","beneficiarios_estimados","_validation"]
    write_header = not OUTPUT_CSV.exists()
    with OUTPUT_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "nombre": record.get("nombre"),
            "sector": record.get("sector"),
            "doc_fuente": record.get("doc_fuente"),
            "presupuesto_total_mxn": record.get("presupuesto_total_mxn"),
            "anio_inicio": record.get("anio_inicio"),
            "anio_fin": record.get("anio_fin"),
            "beneficiarios_estimados": record.get("beneficiarios_estimados"),
            "_validation": record.get("_validation","")
        })
