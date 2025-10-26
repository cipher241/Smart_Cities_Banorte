import os
import time
import json
import glob
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()
# ============= CONFIGURACIÓN =============
MODEL = "gemini-2.0-flash-exp"
INTERVAL = 30  # Cambiar a 5 para demo rápida
OUTPUT_DIR = "prompt_iterations"
MAX_PROMPT_CHARS = 2000
MAX_ITERATIONS = 20

# Archivos
DATASET_FILE = "training_vectors.json"
TRIGGER_FILE = "retrain_trigger.flag"
STATE_FILE = "training_state.json"
BEST_PROMPT_FILE = "best_analysis_prompt.txt"  # ⭐ ESTE ES EL OUTPUT FINAL

# ============= ANCLA INMUTABLE =============
PROMPT_ANCHOR = """
REGLAS FUNDAMENTALES (INMUTABLES):
1. OBJETIVO: Analizar PDFs de proyectos de infraestructura mexicana
2. OUTPUT: JSON estructurado con análisis completo
3. MÉTRICAS: score_costo_beneficio (0-10), eficiencia_financiera (%), beneficiarios_estimados
4. ENFOQUE: Viabilidad económica, impacto social, sostenibilidad
5. FORMATO: JSON válido siempre
"""

# ============= META-PROMPT =============
META_PROMPT = """Eres experto en ingeniería de prompts para análisis financiero.

CONTEXTO:
El prompt que optimizas será usado por una API que recibe PDFs de proyectos.
Debe extraer datos financieros, calcular score costo-beneficio y generar análisis.

CRITERIOS DE MEJORA:
1. Precisión en extracción de datos numéricos
2. Claridad en criterios de scoring
3. Manejo de PDFs difusos o incompletos
4. Output JSON consistente

RESTRICCIONES:
- Máximo 2000 caracteres
- Mantener "REGLAS FUNDAMENTALES" intacta

Responde SOLO en JSON:
{
  "prompt_mejorado": "...",
  "cambios_realizados": ["cambio1", "cambio2"],
  "razonamiento": "...",
  "metricas_mejora": {
    "precision_extraccion": 0-10,
    "claridad_instrucciones": 0-10,
    "robustez_formato": 0-10
  }
}"""


