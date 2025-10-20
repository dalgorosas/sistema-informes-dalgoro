from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
import os
import re
from docxtpl import DocxTemplate
import subprocess
from pathlib import Path
try:
    from docx2pdf import convert as docx2pdf_convert
    _DOCX2PDF_AVAILABLE = True
except Exception:
    _DOCX2PDF_AVAILABLE = False

# --- Módulos de conexión DALGORO ---
from .google_sheets import (
    get_row_by_id,
    get_report_by_id,
    list_projects,
    get_project_by_id,
)
from .google_drive import download_images_by_ids, normalize_ids
from .report_generator import build_context
from .config import DOCX_TEMPLATE_PATH, OUTPUT_DIR

from .config import REPORTS_TIMEZONE, REPORTS_SEQ_SHEET_NAME
from .google_sheets import reserve_report_sequence, format_report_number, append_report_entry
from datetime import datetime
import pytz


# ---------------- Configuración ----------------
templates = Jinja2Templates(directory="templates")
app = FastAPI(title="Generador de Informes DALGORO")

# Montar carpeta de estáticos (logo, css)
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Asegurar carpeta de salida
os.makedirs(OUTPUT_DIR, exist_ok=True)

PDF_ENABLED = os.getenv("PDF_ENABLED", "auto").lower()  # 'auto' | 'on' | 'off'

_INVALID_CHARS = r'[\\/:\"*?<>|]+'
def safe_filename(text: str) -> str:
    return re.sub(_INVALID_CHARS, "_", str(text)).strip()


def _try_convert_to_pdf(docx_path: str) -> str:
    """
    Convierte DOCX a PDF usando docx2pdf (Word) o LibreOffice.
    Devuelve el nombre del PDF si se genera; en caso contrario, "".
    """
    if PDF_ENABLED == "off":
        return ""

    p = Path(docx_path).resolve()
    pdf_path = p.with_suffix(".pdf")

    # 1) Intentar con docx2pdf (Word) – inicializando COM en este hilo
    if _DOCX2PDF_AVAILABLE:
        try:
            import pythoncom  # viene con pywin32
            pythoncom.CoInitialize()
            try:
                from docx2pdf import convert as docx2pdf_convert
                docx2pdf_convert(str(p), str(pdf_path))  # file -> file
                if pdf_path.exists():
                    print("[PDF] OK via docx2pdf:", pdf_path)
                    return pdf_path.name
            finally:
                pythoncom.CoUninitialize()
        except Exception as ex:
            print("[PDF] docx2pdf fallo:", ex)

    # 2) LibreOffice (si lo instalas)
    for soffice in [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "soffice",
    ]:
        try:
            r = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", str(p.parent), str(p)],
                check=True, capture_output=True, text=True
            )
            print("[PDF] LO stdout:", r.stdout)
            print("[PDF] LO stderr:", r.stderr)
            if pdf_path.exists():
                print("[PDF] OK via LibreOffice:", pdf_path)
                return pdf_path.name
        except Exception as ex:
            print(f"[PDF] LibreOffice fallo con {soffice}:", ex)
            continue

    print("[PDF] No se pudo generar PDF para:", p)
    return ""

# ---------------- RUTAS ----------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # Cargar lista de proyectos para el selector (no rompe si falla)
    try:
        projects = list_projects()
    except Exception:
        projects = []
    return templates.TemplateResponse("form.html", {"request": request, "projects": projects})


@app.get("/previsualizar", response_class=HTMLResponse)
def previsualizar(request: Request, id_informe: str):
    """
    Carga datos desde Sheets para previsualizar en el formulario.
    Busca primero en la hoja nueva (Informes) y, si no hay, en la hoja legada (GSHEET_TAB).
    Luego intenta enriquecer con los datos del proyecto (Proyectos).
    """
    try:
        row_reporte = get_report_by_id(id_informe)  # hoja nueva "Informes"
        if not row_reporte:
            row_reporte = get_row_by_id(id_informe)  # Fallback a hoja antigua
    except Exception as e:
        return HTMLResponse(
            f"Error al leer Google Sheets: {e}. "
            f"Verifica GSHEET_ID/hojas/credenciales.",
            status_code=500
        )

    if not row_reporte:
        return HTMLResponse(f"No se encontró id_informe={id_informe} en las hojas configuradas.", status_code=404)

    # Enriquecer con datos del proyecto si hay proyecto_id
    proyecto_id = str(row_reporte.get("proyecto_id", "")).strip()
    row_proyecto = get_project_by_id(proyecto_id) if proyecto_id else {}
    row = {**row_proyecto, **row_reporte}
    row["id_informe"] = id_informe

    # Volver a pasar la lista de proyectos al template
    try:
        projects = list_projects()
    except Exception:
        projects = []

    return templates.TemplateResponse("form.html", {"request": request, "row": row, "projects": projects})


