# analyzer.py
import os, re, json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()  # permite que GEMINI_API_KEY esté en .env

try:
    import google.generativeai as genai
except Exception:
    genai = None

# Configura/instancia el modelo si es posible.
MODEL_NAME = "gemini-2.0-flash-exp"

def init_gemini_model(api_key: str):
    if genai is None:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)

def clean_json_string(json_str: str):
    """Extrae el primer objeto JSON balanceado del texto."""
    if not json_str:
        return None
    s = re.sub(r"```json|```", "", json_str).strip()
    start = None
    depth = 0
    for i,ch in enumerate(s):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = s[start:i+1]
                try:
                    return json.loads(candidate)
                except Exception:
                    start = None
                    depth = 0
    # fallback
    try:
        return json.loads(s)
    except Exception:
        return None

def build_prompt(document_text: str, file_path: str) -> str:
    fn = os.path.basename(file_path)
    fecha = datetime.now().strftime("%Y-%m-%d")
    # Usa el prompt que ya diseñaste (resumido para mantenerlo legible)
    return f"""Eres un extractor de datos para base de datos. Analiza el documento y devuelve UN SOLO objeto JSON con estos campos:

{{
  "nombre": (string, nombre del proyecto),
  "sector": (string, UNO DE: "Agua", "Energía", "Transporte", "Infraestructura", "Salud", "Educación", "Medio Ambiente", "Desarrollo Social"),
  "dependencia": (string, organismo responsable),
  "ubicacion": (string, ciudad/estado),
  "anio_inicio": (integer 4 dígitos o null),
  "anio_fin": (integer 4 dígitos o null),
  "doc_fuente": (string, nombre del documento o "{os.path.basename(file_path)}"),
  "fecha_carga": "{datetime.now().strftime('%Y-%m-%d')}",
  "presupuesto_total_mxn": (float, convertir a número: "15 millones" = 15000000.0, "500 mil" = 500000.0, o null),
  "costo_operativo_mxn": (float, convertir a número o null),
  "costo_mantenimiento_mxn": (float, convertir a número o null),
  "costo_beneficio_estimado_mxn": (float o null),
  "eficiencia_financiera": (float 0-100 porcentaje o null),
  "riesgo_financiero": (string o null),
  "score_costo_beneficio": (float 0.0-10.0 evaluando el proyecto o null),
  "analisis_financiero": (string, resumen análisis o null),
  "resumen_observaciones": (string, notas importantes o null),
  "comparativo": (string o null),
  "beneficiarios_estimados": (float, convertir a número: "100 mil" = 100000.0, "más de 50000" = 50000.0, o null),
  "impacto_principal": (string, máximo 200 chars o null),
  "indicador_principal": (string o null),
  "impacto_fisico": (float o null),
  "kpi": (float o null)
}}

REGLAS:
1. Devuelve UN SOLO objeto JSON (no array, no múltiples objetos)
2. **CONVERSIÓN DE NÚMEROS:**
   - "15 millones de pesos" → 15000000.0
   - "más de 15 millones" → 15000000.0
   - "500 mil pesos" → 500000.0
   - "100 mil habitantes" → 100000.0
   - "más de 50,000 personas" → 50000.0
3. años como integers: 2024, 2025 (NO strings)
4. Si no existe dato: null
5. COHERENCIA: Si dice "mediano plazo" desde 2024 → anio_fin: 2026
6. score_costo_beneficio: Evalúa 0-10 según viabilidad del proyecto
7. NO inventes datos, pero sí convierte textos a números cuando sea posible
8. Responde SOLO el JSON, sin texto adicional

DOCUMENTO:
{document_text}"""

def analyze_with_gemini(model, document_text: str, file_path: str, max_output_tokens: int = 2048):
    """Si model es None, retorna None para fallback en main (heurística)."""
    if model is None:
        return None
    prompt = build_prompt(document_text, file_path)
    try:
        resp = model.generate_content(prompt, generation_config=genai.GenerationConfig(temperature=0.0, max_output_tokens=max_output_tokens))
        raw = resp.text or ""
        parsed = clean_json_string(raw)
        if parsed is None:
            return {"_error": "llm_no_json", "raw_preview": raw[:1000]}
        return parsed
    except Exception as e:
        return {"_error": "llm_exception", "details": str(e)}