class PromptTrainer:
    """Entrenador de prompts - SOLO genera best_analysis_prompt.txt"""
    
    def __init__(self):
        self.state = self.load_state()
        self.client = None
        
    def load_state(self):
        if Path(STATE_FILE).exists():
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
        return {
            "current_iteration": 0,
            "best_iteration": 0,
            "best_score": 0,
            "retrains_completed": 0
        }
    
    def save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def load_dataset(self):
        """Carga dataset de Snowflake"""
        if not Path(DATASET_FILE).exists():
            print(f"⚠️ Dataset no encontrado: {DATASET_FILE}")
            print(f"🔄 Ejecutando ExtraerCrearDS.py automáticamente...")
            
            try:
                import subprocess
                result = subprocess.run(
                    ["python", "ExtraerCrearDS.py", "--extract-once"],  # ⭐ AGREGAR FLAG
                    capture_output=True, 
                    text=True,
                    timeout=120,
                    encoding='utf-8'  # ⭐ AGREGAR ENCODING
                )
                
                if result.returncode == 0:
                    print("✅ Dataset extraído exitosamente")
                    if not Path(DATASET_FILE).exists():
                        print("❌ ExtraerCrearDS.py no generó el archivo esperado")
                        return None
                else:
                    print(f"❌ Error ejecutando ExtraerCrearDS.py:")
                    print(result.stderr)
                    return None
                    
            except subprocess.TimeoutExpired:
                print("❌ ExtraerCrearDS.py tardó demasiado (>2 min)")
                return None
            except Exception as e:
                print(f"❌ Error ejecutando ExtraerCrearDS.py: {e}")
                return None
        
        with open(DATASET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not data or len(data) < 2:
            return None
        
        print(f"✅ Dataset cargado: {len(data)-1} proyectos")
        return data
    
    def generate_context(self, dataset):
        """Genera contexto del dataset"""
        if not dataset or len(dataset) < 2:
            return "Dataset vacío"
        
        headers = dataset[0]
        rows = dataset[1:]
        
        sectores = set()
        presupuestos = []
        
        try:
            idx_sector = headers.index('SECTOR')
            idx_presupuesto = headers.index('PRESUPUESTO_TOTAL')
            
            for row in rows:
                if row[idx_sector]:
                    sectores.add(str(row[idx_sector]))
                if row[idx_presupuesto]:
                    try:
                        presupuestos.append(float(row[idx_presupuesto]))
                    except:
                        pass
        except:
            return f"Dataset: {len(rows)} proyectos"
        
        if not presupuestos:
            return f"Dataset: {len(rows)} proyectos"
        
        return f"""Dataset real (Snowflake): {len(rows)} proyectos
Sectores: {', '.join(list(sectores)[:5])}
Presupuesto promedio: ${sum(presupuestos)/len(presupuestos):,.0f} MXN
Rango: ${min(presupuestos):,.0f} - ${max(presupuestos):,.0f}"""
    
    def validate_size(self, prompt):
        chars = len(prompt)
        return {
            "valid": chars <= MAX_PROMPT_CHARS,
            "chars": chars,
            "percentage": (chars / MAX_PROMPT_CHARS) * 100
        }
    
    def ensure_anchor(self, prompt):
        if "REGLAS FUNDAMENTALES" not in prompt:
            return PROMPT_ANCHOR + "\n\n" + prompt
        return prompt
    
    def improve_prompt(self, context, current_prompt, iteration, condense=False):
        """Llama a Gemini para mejorar el prompt"""
        try:
            validation = self.validate_size(current_prompt)
            
            if condense:
                instruction = f"""CONDENSACIÓN FORZADA

Prompt actual ({validation['chars']}/2000 chars):
{current_prompt}

Reduce a 2000 caracteres manteniendo:
- "REGLAS FUNDAMENTALES"
- Capacidad de análisis
- Output JSON"""
            else:
                instruction = f"""{context}

Prompt actual (Iteración {iteration}):
{validation['chars']}/2000 chars ({validation['percentage']:.1f}%)

{current_prompt}

Mejora para análisis de PDFs:
- Precisión en extracción financiera
- Criterios claros de scoring
- Manejo de datos incompletos
- NO exceder 2000 caracteres"""
            
            response = self.client.generate_content(instruction)
            return response.text
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def parse_json(self, raw):
        try:
            cleaned = raw.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                parts = cleaned.split("```")
                if len(parts) >= 3:
                    cleaned = parts[1]
            return json.loads(cleaned.strip())
        except:
            return None
    
    def calc_avg(self, metrics):
        try:
            return sum([
                float(metrics.get('precision_extraccion', 0)),
                float(metrics.get('claridad_instrucciones', 0)),
                float(metrics.get('robustez_formato', 0))
            ]) / 3
        except:
            return 0
    
    def save_best(self, prompt, iteration, score):
        """⭐ GUARDA EL MEJOR PROMPT - ESTE ES EL OUTPUT FINAL"""
        with open(BEST_PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("🏆 MEJOR PROMPT DE ANÁLISIS (USAR EN API)\n")
            f.write("=" * 80 + "\n")
            f.write(f"Iteración: {iteration}\n")
            f.write(f"Score: {score:.2f}/10\n")
            f.write(f"Generado: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")
            f.write(prompt)
        
        print(f"🏆 Mejor prompt guardado (score: {score:.2f})")
        print(f"📁 Archivo: {BEST_PROMPT_FILE}")
    
    def save_iteration(self, iteration, raw, parsed, prompt, validation):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"iteration_{iteration:04d}_{timestamp}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"ITERACIÓN {iteration}\n")
            f.write(f"Tamaño: {validation['chars']}/2000\n")
            f.write(f"Estado: {'✅' if validation['valid'] else '❌'}\n\n")
            
            if parsed:
                f.write("PROMPT:\n")
                f.write(prompt + "\n\n")
                f.write("CAMBIOS:\n")
                for c in parsed.get("cambios_realizados", []):
                    f.write(f"- {c}\n")
                
                if "metricas_mejora" in parsed:
                    m = parsed["metricas_mejora"]
                    f.write(f"\nMÉTRICAS:\n")
                    f.write(f"Precisión: {m.get('precision_extraccion')}/10\n")
                    f.write(f"Claridad: {m.get('claridad_instrucciones')}/10\n")
                    f.write(f"Robustez: {m.get('robustez_formato')}/10\n")
            else:
                f.write(f"ERROR PARSEANDO\n{raw[:500]}")
        
        return filepath
    def get_latest_prompt(self):
        files = glob.glob(os.path.join(OUTPUT_DIR, "iteration_*.txt"))
        if not files:
            return None
        
        latest = max(files, key=os.path.getmtime)
        
        try:
            with open(latest, "r") as f:
                content = f.read()
            
            if "PROMPT:" in content:
                parts = content.split("PROMPT:")
                if len(parts) > 1:
                    return parts[1].split("CAMBIOS:")[0].strip()
        except:
            pass
        
        return None
    
    def train(self, initial_prompt, max_iter=MAX_ITERATIONS):
        """🔥 ENTRENAMIENTO PRINCIPAL - GENERA MEJOR PROMPT 🔥"""
        
        print("\n" + "=" * 80)
        print("🚀 ENTRENAMIENTO DE PROMPT DE ANÁLISIS")
        print("=" * 80)
        
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Inicializar Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ GEMINI_API_KEY no encontrada")
            return False
        
        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(MODEL, system_instruction=META_PROMPT)
        print("✅ Gemini inicializado")
        
        # Cargar dataset
        dataset = self.load_dataset()
        if not dataset:
            return False
        
        context = self.generate_context(dataset)
        print(f"\n{context}\n")
        
        # Punto de inicio
        prev = self.get_latest_prompt()
        
        if prev:
            current = prev
            iteration = self.state['current_iteration'] + 1
            print(f"🔄 Continuando desde iteración {iteration}")
        else:
            current = self.ensure_anchor(initial_prompt)
            iteration = 1
            
            validation = self.validate_size(current)
            self.save_iteration(0, "BASELINE", None, current, validation)
            print("💾 Baseline guardado")
        
        print(f"\n🎯 Meta: {max_iter} iteraciones")
        print(f"⏱️ Intervalo: {INTERVAL}s\n")
        print("=" * 80)
        
        try:
            while iteration <= max_iter:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{ts}] 🔄 ITERACIÓN {iteration}/{max_iter}")
                print("-" * 80)
                
                current = self.ensure_anchor(current)
                validation = self.validate_size(current)
                print(f"📏 {validation['chars']}/2000 chars")
                
                print("🤖 Optimizando...")
                improved = self.improve_prompt(context, current, iteration)
                
                if not improved:
                    print("⚠️ Sin respuesta")
                    time.sleep(5)
                    continue
                
                parsed = self.parse_json(improved)
                
                if not parsed:
                    print("❌ Error parseando")
                    self.save_iteration(iteration, improved, None, current, validation)
                    iteration += 1
                    continue
                
                new_prompt = parsed.get("prompt_mejorado", current)
                new_prompt = self.ensure_anchor(new_prompt)
                new_validation = self.validate_size(new_prompt)
                
                if new_validation['valid']:
                    current = new_prompt
                    print(f"✅ Optimizado ({new_validation['chars']} chars)")
                    
                    if "metricas_mejora" in parsed:
                        m = parsed["metricas_mejora"]
                        avg = self.calc_avg(m)
                        
                        print(f"📊 Precisión: {m.get('precision_extraccion')}/10")
                        print(f"📊 Claridad: {m.get('claridad_instrucciones')}/10")
                        print(f"📊 Robustez: {m.get('robustez_formato')}/10")
                        print(f"⭐ PROMEDIO: {avg:.2f}/10")
                        
                        if avg > self.state.get('best_score', 0):
                            self.state['best_score'] = avg
                            self.state['best_iteration'] = iteration
                            self.save_best(current, iteration, avg)
                else:
                    print(f"⚠️ Excede: {new_validation['chars']} chars")
                    print("🔄 Condensando...")
                    
                    time.sleep(2)
                    retry = self.improve_prompt(context, new_prompt, iteration, True)
                    
                    if retry:
                        retry_parsed = self.parse_json(retry)
                        if retry_parsed:
                            retry_prompt = retry_parsed.get("prompt_mejorado", current)
                            retry_prompt = self.ensure_anchor(retry_prompt)
                            retry_validation = self.validate_size(retry_prompt)
                            
                            if retry_validation['valid']:
                                current = retry_prompt
                                parsed = retry_parsed
                                new_validation = retry_validation
                                print(f"✅ Condensado: {retry_validation['chars']} chars")
                
                self.save_iteration(iteration, improved, parsed, current, new_validation)
                
                self.state['current_iteration'] = iteration
                self.save_state()
                
                iteration += 1
                
                if iteration <= max_iter:
                    print(f"⏳ Esperando {INTERVAL}s...")
                    time.sleep(INTERVAL)
            
            print("\n" + "=" * 80)
            print("🎉 ENTRENAMIENTO COMPLETADO")
            print("=" * 80)
            print(f"✅ Iteraciones: {max_iter}")
            print(f"🏆 Mejor iteración: #{self.state.get('best_iteration')}")
            print(f"📊 Mejor score: {self.state.get('best_score', 0):.2f}/10")
            print(f"\n⭐ PROMPT FINAL: {BEST_PROMPT_FILE}")
            print(f"📁 Iteraciones: {OUTPUT_DIR}/")
            
            self.state['retrains_completed'] += 1
            self.save_state()
            
            return True
            
        except KeyboardInterrupt:
            print("\n\n🛑 Interrumpido")
            self.save_state()
            return False
    
    def continuous_mode(self, initial_prompt, check_interval=60):
        """Modo continuo: espera triggers y re-entrena"""
        
        print("\n" + "=" * 80)
        print("🎯 MODO CONTINUO")
        print("=" * 80)
        print(f"⏱️ Intervalo: {check_interval}s")
        print(f"📂 Trigger: {TRIGGER_FILE}\n")
        
        cycle = 0
        
        try:
            while True:
                cycle += 1
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{ts}] 🔍 Ciclo #{cycle}")
                
                if Path(TRIGGER_FILE).exists():
                    try:
                        with open(TRIGGER_FILE, "r") as f:
                            trigger = json.load(f)
                        os.remove(TRIGGER_FILE)
                        
                        print("🚨 TRIGGER DETECTADO!")
                        print(f"📊 Nuevos: {trigger.get('new_records')}")
                        print("🔄 Re-entrenando...")
                        
                        self.train(initial_prompt, MAX_ITERATIONS)
                        
                        print("\n✅ Re-entrenamiento completado")
                        print("🔄 Volviendo a monitoreo...")
                    except:
                        pass
                else:
                    print("   💤 Sin triggers")
                
                print(f"   ⏳ Siguiente en {check_interval}s...")
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Detenido")


# ============= MAIN =============
def main():
    """
    ⭐ ÚNICO PROPÓSITO: Generar best_analysis_prompt.txt
    Ese archivo será leído por api_produccion.py
    """
    
    # Prompt inicial base (será optimizado)
    INITIAL_PROMPT = """
Analiza este PDF de proyecto de infraestructura:

{DOCUMENTO}

Extrae:
1. Datos básicos (nombre, sector, ubicación, años)
2. Financieros (presupuesto, costos)
3. Impacto (beneficiarios)
4. Score costo-beneficio (0-10)

Formato JSON:
{
  "nombre": "string",
  "sector": "string",
  "presupuesto_total_mxn": float,
  "beneficiarios_estimados": float,
  "score_costo_beneficio": float,
  "analisis_financiero": "string"
}
"""
    
    trainer = PromptTrainer()
    
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        # Modo continuo (espera triggers)
        trainer.continuous_mode(INITIAL_PROMPT, check_interval=60)
    else:
        # Modo single-run - ✅ CORRECCIÓN AQUÍ
        trainer.train(INITIAL_PROMPT, max_iter=MAX_ITERATIONS)


if __name__ == "__main__":
    main()