@app.post("/generar_desde_sheet", response_class=HTMLResponse)
def generar_desde_sheet(request: Request, id_informe: str = Form(...)):
    """
    Genera el DOCX directamente con los datos cargados desde Sheets.
    Admite imágenes de Drive (IDs o URLs).
    """
    try:
        row_reporte = get_report_by_id(id_informe)
        if not row_reporte:
            row_reporte = get_row_by_id(id_informe)
    except Exception as e:
        return HTMLResponse(
            f"Error al leer Google Sheets: {e}. "
            f"Verifica GSHEET_ID/hojas/credenciales.",
            status_code=500
        )

    if not row_reporte:
        return HTMLResponse(f"No se encontró id_informe={id_informe} en las hojas configuradas.", status_code=404)

    ids_raw = [s.strip() for s in str(row_reporte.get("imagenes_drive_ids", "")).split(",") if s.strip()]
    ids = normalize_ids(ids_raw)
    images = download_images_by_ids(ids) if ids else []

    if not os.path.exists(DOCX_TEMPLATE_PATH):
        return HTMLResponse(
            f"No se encontró la plantilla DOCX: {DOCX_TEMPLATE_PATH}. "
            f"Actualiza DOCX_TEMPLATE_PATH o coloca el archivo en esa ruta.",
            status_code=500
        )

    # Enriquecer con datos del proyecto si hay proyecto_id
    proyecto_id = str(row_reporte.get("proyecto_id", "")).strip()
    row_proyecto = get_project_by_id(proyecto_id) if proyecto_id else {}
    row = {**row_proyecto, **row_reporte}

    # === NUEVO: reservar consecutivo e inyectar numero_informe en el contexto ===
    responsable_val = str(row.get("responsable", "")).strip() or "SIN_RESPONSABLE"
    seq = reserve_report_sequence(REPORTS_SEQ_SHEET_NAME, responsable_val, proyecto_id)
    numero_informe = format_report_number(seq)

    doc = DocxTemplate(DOCX_TEMPLATE_PATH)
    row["numero_informe"] = numero_informe  # para que build_context lo recoja
    context = build_context(doc, row, images)


    nombre_base = row.get("nombre_proyecto") or row.get("proyecto", "")
    proyecto_safe = safe_filename(nombre_base).replace(" ", "_")
    cliente_safe  = safe_filename(row.get("cliente", "")).replace(" ", "_")
    fecha_raw     = str(row.get("fecha", ""))
    fecha_safe    = safe_filename(fecha_raw.replace("/", "-").replace("\\", "-"))
    filename = f"{numero_informe}_{proyecto_safe}_{cliente_safe}_{fecha_safe}.docx" if (proyecto_safe or cliente_safe or fecha_safe) else f"{numero_informe}.docx"
    path = os.path.join(OUTPUT_DIR, filename)

    try:
        doc.render(context)
        doc.save(path)
    except Exception as e:
        return HTMLResponse(f"Error generando el DOCX: {e}", status_code=500)

    # --- NUEVO: intentar convertir a PDF ---
    filename_pdf = _try_convert_to_pdf(path)

    # --- NUEVO: registrar en bitácora de informes ---
    try:
        tz = pytz.timezone(REPORTS_TIMEZONE)
        fecha_iso = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        append_report_entry(proyecto_id=proyecto_id, id_informe=numero_informe, fecha_iso=fecha_iso, responsable=responsable_val)
    except Exception as e:
        print(f"[WARN] Falló registro de informe en 'Informes': {e}")

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "filename": filename, "filename_pdf": filename_pdf, "numero_informe": numero_informe}
    )


