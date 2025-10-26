# main.py
import os
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Importar módulos propios
from config import DOCS_DIR, SAMPLE_DIR, DEBUG_DIR, OUTPUT_JSON, OUTPUT_CSV
from downloader import download_batch_simulated, check_and_download_new_files
from extractor import extract_text
from analyzer import init_gemini_model, analyze_with_gemini
from cleaner import normalize_record, to_number_simple
from storage import (
    load_procesados, 
    save_procesados, 
    append_record_json, 
    append_record_csv
)
from snowflake_uploader import get_snowflake_connection, upload_record_to_snowflake

load_dotenv()

# ============= CONFIGURACIÓN =============
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DRY_RUN = False
UPLOAD_TO_SNOWFLAKE = os.getenv("UPLOAD_TO_SNOWFLAKE", "false").lower() == "true"
MONITORING_INTERVAL = 60  # ✅ Cambiado a 60 segundos (1 minuto)
CONTINUOUS_MODE = os.getenv("CONTINUOUS_MODE", "true").lower() == "true"  # ✅ Default: true


# ============= VALIDACIÓN =============
def validate_record(record: dict) -> dict:
    """Valida que el registro tenga campos mínimos y coherencia."""
    issues = []
    
    if not record.get("nombre"):
        issues.append("nombre_missing")
    if not record.get("sector"):
        issues.append("sector_missing")
    if not record.get("doc_fuente"):
        issues.append("doc_fuente_missing")
    
    valid_sectors = [
        "Agua", "Energía", "Transporte", "Infraestructura", 
        "Salud", "Educación", "Medio Ambiente", "Desarrollo Social"
    ]
    if record.get("sector") and record["sector"] not in valid_sectors:
        issues.append(f"sector_invalid:{record['sector']}")
    
    anio_inicio = record.get("anio_inicio")
    anio_fin = record.get("anio_fin")
    
    if anio_inicio and (anio_inicio < 1900 or anio_inicio > 2100):
        issues.append(f"anio_inicio_invalid:{anio_inicio}")
    
    if anio_fin and (anio_fin < 1900 or anio_fin > 2100):
        issues.append(f"anio_fin_invalid:{anio_fin}")
    
    if anio_inicio and anio_fin and anio_inicio > anio_fin:
        issues.append("anio_inconsistency")
    
    presupuesto = record.get("presupuesto_total_mxn")
    if presupuesto is not None:
        try:
            p = float(presupuesto)
            if p < 0:
                issues.append("presupuesto_negative")
            if p > 1_000_000_000_000:
                issues.append("presupuesto_suspicious")
        except (ValueError, TypeError):
            issues.append("presupuesto_invalid_type")
    
    score = record.get("score_costo_beneficio")
    if score is not None:
        try:
            s = float(score)
            if s < 0 or s > 10:
                issues.append("score_out_of_range")
        except (ValueError, TypeError):
            issues.append("score_invalid_type")
    
    record["_validation"] = ",".join(issues) if issues else "OK"
    record["_validated_at"] = datetime.now().isoformat()
    
    return record


# ============= FALLBACK HEURÍSTICO =============
def fallback_heuristic_extraction(text: str, file_path: Path) -> dict:
    """Extracción heurística simple cuando Gemini falla."""
    import re
    
    record = {
        "nombre": None,
        "sector": None,
        "dependencia": None,
        "ubicacion": None,
        "anio_inicio": None,
        "anio_fin": None,
        "doc_fuente": file_path.name,
        "fecha_carga": datetime.now().strftime('%Y-%m-%d'),
        "presupuesto_total_mxn": None,
        "beneficiarios_estimados": None,
        "_extraction_method": "fallback_heuristic"
    }
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        record["nombre"] = lines[0][:200]
    
    years = re.findall(r'\b(20\d{2})\b', text)
    if years:
        years = sorted([int(y) for y in years])
        record["anio_inicio"] = years[0]
        if len(years) > 1:
            record["anio_fin"] = years[-1]
    
    money_patterns = [
        r'(\d+(?:\.\d+)?)\s*millones?\s*(?:de\s*)?pesos',
        r'(\d+(?:\.\d+)?)\s*mil\s*(?:millones?\s*)?pesos',
        r'\$\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:millones?|mil)?'
    ]
    
    for pattern in money_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = match.group(1).replace(',', '')
            record["presupuesto_total_mxn"] = to_number_simple(amount)
            break
    
    sector_keywords = {
        "Agua": ["agua", "hidráulico", "presa", "acueducto"],
        "Energía": ["energía", "electricidad", "solar", "eólico"],
        "Transporte": ["carretera", "autopista", "transporte", "vial"],
        "Salud": ["hospital", "salud", "clínica", "médico"],
        "Educación": ["escuela", "educación", "universidad", "estudiante"]
    }
    
    text_lower = text.lower()
    for sector, keywords in sector_keywords.items():
        if any(kw in text_lower for kw in keywords):
            record["sector"] = sector
            break
    
    return record


