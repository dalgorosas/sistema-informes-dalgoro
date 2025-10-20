import os
from dotenv import load_dotenv

# ------------------------------------------------------
# Cargar variables del archivo .env
# ------------------------------------------------------
load_dotenv()

# ------------------------------------------------------
# Autenticación y Google Sheets
# ------------------------------------------------------
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GSHEET_ID = os.getenv("GSHEET_ID")

# Hoja principal (retrocompatibilidad)
GSHEET_TAB = os.getenv("GSHEET_TAB", "Datos")

# Nuevas hojas para estructura ampliada
GSHEET_TAB_PROYECTOS = os.getenv("GSHEET_TAB_PROYECTOS", "Proyectos")
GSHEET_TAB_REPORTES = os.getenv("GSHEET_TAB_REPORTES", "Informes")

# ------------------------------------------------------
# Plantillas y salida
# ------------------------------------------------------
DOCX_TEMPLATE_PATH = os.getenv("DOCX_TEMPLATE_PATH", "report_templates/reporte_base.docx")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "downloads")
IMAGE_MAX_WIDTH = int(os.getenv("IMAGE_MAX_WIDTH", "500"))

# ------------------------------------------------------
# Numeración de informes y bitácora
# ------------------------------------------------------
# Hoja donde se registran los informes (ya definida por variable, se mantiene)
# GSHEET_TAB_REPORTES = "Informes"   # (ya declarada arriba, se reutiliza)

# Hoja para contador/turnero de informes (se creará si no existe)
REPORTS_SEQ_SHEET_NAME = os.getenv("REPORTS_SEQ_SHEET_NAME", "INFORMES_SEQ")

# Formato del número de informe
REPORTS_NUMBER_PREFIX = os.getenv("REPORTS_NUMBER_PREFIX", "INF")  # prefijo, p.ej. 'INF'
REPORTS_NUMBER_PAD = int(os.getenv("REPORTS_NUMBER_PAD", "5"))     # ancho con ceros, p.ej. 00001

# Zona horaria para las marcas de tiempo
REPORTS_TIMEZONE = os.getenv("REPORTS_TIMEZONE", "America/Guayaquil")

# ------------------------------------------------------
# Asegurar que existan rutas necesarias
# ------------------------------------------------------
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === Gráfico de Cumplimiento (pie) ===
CHART_WIDTH_MM = 80  # ancho del gráfico en el documento
# Paleta basada en tu UI/branding (gradiente oscuro azul-verde)
COLOR_CUMPLIMIENTO = "#2c5364"  # verde-azulado (match paleta)
COLOR_PENDIENTE = "#203a43"     # azul profundo (match paleta)
CHART_BG = "white"              # fondo blanco para compatibilidad DOCX
