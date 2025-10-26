#!/usr/bin/env python3
"""
Script de diagnóstico para problemas de conexión a Snowflake
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("🔍 DIAGNÓSTICO DE SNOWFLAKE")
print("=" * 60)

# 1. Verificar si el módulo está instalado
print("\n1️⃣  Verificando instalación del paquete snowflake-connector-python...")
try:
    import snowflake.connector
    print("   ✅ Módulo snowflake.connector instalado")
    print(f"   📦 Versión: {snowflake.connector.__version__}")
except ImportError as e:
    print("   ❌ Módulo NO instalado")
    print(f"   📝 Error: {e}")
    print("\n   💡 SOLUCIÓN:")
    print("   pip install snowflake-connector-python")
    exit(1)

# 2. Verificar variables de entorno
print("\n2️⃣  Verificando variables de entorno en .env...")

required_vars = {
    "SNOWFLAKE_ACCOUNT": os.getenv("SNOWFLAKE_ACCOUNT"),
    "SNOWFLAKE_USER": os.getenv("SNOWFLAKE_USER"),
    "SNOWFLAKE_PASSWORD": os.getenv("SNOWFLAKE_PASSWORD"),
    "SNOWFLAKE_WAREHOUSE": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    "SNOWFLAKE_ROLE": os.getenv("SNOWFLAKE_ROLE", "SYSADMIN"),
    "UPLOAD_TO_SNOWFLAKE": os.getenv("UPLOAD_TO_SNOWFLAKE", "false")
}

missing = []
for var, value in required_vars.items():
    if var in ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]:
        if not value or value.strip() == "":
            print(f"   ❌ {var}: NO CONFIGURADO")
            missing.append(var)
        else:
            # Mostrar solo primeros/últimos caracteres por seguridad
            masked = value[:3] + "..." + value[-3:] if len(value) > 6 else "***"
            print(f"   ✅ {var}: {masked}")
    else:
        print(f"   ℹ️  {var}: {value}")

if missing:
    print(f"\n   ❌ Faltan {len(missing)} variable(s) obligatoria(s)")
    print("\n   💡 SOLUCIÓN:")
    print("   Agrega estas líneas a tu archivo .env:\n")
    for var in missing:
        print(f"   {var}=tu_valor_aqui")
    print("\n   📚 ¿Dónde encuentro estos datos?")
    print("   - SNOWFLAKE_ACCOUNT: En la URL de Snowflake (ej: abc12345.us-east-1)")
    print("   - SNOWFLAKE_USER: Tu usuario de Snowflake")
    print("   - SNOWFLAKE_PASSWORD: Tu contraseña de Snowflake")
    exit(1)

# 3. Verificar UPLOAD_TO_SNOWFLAKE
print("\n3️⃣  Verificando flag de activación...")
upload_enabled = os.getenv("UPLOAD_TO_SNOWFLAKE", "false").lower() == "true"
if upload_enabled:
    print("   ✅ UPLOAD_TO_SNOWFLAKE=true (activado)")
else:
    print("   ⚠️  UPLOAD_TO_SNOWFLAKE=false (desactivado)")
    print("\n   💡 Para habilitar subida a Snowflake:")
    print("   Agrega a tu .env: UPLOAD_TO_SNOWFLAKE=true")
    print("\n   ℹ️  El programa funcionará sin Snowflake, solo guardará en JSON/CSV")

# 4. Intentar conexión de prueba
if missing or not upload_enabled:
    print("\n⏭️  Saltando test de conexión (configuración incompleta)")
    exit(0)

print("\n4️⃣  Intentando conexión de prueba a Snowflake...")

try:
    # Conectar sin especificar warehouse/database inicialmente
    conn = snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        role=os.getenv("SNOWFLAKE_ROLE", "SYSADMIN")
    )
    
    print("   ✅ Conexión exitosa!")
    
    cursor = conn.cursor()
    
    # Activar warehouse
    warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
    print(f"   🔧 Activando warehouse {warehouse}...")
    cursor.execute(f"USE WAREHOUSE {warehouse}")
    print(f"   ✅ Warehouse {warehouse} activado")
    
    # Test de query simple
    cursor.execute("SELECT CURRENT_VERSION()")
    version = cursor.fetchone()[0]
    print(f"   📊 Snowflake version: {version}")
    
    # Establecer base de datos
    database = os.getenv("SNOWFLAKE_DATABASE", "BANORTE_AI_ANALYTICS")
    schema = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
    
    try:
        cursor.execute(f"USE DATABASE {database}")
        cursor.execute(f"USE SCHEMA {schema}")
        print(f"   ✅ Usando {database}.{schema}")
    except Exception as e:
        print(f"   ⚠️  Base de datos/schema no existe: {e}")
        print(f"\n   💡 Crea la base de datos ejecutando:")
        print(f"   CREATE DATABASE {database};")
        cursor.close()
        conn.close()
        exit(1)
    
    # Verificar si la tabla existe
    cursor.execute("""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_SCHEMA = 'PUBLIC' 
        AND TABLE_NAME = 'PROYECTOS'
    """)
    
    table_exists = cursor.fetchone()[0] > 0
    if table_exists:
        print("   ✅ Tabla PROYECTOS existe")
    else:
        print("   ⚠️  Tabla PROYECTOS NO existe")
        print("\n   💡 SOLUCIÓN:")
        print("   Crea las tablas ejecutando el script SQL de inicialización")
    
    cursor.close()
    conn.close()
    
    print("\n✅ DIAGNÓSTICO COMPLETADO - TODO FUNCIONA CORRECTAMENTE")

except snowflake.connector.errors.DatabaseError as e:
    print(f"   ❌ Error de base de datos: {e}")
    print("\n   💡 POSIBLES CAUSAS:")
    print("   - Credenciales incorrectas")
    print("   - Base de datos BANORTE_AI_ANALYTICS no existe")
    print("   - Usuario sin permisos suficientes")
    
except snowflake.connector.errors.ProgrammingError as e:
    print(f"   ❌ Error de programación: {e}")
    print("\n   💡 POSIBLES CAUSAS:")
    print("   - Warehouse no existe o está suspendido")
    print("   - Role sin permisos")
    
except Exception as e:
    print(f"   ❌ Error inesperado: {type(e).__name__}")
    print(f"   📝 Detalle: {e}")
    print("\n   💡 POSIBLES CAUSAS:")
    print("   - Problema de red/firewall")
    print("   - Account ID incorrecto")
    print("   - Formato de credenciales inválido")

print("\n" + "=" * 60)