# ============= PROCESAMIENTO DE UN DOCUMENTO =============
def process_single_document(file_path: Path, model, procesados: dict, snowflake_conn=None) -> dict:
    """Procesa un único documento. Retorna el registro extraído (o None si falla)."""
    file_key = file_path.name
    
    # Verificar si ya fue procesado
    if file_key in procesados:
        print(f"  ⏭️  Ya procesado: {file_key}")
        return None
    
    print(f"\n📄 Procesando: {file_key}")
    
    # 1. Extraer texto
    text = extract_text(file_path)
    if not text or len(text.strip()) < 100:
        print(f"  ❌ Texto insuficiente ({len(text)} chars)")
        procesados[file_key] = {
            "status": "failed",
            "reason": "insufficient_text",
            "timestamp": datetime.now().isoformat()
        }
        return None
    
    print(f"  ✓ Texto extraído: {len(text)} caracteres")
    
    # 2. Analizar con Gemini
    result = analyze_with_gemini(model, text, file_path)
    
    # 3. Manejar errores de LLM
    if result is None or "_error" in result:
        error_type = result.get("_error", "unknown") if result else "model_unavailable"
        print(f"  ⚠️  Gemini falló ({error_type}), usando fallback heurístico...")
        
        debug_file = DEBUG_DIR / f"{file_key}.error.json"
        debug_file.write_text(
            json.dumps(result or {"error": "model_none"}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        result = fallback_heuristic_extraction(text, file_path)
    
    # 4. Normalizar y validar
    result = normalize_record(result)
    result = validate_record(result)
    
    # 5. Guardar en debug
    debug_file = DEBUG_DIR / f"{file_key}.json"
    debug_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    # 6. Subir a Snowflake
    if snowflake_conn and result.get("_validation") == "OK":
        success, info = upload_record_to_snowflake(snowflake_conn, result)
        if success:
            print(f"  ☁️  Snowflake ✓ (ID: {info})")
        else:
            print(f"  ☁️  Snowflake ✗ ({info})")
    
    # 7. Marcar como procesado
    procesados[file_key] = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "validation": result.get("_validation", "N/A")
    }
    
    validation_status = result.get("_validation", "N/A")
    print(f"  ✓ Completado | Validación: {validation_status}")
    
    return result


# ============= CICLO DE MONITOREO CONTINUO =============
def continuous_monitoring_loop(model, snowflake_conn=None):
    """
    Ciclo infinito que monitorea sample_sources/ cada MONITORING_INTERVAL segundos.
    """
    print("\n" + "=" * 70)
    print("👁️  MODO MONITOREO CONTINUO ACTIVADO")
    print("=" * 70)
    print(f"⏱️  Intervalo: {MONITORING_INTERVAL} segundos")
    print(f"📂 Monitoreando: {SAMPLE_DIR.absolute()}")
    print("💡 Pon nuevos PDFs en sample_sources/ y se procesarán automáticamente")
    print("🛑 Presiona Ctrl+C para detener\n")
    
    procesados = load_procesados()
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{timestamp}] 🔄 Ciclo #{cycle_count} - Verificando nuevos archivos...")
            
            # Verificar si hay nuevos archivos
            new_files = check_and_download_new_files()
            
            if new_files:
                print(f"✨ Procesando {len(new_files)} archivo(s) nuevo(s)...\n")
                
                for file_path in new_files:
                    try:
                        record = process_single_document(file_path, model, procesados, snowflake_conn)
                        
                        if record and not DRY_RUN:
                            append_record_json(record)
                            append_record_csv(record)
                            save_procesados(procesados)
                            print(f"  💾 Datos guardados")
                    
                    except Exception as e:
                        print(f"  ❌ Error procesando {file_path.name}: {e}")
                        procesados[file_path.name] = {
                            "status": "error",
                            "reason": str(e),
                            "timestamp": datetime.now().isoformat()
                        }
                
                save_procesados(procesados)
                print(f"\n✅ Lote completado")
            
            else:
                print(f"  💤 Sin archivos nuevos")
            
            print(f"  ⏳ Próxima verificación en {MONITORING_INTERVAL}s...")
            time.sleep(MONITORING_INTERVAL)
    
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoreo detenido por el usuario")


# ============= MAIN =============
def main():
    print("=" * 70)
    print("🚀 SISTEMA DE EXTRACCIÓN AUTOMATIZADA - BANORTE AI")
    print("=" * 70)
    
    # 1. Verificar API Key
    if not GEMINI_API_KEY:
        print("❌ ERROR: GEMINI_API_KEY no encontrada en .env")
        sys.exit(1)
    
    print(f"✓ API Key configurada")
    
    # 2. Inicializar modelo
    print("🤖 Inicializando Gemini...")
    model = init_gemini_model(GEMINI_API_KEY)
    if model is None:
        print("⚠️  Advertencia: google.generativeai no disponible. Solo fallback heurístico.")
    else:
        print("✓ Gemini inicializado")
    
    # 3. Conectar a Snowflake
    snowflake_conn = None
    if UPLOAD_TO_SNOWFLAKE:
        print("☁️  Conectando a Snowflake...")
        snowflake_conn = get_snowflake_connection()
        if snowflake_conn:
            print("✓ Snowflake conectado")
        else:
            print("⚠️  Snowflake no disponible - solo se guardará en JSON/CSV")
    
    # 4. Procesar archivos existentes en manifest
    print("\n📥 Verificando archivos existentes en manifest...")
    downloaded_files = download_batch_simulated()
    
    if downloaded_files:
        print(f"📋 Procesando {len(downloaded_files)} archivo(s) existente(s)...")
        procesados = load_procesados()
        
        for file_path in downloaded_files:
            try:
                record = process_single_document(file_path, model, procesados, snowflake_conn)
                if record and not DRY_RUN:
                    append_record_json(record)
                    append_record_csv(record)
                    save_procesados(procesados)
            except Exception as e:
                print(f"❌ Error: {e}")
    
    # 5. Iniciar monitoreo continuo
    if CONTINUOUS_MODE:
        continuous_monitoring_loop(model, snowflake_conn)
    else:
        print("\n✅ Procesamiento completado")
        print("💡 Para modo continuo, configura: CONTINUOUS_MODE=true en .env")
    
    # Cerrar conexión Snowflake
    if snowflake_conn:
        snowflake_conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)