import snowflake.connector
import json

# Conexión
conn = snowflake.connector.connect(
    user='GUYO',  # Using your login name
    password='VtXtg4miN9h558H',
    account='XBHKLTH-FP24352',  # Using your full account identifier
    role='ACCOUNTADMIN'  # Using your assigned role
)
cur = conn.cursor()

# Create database and schema if they don't exist
cur.execute("CREATE DATABASE IF NOT EXISTS PROYECTOS_DB")
cur.execute("USE DATABASE PROYECTOS_DB")
cur.execute("CREATE SCHEMA IF NOT EXISTS PUBLIC")
cur.execute("USE SCHEMA PUBLIC")

# Create tables if they don't exist
cur.execute("""
CREATE TABLE IF NOT EXISTS Proyectos (
    id_proyecto INTEGER,
    nombre VARCHAR(255),
    sector VARCHAR(100),
    dependencia VARCHAR(100),
    ubicacion VARCHAR(255),
    anio_inicio INTEGER,
    anio_fin INTEGER,
    doc_fuente VARCHAR(255),
    fecha_carga DATE,
    PRIMARY KEY (id_proyecto)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS Finanzas (
    id_finanzas INTEGER,
    id_proyecto_fin INTEGER,
    fuente_financiamiento VARCHAR(100),
    presupuesto_total FLOAT,
    costo_operativo_mxn FLOAT,
    costo_mantenimiento_mxn FLOAT,
    costo_beneficio_estimado_mxn FLOAT,
    eficiencia_financiera VARCHAR(50),
    riesgo_financiero VARCHAR(50),
    PRIMARY KEY (id_finanzas),
    FOREIGN KEY (id_proyecto_fin) REFERENCES Proyectos(id_proyecto)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS Impacto (
    id_impacto INTEGER,
    id_proyecto_imp INTEGER,
    beneficiarios_estimados VARCHAR(100),
    impacto_principal VARCHAR(255),
    indicador_principal VARCHAR(255),
    avance_fisico FLOAT,
    kpi FLOAT,
    PRIMARY KEY (id_impacto),
    FOREIGN KEY (id_proyecto_imp) REFERENCES Proyectos(id_proyecto)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS Evaluacion (
    id_evol INTEGER,
    id_proyecto_eval INTEGER,
    fecha_evol DATE,
    score_costo_beneficio FLOAT,
    analisis_financiero VARCHAR(255),
    recomendaciones VARCHAR(255),
    comparativa VARCHAR(255),
    PRIMARY KEY (id_evol),
    FOREIGN KEY (id_proyecto_eval) REFERENCES Proyectos(id_proyecto)
)
""")

# First, let's read existing data from Snowflake
print("Reading existing data from Snowflake...")

# Query to get data from all tables
cur.execute("""
    SELECT 
        p.*,
        f.id_finanzas, f.id_proyecto_fin, f.fuente_financiamiento, f.presupuesto_total,
        f.costo_operativo_mxn, f.costo_mantenimiento_mxn, f.costo_beneficio_estimado_mxn,
        f.eficiencia_financiera, f.riesgo_financiero,
        i.id_impacto, i.id_proyecto_imp, i.beneficiarios_estimados, i.impacto_principal,
        i.indicador_principal, i.avance_fisico, i.kpi,
        e.id_evol, e.id_proyecto_eval, e.fecha_evol, e.score_costo_beneficio,
        e.analisis_financiero, e.recomendaciones, e.comparativa
    FROM Proyectos p
    LEFT JOIN Finanzas f ON p.id_proyecto = f.id_proyecto_fin
    LEFT JOIN Impacto i ON p.id_proyecto = i.id_proyecto_imp
    LEFT JOIN Evaluacion e ON p.id_proyecto = e.id_proyecto_eval
    ORDER BY p.id_proyecto
""")

# Fetch all existing data
existing_data = cur.fetchall()

# Get column names from the query
columns = [desc[0] for desc in cur.description]

print("\nExisting data in Snowflake:")
if existing_data:
    print(f"\nFound {len(existing_data)} projects in the database:")
    for row in existing_data:
        print(f"\nProject ID: {row[0]}")
        print(f"Name: {row[1]}")
        print("-------------------")
else:
    print("No existing data found in the database.")

# Now proceed with the new data to be inserted
# Save fetched data to a JSON file
rows_as_dicts = [dict(zip(columns, row)) for row in existing_data]
output_path = 'snowflake_projects.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(rows_as_dicts, f, ensure_ascii=False, indent=2, default=str)

print(f"Saved {len(rows_as_dicts)} rows to {output_path}")

cur.close()
conn.close()