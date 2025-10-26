import os
import json
from pathlib import Path
from datetime import datetime
import google.generativeai as genai
import pdfplumber
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from dotenv import load_dotenv

load_dotenv()

# ============= CONFIGURACIÓN =============
BEST_PROMPT_FILE = "best_analysis_prompt.txt"
MODEL = "gemini-2.0-flash-exp"
OUTPUT_DIR = "analisis_generados"


class AnalizadorProyectos:
    """
    ⭐ API PRINCIPAL DE PRODUCCIÓN
    Lee el mejor prompt del entrenamiento y analiza PDFs nuevos
    """
    
    def __init__(self):
        self.best_prompt = self.load_best_prompt()
        self.client = self.init_gemini()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    def load_best_prompt(self):
        """⭐ CARGA EL MEJOR PROMPT DEL ENTRENAMIENTO"""
        if not Path(BEST_PROMPT_FILE).exists():
            print(f"❌ Prompt no encontrado: {BEST_PROMPT_FILE}")
            print(f"💡 Ejecuta primero: python MainEntrenamientoForzado.py")
            return None
        
        with open(BEST_PROMPT_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extraer solo el prompt (sin headers)
        if "PROMPT OPTIMIZADO:" in content:
            prompt = content.split("PROMPT OPTIMIZADO:")[1].split("=" * 80)[0].strip()
        elif "=" * 80 in content:
            # Si tiene headers, tomar después del último separador
            parts = content.split("=" * 80)
            prompt = parts[-1].strip()
        else:
            prompt = content
        
        print(f"✅ Mejor prompt cargado ({len(prompt)} caracteres)")
        return prompt
    
    def init_gemini(self):
        """Inicializa cliente Gemini"""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ GEMINI_API_KEY no encontrada")
            return None
        
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(MODEL)
    
    def extract_text_from_pdf(self, pdf_path):
        """Extrae texto del PDF"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
                text = "\n".join(pages).strip()
            
            print(f"✅ Texto extraído: {len(text)} caracteres")
            return text
        except Exception as e:
            print(f"❌ Error extrayendo texto: {e}")
            return None
    
    def analyze_with_best_prompt(self, document_text):
        """⭐ USA EL MEJOR PROMPT PARA ANALIZAR"""
        
        if not self.best_prompt or not self.client:
            return None
        
        # Insertar el documento en el prompt
        final_prompt = self.best_prompt.replace("{DOCUMENTO}", document_text)
        
        try:
            print("🤖 Analizando con Gemini usando mejor prompt...")
            response = self.client.generate_content(final_prompt)
            
            # Parsear JSON
            raw = response.text.strip()
            
            # Limpiar marcadores
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                parts = raw.split("```")
                if len(parts) >= 3:
                    raw = parts[1]
            
            result = json.loads(raw.strip())
            
            print("✅ Análisis completado")
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ Error parseando JSON: {e}")
            print(f"Raw output: {response.text[:500]}")
            return None
        except Exception as e:
            print(f"❌ Error en análisis: {e}")
            return None
    
    def generate_pdf_report(self, analysis, original_filename):
        """Genera PDF con el análisis completo"""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"analisis_{timestamp}.pdf"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Título
        story.append(Paragraph("ANÁLISIS DE PROYECTO DE INFRAESTRUCTURA", styles['Title']))
        story.append(Spacer(1, 0.2 * inch))
        
        # Info del documento
        story.append(Paragraph(f"<b>Documento analizado:</b> {original_filename}", styles['Normal']))
        story.append(Paragraph(f"<b>Fecha de análisis:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 0.3 * inch))
        
        # Datos del proyecto
        story.append(Paragraph("<b>INFORMACIÓN DEL PROYECTO</b>", styles['Heading1']))
        story.append(Spacer(1, 0.1 * inch))
        
        project_data = [
            ["Campo", "Valor"],
            ["Nombre", analysis.get("nombre", "N/A")],
            ["Sector", analysis.get("sector", "N/A")],
            ["Dependencia", analysis.get("dependencia", "N/A")],
            ["Ubicación", analysis.get("ubicacion", "N/A")],
            ["Año inicio", str(analysis.get("anio_inicio", "N/A"))],
            ["Año fin", str(analysis.get("anio_fin", "N/A"))],
        ]
        
        t = Table(project_data)
        story.append(t)
        story.append(Spacer(1, 0.3 * inch))
        
        # Análisis financiero
        story.append(Paragraph("<b>ANÁLISIS FINANCIERO</b>", styles['Heading1']))
        story.append(Spacer(1, 0.1 * inch))
        
        presupuesto = analysis.get("presupuesto_total_mxn", 0)
        if presupuesto:
            story.append(Paragraph(f"<b>Presupuesto Total:</b> ${presupuesto:,.2f} MXN", styles['Normal']))
        
        beneficiarios = analysis.get("beneficiarios_estimados", 0)
        if beneficiarios:
            story.append(Paragraph(f"<b>Beneficiarios Estimados:</b> {beneficiarios:,.0f}", styles['Normal']))
        
        story.append(Spacer(1, 0.2 * inch))
        
        analisis_fin = analysis.get("analisis_financiero", "No disponible")
        story.append(Paragraph(analisis_fin, styles['Normal']))
        story.append(Spacer(1, 0.3 * inch))
        
        # Score costo-beneficio
        score = analysis.get("score_costo_beneficio", 0)
        story.append(Paragraph("<b>EVALUACIÓN COSTO-BENEFICIO</b>", styles['Heading1']))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"<b>Score:</b> {score}/10", styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))
        
        # Recomendaciones
        if "recomendaciones" in analysis:
            story.append(Paragraph("<b>RECOMENDACIONES</b>", styles['Heading1']))
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(analysis["recomendaciones"], styles['Normal']))
        
        # Construir PDF
        doc.build(story)
        
        print(f"📄 PDF generado: {output_path}")
        return output_path
    
    def analyze_pdf(self, pdf_path):
        """
        ⭐ MÉTODO PRINCIPAL: Analiza un PDF y retorna análisis + PDF
        
        Este es el método que llamarías desde tu API REST
        """
        
        print("\n" + "=" * 80)
        print("📊 ANÁLISIS DE PROYECTO CON MEJOR PROMPT")
        print("=" * 80)
        print(f"📁 Archivo: {pdf_path}\n")
        
        # 1. Extraer texto
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return None, None
        
        # 2. Analizar con mejor prompt
        analysis = self.analyze_with_best_prompt(text)
        if not analysis:
            return None, None
        
        # 3. Generar PDF
        pdf_output = self.generate_pdf_report(analysis, os.path.basename(pdf_path))
        
        # 4. Retornar resultados
        print("\n" + "=" * 80)
        print("✅ ANÁLISIS COMPLETADO")
        print("=" * 80)
        print(f"📊 Score costo-beneficio: {analysis.get('score_costo_beneficio', 'N/A')}/10")