import os
import json
import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv
import sys
import re
from datetime import datetime

# ---------------- CONFIGURACIÓN ----------------
load_dotenv(".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print(json.dumps({"error": "GEMINI_API_KEY no encontrada"}, ensure_ascii=False))
    sys.exit(1)

genai.configure(api_key=api_key)

model = genai.GenerativeModel(
    "gemini-2.0-flash-exp",
    generation_config={
        "temperature": 0,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json",
    }
)

MAX_CHARS = 100000

# ---------------- FUNCIONES ----------------

def extract_text(file_path):
    """Extrae texto de PDF o TXT."""
    if file_path.lower().endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
            return " ".join(pages)
    elif file_path.lower().endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return None

def truncate_smart(text, max_chars):
    """Trunca el texto inteligentemente."""
    if len(text) <= max_chars:
        return text
    
    start_portion = int(max_chars * 0.7)
    end_portion = max_chars - start_portion
    
    return text[:start_portion] + "\n\n[...TRUNCADO...]\n\n" + text[-end_portion:]

def build_prompt(document_text, file_path):
    """Prompt para extraer JSON con campos exactos de DB."""
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

def clean_json_string(json_str):
    """Limpia JSON corrupto."""
    json_str = re.sub(r'```json\s*', '', json_str)
    json_str = re.sub(r'```\s*', '', json_str)
    json_str = json_str.strip()
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Buscar primer objeto JSON completo
    stack = []
    start_idx = -1
    
    for i, char in enumerate(json_str):
        if char == '{':
            if not stack:
                start_idx = i
            stack.append('{')
        elif char == '}':
            if stack:
                stack.pop()
                if not stack and start_idx != -1:
                    try:
                        return json.loads(json_str[start_idx:i+1])
                    except json.JSONDecodeError:
                        continue
    
    raise json.JSONDecodeError("No se encontró JSON válido", json_str, 0)

def analyze_document(document_text, file_path):
    """Envía el documento y retorna JSON."""
    document_text = truncate_smart(document_text, MAX_CHARS)
    prompt = build_prompt(document_text, file_path)
    
    try:
        response = model.generate_content(prompt)
        output = response.text.strip()
        return clean_json_string(output)
        
    except json.JSONDecodeError as e:
        return {
            "error": "JSON inválido",
            "details": str(e),
            "raw_preview": output[:300] if 'output' in locals() else "N/A"
        }
    except Exception as e:
        return {"error": str(e)}

# ---------------- MAIN ----------------

if __name__ == "__main__":
    file_path = "documento_difuso.pdf"
    
    text = extract_text(file_path)
    if not text:
        print(json.dumps({"error": "No se pudo leer el archivo"}, ensure_ascii=False))
        sys.exit(1)
    
    result = analyze_document(text, file_path)
    
    # SALIDA: JSON plano directo
    print(json.dumps(result, indent=2, ensure_ascii=False))