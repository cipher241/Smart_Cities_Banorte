# cleaner.py
import re

def to_number_simple(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).lower().replace(",", "").strip()
    if s in ("", "null", "none", "-"):
        return None
    m = re.search(r'(\d+(\.\d+)?)\s*mill', s)
    if m:
        return float(m.group(1)) * 1_000_000
    k = re.search(r'(\d+(\.\d+)?)\s*mil', s)
    if k:
        return float(k.group(1)) * 1_000
    d = re.search(r'(\d+(\.\d+)?)', s)
    if d:
        return float(d.group(1))
    return None

def normalize_record(rec: dict) -> dict:
    # Ensure keys
    rec = dict(rec)  # copy
    rec.setdefault("nombre", None)
    rec.setdefault("sector", None)
    rec.setdefault("doc_fuente", None)
    rec.setdefault("fecha_carga", None)

    for k in ["presupuesto_total_mxn","beneficiarios_estimados","costo_operativo_mxn","costo_mantenimiento_mxn","impacto_fisico","kpi","score_costo_beneficio","eficiencia_financiera"]:
        if k in rec:
            rec[k] = to_number_simple(rec.get(k))

    for ky in ("anio_inicio","anio_fin"):
        v = rec.get(ky)
        if v in (None,"", "null"):
            rec[ky] = None
        else:
            try:
                rec[ky] = int(str(v).strip()[:4])
            except:
                rec[ky] = None

    # confianza normalization if present
    if isinstance(rec.get("confianza"), dict):
        for ck, cv in rec["confianza"].items():
            try:
                rec["confianza"][ck] = float(cv)
            except:
                rec["confianza"][ck] = None

    return rec
