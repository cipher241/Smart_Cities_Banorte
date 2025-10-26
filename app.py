# app.py
import os
import json
import logging
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
import pdfplumber

# Gemini
import google.generativeai as genai

# ================== ENV & LOGGING ==================
load_dotenv()

DEBUG_VERBOSE = os.getenv("DEBUG_VERBOSE", "1") == "1"

logging.basicConfig(
    level=logging.DEBUG if DEBUG_VERBOSE else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("banorte-app")

# ================== CONFIG ==================
UPLOAD_FOLDER = "uploads_hackathon"
BEST_PROMPT_FILE = "best_analysis_prompt.txt"
DATASET_FILE = "training_dataset.json"

# Preferencia de modelos (fallback automático)
MODEL_CANDIDATES = [
    os.getenv("GEMINI_MODEL") or "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static", exist_ok=True)

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB


# ================== UTILS ==================
def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def read_text_file(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("No se pudo leer %s: %s", path, e)
        return default


# ================== CORE ANALYZER ==================
class AnalizadorPoliticaPublica:
    def __init__(self):
        self.model_name = None
        self.client = None
        self.best_prompt = self._load_best_prompt()
        self.dataset_context = self._load_dataset()
        self._init_gemini()

        log.info("✅ Sistema inicializado")
        log.info("📊 Prompt cargado | chars=%s", len(self.best_prompt))
        log.info("📚 Dataset base | proyectos=%s", len(self.dataset_context))

    def _init_gemini(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            log.error("❌ GEMINI_API_KEY no encontrada. Define la variable de entorno.")
            self.client = None
            return

        genai.configure(api_key=api_key)

        last_error = None
        for candidate in MODEL_CANDIDATES:
            try:
                self.client = genai.GenerativeModel(candidate)
                self.model_name = candidate
                log.info("🧠 Modelo Gemini activo: %s", candidate)
                return
            except Exception as e:
                last_error = e
                log.warning("⚠️ Falló cargar modelo %s: %s", candidate, e)

        log.error("❌ No se pudo inicializar ningún modelo Gemini: %s", last_error)
        self.client = None

    def _load_best_prompt(self) -> str:
        path = Path(BEST_PROMPT_FILE)
        if not path.exists():
            return self._fallback_prompt()

        try:
            content = read_text_file(path)
            if "=" * 80 in content:
                parts = content.split("=" * 80)
                return (parts[-1].strip() if len(parts) > 2 else content).strip()
            return content.strip()
        except Exception as e:
            log.warning("No se pudo cargar BEST_PROMPT_FILE: %s", e)
            return self._fallback_prompt()

    def _fallback_prompt(self) -> str:
        return (
            "Analiza el proyecto y extrae datos clave.\n"
            "Retorna JSON con: nombre, sector, presupuesto_total_mxn, beneficiarios_estimados, "
            "score_costo_beneficio (0-10), analisis_financiero, riesgo_financiero, recomendaciones."
        )

    def _load_dataset(self):
        path = Path(DATASET_FILE)
        if not path.exists():
            log.warning("Dataset no encontrado (%s). Se continúa sin contexto.", path)
            return []
        try:
            data = json.loads(read_text_file(path, "[]"))
            return data if isinstance(data, list) else []
        except Exception as e:
            log.warning("Dataset inválido: %s", e)
            return []

    def _generate_context(self) -> str:
        if not self.dataset_context:
            return "Dataset no disponible"

        sectores = {p.get("SECTOR") for p in self.dataset_context if p.get("SECTOR")}
        presupuestos = [
            p.get("PRESUPUESTO_TOTAL")
            for p in self.dataset_context
            if p.get("PRESUPUESTO_TOTAL") is not None
        ]
        scores = [
            p.get("SCORE_COSTO_BENEFICIO")
            for p in self.dataset_context
            if p.get("SCORE_COSTO_BENEFICIO") is not None
        ]

        if not presupuestos:
            return f"Base de datos: {len(self.dataset_context)} proyectos"

        try:
            prom_pres = sum(presupuestos) / max(1, len(presupuestos))
            prom_score = sum(scores) / max(1, len(scores)) if scores else 0
            rango_min = min(presupuestos)
            rango_max = max(presupuestos)
        except Exception:
            prom_pres, prom_score, rango_min, rango_max = 0, 0, 0, 0

        return f"""CONTEXTO - BASE DE DATOS ACTUAL:
• Proyectos analizados: {len(self.dataset_context)}
• Sectores: {', '.join(list(sectores)[:5])}
• Presupuesto promedio: ${prom_pres:,.0f} MXN
• Score histórico promedio: {prom_score:.1f}/10
• Rango: ${rango_min:,.0f} - ${rango_max:,.0f} MXN

ENFOQUE DE EVALUACIÓN:
✓ Realismo sobre promesas políticas
✓ Impacto social MEDIBLE
✓ Riesgos financieros ESPECÍFICOS
✓ Comparación con proyectos similares"""

    def extract_text(self, pdf_path: str):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join([(p.extract_text() or "") for p in pdf.pages]).strip()
            if not text or len(text) < 80:
                log.warning("Texto muy corto o vacío tras extracción PDF.")
                return None
            return text
        except Exception as e:
            log.error("Error extrayendo PDF: %s", e)
            return None

    def analyze(self, text: str):
        if not self.client:
            return {"error": "Gemini no disponible. Verifica GEMINI_API_KEY / modelo."}

        context = self._generate_context()
        prompt = f"""{context}

El sistema emplea un modelo de evaluación especializado entrenado con un corpus curado de proyectos públicos,
reforzado con técnicas de prompting y recuperación de contexto, orquestado sobre la API de Gemini. Su objetivo es
asistir a gobiernos de distinta escala en la formulación y priorización de proyectos con mayor impacto social y solidez financiera.

RETORNA ESTRICTAMENTE ESTE JSON (sin texto adicional):
{{
  "nombre": "string",
  "sector": "string",
  "ubicacion": "string",
  "presupuesto_total_mxn": float,
  "beneficiarios_estimados": float,
  "eficiencia_financiera": float,
  "score_costo_beneficio": float,
  "analisis_financiero": "string",
  "riesgo_financiero": "1. ... 2. ... 3. ... 4. ... 5. ...",
  "recomendaciones": "1. ... 2. ... 3. ... 4. ... 5. ..."
}}

CRITERIOS:
- Beneficiarios: si no hay dato explícito, estimar razonablemente (nunca null).
- Riesgos y Recomendaciones: 5 puntos numerados, concretos.
- Análisis financiero: 150-200 palabras, viabilidad, costo—beneficio, sostenibilidad, riesgos.

DOCUMENTO (máx 50k chars):
{text[:50000]}"""

        try:
            resp = self.client.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3, max_output_tokens=8000
                ),
            )
            raw = (resp.text or "").strip()
            log.debug("Respuesta cruda del modelo (recortada): %s", raw[:400])

            if "```json" in raw:
                raw = raw.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in raw:
                raw = raw.split("```", 1)[1]
            raw = raw.strip()

            result = json.loads(raw)

            if safe_float(result.get("beneficiarios_estimados")) <= 0:
                result["beneficiarios_estimados"] = 10000

            if not result.get("riesgo_financiero"):
                result["riesgo_financiero"] = (
                    "1. Información insuficiente. 2. Requiere auditoría completa. "
                    "3. Falta de datos críticos. 4. Riesgo de ejecución. 5. Riesgo de sobrecosto."
                )

            if not result.get("recomendaciones"):
                result["recomendaciones"] = (
                    "1. Solicitar documentación completa. 2. Auditoría independiente. "
                    "3. Rediseñar cronograma. 4. Financiamiento por hitos. 5. KPIs públicos."
                )

            score = safe_float(result.get("score_costo_beneficio"))
            if score >= 9:
                ver = "Banorte recomienda financiamiento prioritario por métricas excepcionales"
            elif score >= 7:
                ver = "Banorte sugiere financiamiento condicionado a supervisión rigurosa"
            elif score >= 5:
                ver = "Banorte no recomienda participación sin reestructuración mayor del proyecto"
            else:
                ver = "Banorte rechaza financiamiento por riesgos críticos identificados"

            result["veredicto_banorte"] = result.get("veredicto_banorte") or ver
            result["justificacion_veredicto"] = result.get("justificacion_veredicto") or (
                "Decisión sustentada en costo—beneficio, riesgos y comparables históricos."
            )

            result["_debug"] = {
                "model": self.model_name,
                "chars_in": len(text),
                "dataset_size": len(self.dataset_context),
            }

            return result

        except json.JSONDecodeError as e:
            log.error("JSON inválido del modelo: %s", e)
            return {"error": "Respuesta inválida del modelo (JSON)"}
        except Exception as e:
            log.exception("Error durante analyze(): %s", e)
            return {"error": str(e)}


# Instancia única del analizador
analizador = AnalizadorPoliticaPublica()


# ================== HTML/JS (UI COMPLETA) ==================
HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>BANORTE • Evaluación de Proyectos Gubernamentales</title>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root{--rojo:#EB0029;--rojo-hover:#DB0026;--gris:#323E48;--gris-sec:#5B6670;--gris-borde:#C1C5C8;--gris-fondo:#F6F6F6;--blanco:#FFFFFF;--success-bg:#E8F5E9;--success-fg:#2E7D32;--error-bg:#FFEBEE;--error-fg:#EB0029;--shadow:0 10px 24px rgba(0,0,0,.08)}
    *{box-sizing:border-box}
    html,body{margin:0;padding:0;background:var(--gris-fondo);color:var(--gris);font-family:"Inter","Segoe UI",Arial,sans-serif}
    .wrap{max-width:1100px;margin:auto;padding:28px 20px 80px}
    .appbar{background:linear-gradient(180deg,#fff 0%,#fff8f9 100%);color:var(--gris);border:1px solid var(--gris-borde);border-radius:16px;padding:18px 22px;display:flex;align-items:center;gap:14px;box-shadow:var(--shadow);position:relative;overflow:hidden}
    .brand{display:flex;align-items:center;gap:14px;margin:auto}
    .brand img{height:46px}
    .brand-title{font-weight:800;letter-spacing:.2px;text-align:center;font-size:18px}
    .subtitle{opacity:.95;font-size:12.5px;margin-top:2px;text-align:center}
    .demo-banner{margin:12px 0 0;background:#FFF1F3;border:1px solid #F8C9D2;color:#7A2432;border-radius:12px;padding:10px 14px;font-size:14px}
    .demo-badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#FFD8DF;color:#7A2432;font-weight:700;font-size:12px;margin-right:8px}
    .grid{display:grid;grid-template-columns:380px 1fr;gap:18px;margin-top:18px}
    @media (max-width:1020px){.grid{grid-template-columns:1fr}}
    .card{background:var(--blanco);border:1px solid var(--gris-borde);border-radius:16px;padding:18px;box-shadow:var(--shadow)}
    .card h3{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--gris);letter-spacing:.2px}
    .upload{border:2px dashed var(--gris-borde);border-radius:14px;padding:28px;text-align:center;background:var(--gris-fondo);transition:.25s;cursor:pointer}
    .upload:hover{border-color:var(--rojo);background:#FFF5F7}
    .upload .big{font-size:15px;font-weight:700;color:var(--gris)}
    .muted{color:var(--gris-sec);font-size:12px}
    .file-pill{display:flex;align-items:center;justify-content:space-between;gap:10px;background:#fff;border:1px solid var(--gris-borde);padding:10px 12px;border-radius:12px;margin-top:12px}
    .hidden{display:none!important}
    .btn-primary{width:100%;margin-top:12px;padding:15px 16px;border:none;border-radius:8px;font-weight:700;color:#fff;background:var(--rojo);cursor:pointer;transition:.2s;letter-spacing:.3px;font-size:15px;box-shadow:var(--shadow)}
    .btn-primary:hover{background:var(--rojo-hover)}
    .btn-primary:disabled{background:#CFD2D3;color:#A2A9AD;cursor:not-allowed}
    .alert{display:none;margin-top:12px;padding:12px 14px;border-radius:8px;font-size:14px;border-left:4px solid transparent}
    .alert.ok{background:var(--success-bg);color:var(--success-fg);border-color:#4CAF50}
    .alert.err{background:var(--error-bg);color:var(--error-fg);border-color:var(--error-fg)}
    .kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    .kpi{background:var(--gris-fondo);border:1px solid var(--gris-borde);border-radius:12px;padding:16px;text-align:center}
    .kpi .label{font-size:12px;color:var(--gris-sec)}
    .kpi .value{margin-top:6px;font-size:24px;font-weight:800;color:var(--gris)}
    .score-card{display:grid;grid-template-columns:240px 1fr;gap:18px;align-items:center}
    @media (max-width:560px){.score-card{grid-template-columns:1fr}}
    .chip{display:inline-flex;align-items:center;gap:8px;background:#fff;border:1px solid var(--gris-borde);border-radius:999px;padding:6px 10px;font-size:12px;color:var(--gris)}
    .scale{display:flex;gap:6px;margin-top:10px}
    .bar{height:8px;flex:1;background:#E7E9EC;border-radius:6px;overflow:hidden}
    .bar>span{display:block;height:100%}
    .section{margin-top:14px;display:grid;gap:10px}
    .section .title{font-weight:800;letter-spacing:.2px;color:var(--gris)}
    .prose{line-height:1.6;font-size:15px;color:var(--gris)}
    .prose ol{margin:0;padding-left:18px}
    .prose li{margin:6px 0}
    .notice{margin-top:12px;border-left:4px solid var(--rojo);background:#FFF1F3;color:#7A2432;padding:12px 14px;border-radius:10px;font-size:14px}
    .veredicto{border:2px solid var(--rojo);border-radius:12px;padding:16px;display:grid;gap:10px;background:#FFF5F7}
    .v-title{font-weight:900;font-size:16px;letter-spacing:.3px;color:var(--gris)}
    .v-text{color:var(--gris)}
    .v-just{color:var(--gris-sec);font-size:14px}
    .footer{margin-top:22px;text-align:center;color:var(--gris-sec);font-size:12px}
    .overlay{position:fixed;inset:0;background:rgba(50,62,72,.28);backdrop-filter:blur(2px);display:none;align-items:center;justify-content:center;z-index:9999}
    .loader{background:#fff;border:1px solid var(--gris-borde);border-radius:12px;padding:18px 20px;width:min(92%,360px);box-shadow:var(--shadow);color:var(--gris);text-align:center}
    .spinner{width:42px;height:42px;border:4px solid #E7E9EC;border-top:4px solid var(--rojo);border-radius:50%;margin:0 auto 12px;animation:spin 1s linear infinite}
    @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
    .loader-title{font-weight:800;margin-bottom:4px}
    .loader-sub{font-size:13px;color:#5B6670}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="appbar">
      <div class="brand">
        <img src="/static/Logo.png" alt="Banorte" onerror="this.onerror=null;this.src='https://upload.wikimedia.org/wikipedia/commons/f/fe/Banorte_logo.svg';">
        <div>
          <div class="brand-title">BANORTE — Plataforma de Análisis de Proyectos</div>
          <div class="subtitle">Evaluación con IA • Costo–beneficio • Enfoque de política pública</div>
        </div>
      </div>
    </div>
    <div class="demo-banner"><span class="demo-badge">DEMO</span>Por fines demostrativos, el análisis debe realizarse <b>una única vez por sesión</b>. Si necesitas repetir, recarga la página.</div>
    <div class="grid">
      <div class="card">
        <h3>1) Carga tu proyecto (PDF)</h3>
        <div id="drop" class="upload">
          <div class="big">📄 Arrastra tu PDF aquí</div>
          <div class="muted">o haz clic para seleccionarlo (máx 16 MB)</div>
          <input id="file" type="file" accept=".pdf" class="hidden"/>
        </div>
        <div id="filePill" class="file-pill hidden">
          <div id="fileName">archivo.pdf</div>
          <button id="remove" style="background:none;border:1px solid var(--gris-borde);color:var(--gris);padding:6px 10px;border-radius:8px;cursor:pointer">Quitar</button>
        </div>
        <button id="analyze" class="btn-primary" disabled>Analizar con IA</button>
        <div id="alert" class="alert"></div>
        <div class="notice"><strong>Aviso demostrativo:</strong> sube un <b>documento de planeación de proyecto urbano</b> de <b>máximo 4 cuartillas</b> con: objetivo, alcance, presupuesto estimado, población beneficiaria, cronograma por hitos y riesgos principales.</div>
        <div class="section">
          <div class="title">¿Qué hace esta herramienta?</div>
          <div class="prose">
            <p>La plataforma emplea un <b>modelo de evaluación especializado</b>, entrenado con un <b>corpus curado de proyectos públicos</b> y <b>mejoras de prompting</b>, orquestado sobre la <b>API de Gemini</b>. Su propósito es <b>asistir a gobiernos de distinta escala</b> en la <b>formulación, priorización y financiamiento</b> de proyectos con mayor impacto social y solidez financiera.</p>
            <ul style="margin:6px 0 0;padding-left:18px">
              <li><b>Integra aprendizaje previo</b> de casos comparables para estimar métricas clave con rigor.</li>
              <li><b>Estandariza</b> la lectura del PDF y genera un <b>JSON</b> con indicadores accionables.</li>
              <li><b>Visualiza</b> el resultado con <b>donut de score</b>, <b>KPIs</b> y un <b>veredicto estratégico</b> alineado a criterios bancarios.</li>
            </ul>
          </div>
        </div>
      </div>
      <div class="card">
        <h3>2) Resultados</h3>
        <div class="score-card">
          <div style="justify-self:center"><canvas id="scoreDonut" width="220" height="220" style="max-width:240px;max-height:240px"></canvas></div>
          <div>
            <div class="chip">📊 Score costo–beneficio: <b id="scoreValue">—</b></div>
            <div class="scale">
              <div class="bar"><span id="seg1" style="width:0"></span></div>
              <div class="bar"><span id="seg2" style="width:0"></span></div>
              <div class="bar"><span id="seg3" style="width:0"></span></div>
              <div class="bar"><span id="seg4" style="width:0"></span></div>
              <div class="bar"><span id="seg5" style="width:0"></span></div>
            </div>
            <div class="kpis" style="margin-top:12px">
              <div class="kpi"><div class="label">Presupuesto</div><div id="kpiPres" class="value">—</div></div>
              <div class="kpi"><div class="label">Beneficiarios</div><div id="kpiBen" class="value">—</div></div>
              <div class="kpi"><div class="label">Eficiencia financiera</div><div id="kpiEfi" class="value">—</div></div>
            </div>
          </div>
        </div>
        <div class="section"><div class="title">📌 Nombre / Sector / Ubicación</div><div class="prose" id="nsu">—</div></div>
        <div class="section"><div class="title">📊 Análisis financiero</div><div class="prose" id="analisis">—</div></div>
        <div class="section"><div class="title">⚠️ Riesgos identificados</div><div class="prose" id="riesgos">—</div></div>
        <div class="section"><div class="title">💡 Recomendaciones</div><div class="prose" id="recomendaciones">—</div></div>
        <div class="veredicto">
          <div class="v-title">🏦 Veredicto Banorte</div>
          <div class="v-text" id="veredicto">—</div>
          <div class="v-just" id="justificacion">—</div>
        </div>
      </div>
    </div>
    <div class="footer">© 2025 Banorte — Demo de innovación (Hackatón)</div>
  </div>
  <div id="overlay" class="overlay">
    <div class="loader">
      <div class="spinner"></div>
      <div class="loader-title">Procesando archivo…</div>
      <div class="loader-sub">Analizando con IA de Banorte. Esto puede tomar 20–60 segundos.</div>
    </div>
  </div>
  <script>
    const drop=document.getElementById('drop'),input=document.getElementById('file'),pill=document.getElementById('filePill'),fname=document.getElementById('fileName'),removeBtn=document.getElementById('remove'),analyzeBtn=document.getElementById('analyze'),alertBox=document.getElementById('alert'),overlay=document.getElementById('overlay'),scoreCanvas=document.getElementById('scoreDonut'),scoreVal=document.getElementById('scoreValue'),kpiPres=document.getElementById('kpiPres'),kpiBen=document.getElementById('kpiBen'),kpiEfi=document.getElementById('kpiEfi'),nsu=document.getElementById('nsu'),anal=document.getElementById('analisis'),riesgos=document.getElementById('riesgos'),recs=document.getElementById('recomendaciones'),verd=document.getElementById('veredicto'),just=document.getElementById('justificacion');
    let selectedFile=null,donutChart=null,demoConsumed=false;
    function toast(msg,type='ok'){alertBox.textContent=msg;alertBox.className='alert '+(type==='ok'?'ok':'err');alertBox.style.display='block';clearTimeout(alertBox._t);alertBox._t=setTimeout(()=>alertBox.style.display='none',2600)}
    function showOverlay(show){overlay.style.display=show?'flex':'none'}
    function money(n){if(n==null||isNaN(n))return'—';return'$'+(Number(n)/1e6).toFixed(1)+'M'}
    function number(n){if(n==null||isNaN(n))return'—';return Number(n).toLocaleString('es-MX')}
    function percent(n){if(n==null||isNaN(n))return'—';return Math.round(Number(n))+'%'}
    function escapeHtml(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
    function niceList(text){if(!text)return'—';const lines=text.split(/\\n|(?=\\d+\\.)/g).map(s=>s.trim()).filter(Boolean);if(lines.length<=1)return escapeHtml(text);const items=lines.map(li=>'<li>'+escapeHtml(li.replace(/^\\d+\\.?\\s*/,''))+'</li>').join('');return'<ol>'+items+'</ol>'}
    function renderDonut(score){const ctx=scoreCanvas.getContext('2d');const pct=Math.max(0,Math.min(100,(Number(score)/10)*100));const color=score>=9?'#22c55e':score>=7?'#a3e635':score>=5?'#f59e0b':score>=3?'#fb923c':'#ef4444';if(donutChart)donutChart.destroy();donutChart=new Chart(ctx,{type:'doughnut',data:{datasets:[{data:[pct,100-pct],borderWidth:0,backgroundColor:[color,'#E7E9EC']}]},options:{cutout:'70%',responsive:true,plugins:{legend:{display:false},tooltip:{enabled:false}}},plugins:[{id:'centerText',afterDraw(c){const{ctx}=c;const center=c.getDatasetMeta(0).data[0];if(!center)return;ctx.save();ctx.font='800 30px Inter';ctx.fillStyle='#323E48';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(`${Math.round(pct)}%`,center.x,center.y);ctx.font='600 12px Inter';ctx.fillStyle='#5B6670';ctx.fillText('Score',center.x,center.y+22);ctx.restore()}}]});const segs=[seg1,seg2,seg3,seg4,seg5];const fills=[score>=2?(Math.min(score,2)/2):0,score>2?(Math.min(score-2,2)/2):0,score>4?(Math.min(score-4,2)/2):0,score>6?(Math.min(score-6,2)/2):0,score>8?(Math.min(score-8,2)/2):0];const colors=['#ef4444','#fb923c','#f59e0b','#a3e635','#22c55e'];segs.forEach((el,i)=>{el.style.width=(fills[i]*100)+'%';el.style.background=colors[i]})}
    drop.addEventListener('click',()=>input.click());drop.addEventListener('dragover',e=>{e.preventDefault();drop.style.borderColor='#EB0029'});drop.addEventListener('dragleave',()=>{drop.style.borderColor='var(--gris-borde)'});drop.addEventListener('drop',e=>{e.preventDefault();drop.style.borderColor='var(--gris-borde)';const f=e.dataTransfer.files&&e.dataTransfer.files[0];if(!f){toast('No se detectó archivo','err');return}setFile(f)});input.addEventListener('change',e=>{const f=e.target.files&&e.target.files[0];if(!f)return;setFile(f)});
    function setFile(f){if(demoConsumed){toast('Límite demo alcanzado. Recarga la página para reiniciar.','err');return}if(f.type!=='application/pdf'){toast('Solo se permite PDF','err');return}if(f.size>16*1024*1024){toast('Máximo 16 MB','err');return}selectedFile=f;fname.textContent='📄 '+f.name;pill.classList.remove('hidden');analyzeBtn.disabled=false;toast('Archivo listo','ok')}
    removeBtn.addEventListener('click',()=>{if(demoConsumed){toast('Límite demo alcanzado. Recarga la página para reiniciar.','err');return}selectedFile=null;pill.classList.add('hidden');analyzeBtn.disabled=true;toast('Archivo retirado','ok')});
    analyzeBtn.addEventListener('click',async()=>{if(!selectedFile){toast('Selecciona un PDF primero','err');return}if(demoConsumed){toast('Límite demo alcanzado. Recarga la página para reiniciar.','err');return}analyzeBtn.disabled=true;showOverlay(true);toast('Subiendo y procesando…','ok');const fd=new FormData();fd.append('file',selectedFile);try{const res=await fetch('/api/analyze',{method:'POST',body:fd});const data=await res.json();showOverlay(false);if(data.error){analyzeBtn.disabled=false;toast('Error: '+data.error,'err');return}demoConsumed=true;analyzeBtn.disabled=true;drop.style.pointerEvents='none';input.disabled=true;const score=Number(data.score_costo_beneficio||0)||0;const pres=Number(data.presupuesto_total_mxn||0)||0;const ben=Number(data.beneficiarios_estimados||0)||0;const efi=Number(data.eficiencia_financiera||0)||0;renderDonut(score);scoreVal.textContent=score.toFixed(1)+'/10';kpiPres.textContent=money(pres);kpiBen.textContent=number(ben);kpiEfi.textContent=percent(efi);const nom=data.nombre||'Proyecto sin nombre';const sec=data.sector||'—';const ubi=data.ubicacion||'—';nsu.innerHTML=`<b>${escapeHtml(nom)}</b> · <span style="color:var(--gris-sec)">${escapeHtml(sec)}</span> · <span style="color:var(--gris-sec)">${escapeHtml(ubi)}</span>`;anal.innerHTML=escapeHtml(data.analisis_financiero||'—').replace(/\\n\\n/g,'<br><br>');riesgos.innerHTML=niceList(data.riesgo_financiero);recs.innerHTML=niceList(data.recomendaciones);const baseJust=data.justificacion_veredicto||'Decisión sustentada en costo–beneficio, riesgos y comparables históricos.';const tech='aprovecha tecnologías probadas (sensórica/IoT, analítica geoespacial y tableros en tiempo real) para reducir incertidumbre operativa';const fin='estructura de financiamiento flexible (crédito sindicado, desembolsos por hitos y covenants de desempeño) que protege el capital y acelera el impacto social';let extra='';if(score>=9)extra=`Prioridad estratégica: ${tech}; ${fin}.`;else if(score>=7)extra=`Viable con supervisión: ${tech} y ${fin} con gatillos de mitigación.`;else if(score>=5)extra=`Requiere reestructura: foco en ${tech} y rediseñar ${fin} para mitigar capex/opex.`;else extra=`No recomendable en esta versión: incluso con ${tech}, los riesgos exceden umbrales; ${fin} no compensa la exposición actual.`;verd.textContent=data.veredicto_banorte||'—';just.textContent=`${extra} ${baseJust}`;console.log("DEBUG payload:",data._debug||{});toast('✅ Análisis completado (demo 1/1)','ok')}catch(e){analyzeBtn.disabled=false;showOverlay(false);toast('Error de conexión','err');console.error(e)}});
  </script>
</body>
</html>
"""


# ================== RUTAS FLASK ==================
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Servidor activo"})


@app.route("/api/analyze", methods=["POST"])
def analyze_endpoint():
    """Endpoint principal: recibe PDF, extrae texto, analiza con IA"""
    if "file" not in request.files:
        return jsonify({"error": "No se recibió archivo"}), 400
    
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "Archivo vacío"}), 400
    
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Solo se aceptan archivos PDF"}), 400
    
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        log.info("📄 Archivo recibido: %s", filename)
        
        text = analizador.extract_text(filepath)
        if not text:
            return jsonify({"error": "No se pudo extraer texto del PDF"}), 400
        
        log.info("📝 Texto extraído: %d caracteres", len(text))
        
        result = analizador.analyze(text)
        
        try:
            os.remove(filepath)
        except Exception as e:
            log.warning("No se pudo eliminar archivo temporal: %s", e)
        
        if "error" in result:
            return jsonify(result), 500
        
        return jsonify(result)
    
    except Exception as e:
        log.exception("❌ Error en /api/analyze: %s", e)
        return jsonify({"error": f"Error interno: {str(e)}"}), 500


# ================== MAIN (DEBUG MODE) ==================
if __name__ == "__main__":
    print("=" * 70)
    print("🏛️  BANORTE - SISTEMA DE ANÁLISIS GUBERNAMENTAL (DEBUG MODE)")
    print("🌐  URL: http://localhost:5000")
    print(f"🧠  Modelo activo: {analizador.model_name}")
    print("ℹ️   Endpoints: /  |  /api/analyze (POST)  |  /health")
    print("=" * 70)
    app.run(debug=True, host="0.0.0.0", port=5000)
