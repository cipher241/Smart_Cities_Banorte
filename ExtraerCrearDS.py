import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
import snowflake.connector
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

# ============= CONFIGURACIÓN =============
SNOWFLAKE_CONFIG = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT", "XBHKLTH-FP24352"),
    "user": os.getenv("SNOWFLAKE_USER", "GUYO"),
    "password": os.getenv("SNOWFLAKE_PASSWORD", "VtXtg4miN9h558H"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    "database": os.getenv("SNOWFLAKE_DATABASE", "BANORTE_AI_ANALYTICS"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
    "role": os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")
}

# Archivos de estado
STATE_FILE = "monitor_state.json"
DATASET_FILE = "training_vectors.json"
DATASET_DICT = "training_dataset.json"
TRIGGER_FILE = "retrain_trigger.flag"

# Configuración de monitoreo
CHECK_INTERVAL = 30  # segundos entre verificaciones
MIN_RETRAIN_RECORDS = 1  # mínimo de registros nuevos para re-entrenar


class SnowflakeMonitor:
    """Monitor reactivo de cambios en Snowflake"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.state = self.load_state()
        self.last_check = None
        
    def load_state(self):
        """Carga el estado del último monitoreo"""
        if Path(STATE_FILE).exists():
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
        
        return {
            "last_id_proyecto": 0,
            "total_records": 0,
            "last_update": None,
            "retrains_triggered": 0
        }
    
    def save_state(self):
        """Guarda el estado actual"""
        self.state["last_update"] = datetime.now().isoformat()
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)
    
    def connect(self):
        """Conecta a Snowflake"""
        try:
            self.conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
            self.cursor = self.conn.cursor()
            
            self.cursor.execute(f"USE WAREHOUSE {SNOWFLAKE_CONFIG['warehouse']}")
            self.cursor.execute(f"USE DATABASE {SNOWFLAKE_CONFIG['database']}")
            self.cursor.execute(f"USE SCHEMA {SNOWFLAKE_CONFIG['schema']}")
            
            return True
        except Exception as e:
            print(f"❌ Error conectando: {e}")
            return False
    
    def disconnect(self):
        """Cierra conexión"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
    
    def check_new_records(self):
        """
        Verifica si hay nuevos registros en PROYECTOS.
        Retorna: (hay_nuevos, count_nuevos, nuevos_ids)
        """
        try:
            # Obtener el ID máximo actual
            self.cursor.execute("SELECT MAX(id_proyecto) FROM PROYECTOS")
            result = self.cursor.fetchone()
            max_id = result[0] if result and result[0] else 0
            
            last_id = self.state["last_id_proyecto"]
            
            if max_id > last_id:
                # Hay nuevos registros
                nuevos = max_id - last_id
                
                # Obtener los IDs nuevos
                self.cursor.execute(f"""
                    SELECT id_proyecto, nombre, sector 
                    FROM PROYECTOS 
                    WHERE id_proyecto > {last_id}
                    ORDER BY id_proyecto
                """)
                nuevos_registros = self.cursor.fetchall()
                
                return True, nuevos, nuevos_registros
            
            return False, 0, []
            
        except Exception as e:
            print(f"❌ Error verificando registros: {e}")
            return False, 0, []
    
    def extract_full_dataset(self):
        """Extrae el dataset completo actualizado"""
        try:
            query = """
                SELECT 
                    p.id_proyecto,
                    p.nombre,
                    p.sector,
                    p.dependencia,
                    p.ubicacion,
                    p.anio_inicio,
                    p.anio_fin,
                    p.doc_fuente,
                    p.fecha_carga,
                    f.presupuesto_total,
                    f.costo_operativo_mxn,
                    f.costo_mantenimiento_mxn,
                    f.costo_beneficio_estimado_mxn,
                    f.eficiencia_financiera,
                    f.riesgo_financiero,
                    i.beneficiarios_estimados,
                    i.impacto_principal,
                    i.indicador_principal,
                    i.avance_fisico,
                    i.kpi,
                    e.score_costo_beneficio,
                    e.analisis_financiero,
                    e.recomendaciones,
                    e.comparativa
                FROM PROYECTOS p
                LEFT JOIN FINANZAS f ON p.id_proyecto = f.id_proyecto
                LEFT JOIN IMPACTO_SOCIAL i ON p.id_proyecto = i.id_proyecto
                LEFT JOIN EVALUACIONES e ON p.id_proyecto = e.id_proyecto
                ORDER BY p.id_proyecto
            """
            
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            columns = [desc[0] for desc in self.cursor.description]
            
            # Formato vectores
            data_vectores = [columns] + [list(row) for row in rows]
            
            # Formato diccionarios
            data_dict = [dict(zip(columns, row)) for row in rows]
            
            return data_vectores, data_dict
            
        except Exception as e:
            print(f"❌ Error extrayendo dataset: {e}")
            return None, None
    
    def update_dataset_files(self, data_vectores, data_dict):
        """Actualiza los archivos de dataset"""
        try:
            # Guardar vectores
            with open(DATASET_FILE, "w", encoding="utf-8") as f:
                json.dump(data_vectores, f, ensure_ascii=False, indent=2, default=str)
            
            # Guardar diccionarios
            with open(DATASET_DICT, "w", encoding="utf-8") as f:
                json.dump(data_dict, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"💾 Dataset actualizado: {len(data_vectores)-1} proyectos")
            return True
            
        except Exception as e:
            print(f"❌ Error guardando dataset: {e}")
            return False
    
    def trigger_retraining(self, nuevos_count):
        """Crea un flag para disparar re-entrenamiento"""
        try:
            trigger_data = {
                "triggered_at": datetime.now().isoformat(),
                "new_records": nuevos_count,
                "total_records": self.state["total_records"],
                "reason": "new_data_detected"
            }
            
            with open(TRIGGER_FILE, "w") as f:
                json.dump(trigger_data, f, indent=2)
            
            self.state["retrains_triggered"] += 1
            print(f"🚀 Re-entrenamiento disparado (trigger #{self.state['retrains_triggered']})")
            return True
            
        except Exception as e:
            print(f"❌ Error creando trigger: {e}")
            return False
    
    def monitor_loop(self):
        """Ciclo principal de monitoreo"""
        print("=" * 80)
        print("👁️  MONITOR REACTIVO DE SNOWFLAKE")
        print("=" * 80)
        print(f"📊 Estado inicial:")
        print(f"   • Último ID procesado: {self.state['last_id_proyecto']}")
        print(f"   • Total de registros: {self.state['total_records']}")
        print(f"   • Re-entrenamientos: {self.state['retrains_triggered']}")
        print(f"\n⏱️  Intervalo de verificación: {CHECK_INTERVAL}s")
        print(f"🔄 Mínimo para re-entrenar: {MIN_RETRAIN_RECORDS} registro(s)")
        print("\n💡 Presiona Ctrl+C para detener\n")
        print("=" * 80)
        
        cycle = 0
        
        try:
            while True:
                cycle += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] 🔍 Ciclo #{cycle} - Verificando nuevos datos...")
                
                # Conectar
                if not self.connect():
                    print("⚠️  Sin conexión, reintentando en 10s...")
                    time.sleep(10)
                    continue
                
                # Verificar nuevos registros
                hay_nuevos, count_nuevos, registros = self.check_new_records()
                
                if hay_nuevos:
                    print(f"\n🆕 ¡NUEVOS REGISTROS DETECTADOS!")
                    print(f"   • Cantidad: {count_nuevos}")
                    print(f"   • Rango de IDs: {self.state['last_id_proyecto']+1} - {self.state['last_id_proyecto']+count_nuevos}")
                    print(f"\n📋 Proyectos nuevos:")
                    
                    for id_proy, nombre, sector in registros:
                        print(f"   • ID {id_proy}: {nombre} ({sector})")
                    
                    # Extraer dataset actualizado
                    print(f"\n🔄 Actualizando dataset...")
                    data_vectores, data_dict = self.extract_full_dataset()
                    
                    if data_vectores and data_dict:
                        # Guardar dataset
                        if self.update_dataset_files(data_vectores, data_dict):
                            # Actualizar estado
                            self.cursor.execute("SELECT MAX(id_proyecto) FROM PROYECTOS")
                            max_id = self.cursor.fetchone()[0]
                            self.state["last_id_proyecto"] = max_id
                            self.state["total_records"] = len(data_vectores) - 1
                            self.save_state()
                            
                            # Disparar re-entrenamiento
                            if count_nuevos >= MIN_RETRAIN_RECORDS:
                                self.trigger_retraining(count_nuevos)
                                print(f"✅ Sistema listo para re-entrenar")
                            else:
                                print(f"⏳ Esperando {MIN_RETRAIN_RECORDS} registros para re-entrenar")
                        else:
                            print(f"❌ Error actualizando dataset")
                    else:
                        print(f"❌ Error extrayendo datos")
                else:
                    print(f"   💤 Sin cambios (último ID: {self.state['last_id_proyecto']})")
                
                # Desconectar
                self.disconnect()
                
                # Esperar
                print(f"   ⏳ Siguiente verificación en {CHECK_INTERVAL}s...")
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Monitor detenido por el usuario")
            self.disconnect()
            
            # Resumen final
            print("\n" + "=" * 80)
            print("📊 RESUMEN FINAL")
            print("=" * 80)
            print(f"Ciclos ejecutados: {cycle}")
            print(f"Total de proyectos: {self.state['total_records']}")
            print(f"Re-entrenamientos disparados: {self.state['retrains_triggered']}")
            print(f"Último ID procesado: {self.state['last_id_proyecto']}")
            
        except Exception as e:
            print(f"\n❌ Error crítico: {e}")
            self.disconnect()


# ============= MAIN =============
def main():
    """
    â­ ÃšNICO PROPÃ"SITO: Generar best_analysis_prompt.txt
    Ese archivo serÃ¡ leÃ­do por api_produccion.py
    """
    
    # ⭐ AGREGAR ESTA DETECCIÓN
    import sys
    
    if "--extract-once" in sys.argv:
        # Modo extracción única (para el entrenamiento)
        monitor = SnowflakeMonitor()
        if not monitor.connect():
            print("❌ No se pudo conectar a Snowflake")
            sys.exit(1)
        
        print("📊 Extrayendo dataset desde Snowflake...")
        data_vectores, data_dict = monitor.extract_full_dataset()
        
        if data_vectores and data_dict:
            monitor.update_dataset_files(data_vectores, data_dict)
            monitor.state["total_records"] = len(data_vectores) - 1
            monitor.save_state()
            print(f"✅ Dataset guardado: {len(data_vectores)-1} registros")
            monitor.disconnect()
            sys.exit(0)
        else:
            print("❌ Error extrayendo datos")
            monitor.disconnect()
            sys.exit(1)
    else:
        # Modo monitor continuo (original)
        monitor = SnowflakeMonitor()
        monitor.monitor_loop()


if __name__ == "__main__":
    main()