@app.get("/get_project_data", response_class=HTMLResponse)
def get_project_data(request: Request, proyecto_id: str):
    """Devuelve los datos de un proyecto en JSON para autollenar el formulario."""
    try:
        data = get_project_by_id(proyecto_id)
        if not data:
            return {"success": False, "error": "Proyecto no encontrado"}
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/generar", response_class=HTMLResponse)
def generar(
    request: Request,
    proyecto_id: str = Form(""),
    nombre_proyecto: str = Form(""),
    proyecto: str = Form(...),
    cliente: str = Form(...),
    fecha: str = Form(...),
    responsable: str = Form(...),
    objetivo_visita: str = Form(""),
    metodologia: str = Form(""),
    descripcion: str = Form(""),
    hallazgos: str = Form(""),
    conformidades: str = Form(""),
    no_conformidades: str = Form(""),
    acciones_inmediatas: str = Form(""),
    conclusiones: str = Form(""),
    recomendaciones: str = Form(""),
    nivel_cumplimiento: str = Form(""),
    imagenes_drive_ids: Optional[str] = Form(None),
):
    # Si viene proyecto_id, intenta traer datos del proyecto
    row_proyecto = {}
    if proyecto_id.strip():
        try:
            fetched = get_project_by_id(proyecto_id.strip())
            if fetched:
                row_proyecto = fetched
        except Exception:
            row_proyecto = {}

    # Normalizar/descargar imágenes
    ids: List[str] = []
    if imagenes_drive_ids:
        ids = [s.strip() for s in imagenes_drive_ids.split(",") if s.strip()]
        ids = normalize_ids(ids)
    images = download_images_by_ids(ids) if ids else []

    # Contexto para la plantilla
    row_like = {
        "proyecto_id": proyecto_id,
        "nombre_proyecto": (nombre_proyecto or row_proyecto.get("nombre_proyecto") or proyecto),
        "promotor_representante": row_proyecto.get("promotor_representante", ""),
        "licencia_ambiental": row_proyecto.get("licencia_ambiental", ""),
        "sector_productivo": row_proyecto.get("sector_productivo", ""),
        "ubicacion_politica": row_proyecto.get("ubicacion_politica", ""),
        "area": row_proyecto.get("area", ""),
        "proyecto": proyecto,
        "cliente": cliente,
        "fecha": fecha,
        "responsable": responsable,
        "objetivo_visita": objetivo_visita,
        "metodologia": metodologia,
        "descripcion": descripcion,
        "hallazgos": hallazgos,
        "conformidades": conformidades,
        "no_conformidades": no_conformidades,
        "acciones_inmediatas": acciones_inmediatas,
        "conclusiones": conclusiones,
        "recomendaciones": recomendaciones,
        "nivel_cumplimiento": nivel_cumplimiento,
    }
    # === NUEVO: reservar consecutivo e inyectar numero_informe ===
    responsable_val = (responsable or "").strip() or "SIN_RESPONSABLE"
    seq = reserve_report_sequence(REPORTS_SEQ_SHEET_NAME, responsable_val, proyecto_id)
    numero_informe = format_report_number(seq)
    row_like["numero_informe"] = numero_informe


    if not os.path.exists(DOCX_TEMPLATE_PATH):
        return HTMLResponse(f"No se encontró la plantilla DOCX: {DOCX_TEMPLATE_PATH}", status_code=500)

    doc = DocxTemplate(DOCX_TEMPLATE_PATH)
    context = build_context(doc, row_like, images)

    nombre_base = row_like.get("nombre_proyecto") or row_like.get("proyecto", "")
    proyecto_safe = safe_filename(nombre_base).replace(" ", "_")
    cliente_safe = safe_filename(cliente).replace(" ", "_")
    fecha_safe = safe_filename(fecha.replace("/", "-").replace("\\", "-"))
    filename = f"{numero_informe}_{proyecto_safe}_{cliente_safe}_{fecha_safe}.docx" if (proyecto_safe or cliente_safe or fecha_safe) else f"{numero_informe}.docx"
    path = os.path.join(OUTPUT_DIR, filename)

    try:
        doc.render(context)
        doc.save(path)
    except Exception as e:
        return HTMLResponse(f"Error generando el DOCX: {e}", status_code=500)

    # --- NUEVO: intentar convertir a PDF ---
    filename_pdf = _try_convert_to_pdf(path)

    # --- NUEVO: registrar en bitácora de informes ---
    try:
        tz = pytz.timezone(REPORTS_TIMEZONE)
        fecha_iso = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        append_report_entry(proyecto_id=proyecto_id, id_informe=numero_informe, fecha_iso=fecha_iso, responsable=responsable_val)
    except Exception as e:
        print(f"[WARN] Falló registro de informe en 'Informes': {e}")

    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "filename": filename,
            "filename_pdf": filename_pdf,
            "numero_informe": numero_informe,
        },
    )

@app.get("/descargar/{filename}")
def descargar(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return HTMLResponse("Archivo no encontrado", status_code=404)
    # MIME dinámico según extensión
    mime = "application/pdf" if filename.lower().endswith(".pdf") \
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=mime, filename=filename)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
