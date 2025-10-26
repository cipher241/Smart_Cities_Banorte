# snowflake_uploader.py
"""
Módulo para subir datos desde salida_limpia.json a Snowflake.
"""
import os
from dotenv import load_dotenv

load_dotenv()

try:
    import snowflake.connector
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False


# Configuración Snowflake
SNOWFLAKE_CONFIG = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    "database": os.getenv("SNOWFLAKE_DATABASE", "BANORTE_AI_ANALYTICS"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
    "role": os.getenv("SNOWFLAKE_ROLE", "SYSADMIN")
}


def get_snowflake_connection():
    """Retorna conexión a Snowflake o None si falla."""
    if not SNOWFLAKE_AVAILABLE:
        return None
    
    # Validar credenciales
    missing = [k for k, v in SNOWFLAKE_CONFIG.items() 
               if not v and k in ["account", "user", "password"]]
    if missing:
        return None
    
    try:
        # Conectar SIN especificar warehouse inicialmente
        conn = snowflake.connector.connect(
            account=SNOWFLAKE_CONFIG["account"],
            user=SNOWFLAKE_CONFIG["user"],
            password=SNOWFLAKE_CONFIG["password"],
            role=SNOWFLAKE_CONFIG["role"]
        )
        
        cursor = conn.cursor()
        
        # Activar el warehouse explícitamente
        warehouse = SNOWFLAKE_CONFIG["warehouse"]
        try:
            cursor.execute(f"USE WAREHOUSE {warehouse}")
        except Exception as e:
            print(f"  ⚠️  No se pudo usar warehouse {warehouse}: {e}")
            # Intentar listar warehouses disponibles
            try:
                cursor.execute("SHOW WAREHOUSES")
                warehouses = cursor.fetchall()
                if warehouses:
                    available = [w[0] for w in warehouses]
                    print(f"  ℹ️  Warehouses disponibles: {', '.join(available)}")
            except:
                pass
            cursor.close()
            conn.close()
            return None
        
        # Establecer base de datos y schema
        database = SNOWFLAKE_CONFIG["database"]
        schema = SNOWFLAKE_CONFIG["schema"]
        
        try:
            cursor.execute(f"USE DATABASE {database}")
            cursor.execute(f"USE SCHEMA {schema}")
        except Exception as e:
            print(f"  ⚠️  Error estableciendo DB/Schema: {e}")
            cursor.close()
            conn.close()
            return None
        
        cursor.close()
        return conn
        
    except Exception as e:
        print(f"  ❌ Error conectando a Snowflake: {e}")
        return None


def upload_record_to_snowflake(conn, record):
    """
    Inserta un registro en las 4 tablas de Snowflake.
    Retorna (success: bool, id_proyecto o error_msg)
    """
    cursor = conn.cursor()
    
    try:
        # Asegurar que estamos en el contexto correcto
        cursor.execute(f"USE WAREHOUSE {SNOWFLAKE_CONFIG['warehouse']}")
        cursor.execute(f"USE DATABASE {SNOWFLAKE_CONFIG['database']}")
        cursor.execute(f"USE SCHEMA {SNOWFLAKE_CONFIG['schema']}")
        
        # 1. PROYECTOS
        cursor.execute("""
            INSERT INTO PROYECTOS 
                (nombre, sector, dependencia, ubicacion, anio_inicio, anio_fin, doc_fuente, fecha_carga)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            record.get("nombre"),
            record.get("sector"),
            record.get("dependencia"),
            record.get("ubicacion"),
            record.get("anio_inicio"),
            record.get("anio_fin"),
            record.get("doc_fuente"),
            record.get("fecha_carga")
        ))
        
        # Obtener ID generado
        cursor.execute("SELECT MAX(id_proyecto) FROM PROYECTOS")
        id_proyecto = cursor.fetchone()[0]
        
        # 2. FINANZAS
        cursor.execute("""
            INSERT INTO FINANZAS 
                (id_proyecto, fuente_financiamiento, presupuesto_total, 
                 costo_operativo_mxn, costo_mantenimiento_mxn, costo_beneficio_estimado_mxn,
                 eficiencia_financiera, riesgo_financiero)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            id_proyecto,
            None,
            record.get("presupuesto_total_mxn"),
            record.get("costo_operativo_mxn"),
            record.get("costo_mantenimiento_mxn"),
            record.get("costo_beneficio_estimado_mxn"),
            record.get("eficiencia_financiera"),  # ✅ Ya es FLOAT, no convertir a string
            record.get("riesgo_financiero")
        ))
        
        # 3. IMPACTO_SOCIAL
        cursor.execute("""
            INSERT INTO IMPACTO_SOCIAL 
                (id_proyecto, beneficiarios_estimados, impacto_principal, 
                 indicador_principal, avance_fisico, kpi)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            id_proyecto,
            record.get("beneficiarios_estimados"),  # ✅ Ya es FLOAT, no convertir a string
            record.get("impacto_principal"),
            record.get("indicador_principal"),
            record.get("impacto_fisico"),
            record.get("kpi")
        ))
        
        # 4. EVALUACIONES
        cursor.execute("""
            INSERT INTO EVALUACIONES 
                (id_proyecto, fecha_evaluacion, score_costo_beneficio, 
                 analisis_financiero, recomendaciones, comparativa)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            id_proyecto,
            record.get("fecha_carga"),
            record.get("score_costo_beneficio"),
            record.get("analisis_financiero"),
            record.get("resumen_observaciones"),
            record.get("comparativo")
        ))
        
        conn.commit()
        cursor.close()
        return True, id_proyecto
        
    except Exception as e:
        conn.rollback()
        cursor.close()
        return False, str(e)