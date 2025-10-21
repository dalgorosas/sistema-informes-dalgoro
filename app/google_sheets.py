from typing import Dict, Any, Optional, List
from .google_auth import get_sheets_client
from .config import GSHEET_ID, GSHEET_TAB, GSHEET_TAB_REPORTES, GSHEET_TAB_PROYECTOS
from datetime import datetime
import pytz
from .config import REPORTS_TIMEZONE, GSHEET_TAB_REPORTES, REPORTS_SEQ_SHEET_NAME, REPORTS_NUMBER_PREFIX, REPORTS_NUMBER_PAD

# -----------------------------------------
# Utilidades internas
# -----------------------------------------
def _require_gsheet_id() -> str:
    if not GSHEET_ID:
        raise RuntimeError(
            "GSHEET_ID no está configurado. Define la variable de entorno GSHEET_ID con el ID del Spreadsheet."
        )
    return GSHEET_ID


def _open_ws(tab_name: str):
    gc = get_sheets_client()
    sh = gc.open_by_key(_require_gsheet_id())
    return sh.worksheet(tab_name)

def _get_all_records(tab_name: str) -> List[Dict[str, Any]]:
    ws = _open_ws(tab_name)
    return ws.get_all_records()

def _open_or_create_ws(tab_name: str):
    """
    Abre la hoja; si no existe, la crea (1x8) y la retorna.
    """
    gc = get_sheets_client()
    sh = gc.open_by_key(_require_gsheet_id())
    try:
        return sh.worksheet(tab_name)
    except Exception:
        sh.add_worksheet(title=tab_name, rows=1, cols=8)
        return sh.worksheet(tab_name)

def ensure_headers(tab_name: str, headers: List[str]) -> None:
    """
    Crea la hoja si no existe y asegura cabeceras exactas en fila 1.
    """
    ws = _open_or_create_ws(tab_name)
    first_row = ws.row_values(1)
    if not first_row:
        end_col = chr(ord('A') + len(headers) - 1)
        ws.update(f"A1:{end_col}1", [headers])

def reserve_report_sequence(tab_name: str, responsable: str, proyecto_id: str) -> int:
    """
    'Toma turno' atómicamente: agrega una fila con timestamp y devuelve el número consecutivo.
    El consecutivo = (nro_fila - 1) porque la fila 1 es cabecera.
    """
    ensure_headers(tab_name, ["timestamp", "responsable", "proyecto_id"])
    ws = _open_or_create_ws(tab_name)

    tz = pytz.timezone(REPORTS_TIMEZONE)
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    ws.append_row([ts, responsable, proyecto_id], value_input_option="USER_ENTERED")
    total_rows = len(ws.get_all_values())
    seq = total_rows - 1  # fila 2 => secuencia 1
    if seq < 1:
        raise RuntimeError("No se pudo calcular el consecutivo de informes.")
    return seq

def format_report_number(seq: int, prefix: str = REPORTS_NUMBER_PREFIX, pad: int = REPORTS_NUMBER_PAD) -> str:
    year = datetime.now().year
    return f"{prefix}-{year}-{seq:0{pad}d}"

def append_report_entry(proyecto_id: str, id_informe: str, fecha_iso: str, responsable: str) -> None:
    """
    Agrega la fila a la hoja de 'Informes' con columnas:
    proyecto_id | id_informe | fecha | responsable
    """
    ensure_headers(GSHEET_TAB_REPORTES, ["proyecto_id", "id_informe", "fecha", "responsable"])
    ws = _open_or_create_ws(GSHEET_TAB_REPORTES)
    ws.append_row([proyecto_id, id_informe, fecha_iso, responsable], value_input_option="USER_ENTERED")

# -----------------------------------------
# INFORMES (hoja nueva por defecto)
# -----------------------------------------
def get_report_by_id(id_informe: str) -> Optional[Dict[str, Any]]:
    """
    Busca un informe por su id_informe en la hoja de reportes NUEVA (Informes).
    """
    rows = _get_all_records(GSHEET_TAB_REPORTES)
    for r in rows:
        if str(r.get("id_informe", "")).strip() == str(id_informe).strip():
            return r
    return None

# -----------------------------------------
# RETROCOMPATIBILIDAD (hoja legada GSHEET_TAB)
# -----------------------------------------
def get_row_by_id(id_informe: str) -> Optional[Dict[str, Any]]:
    """
    Fallback real a la hoja antigua (GSHEET_TAB, p.ej. 'Hoja1').
    Se usa mientras migras a la nueva estructura por dos hojas.
    """
    rows = _get_all_records(GSHEET_TAB)
    for r in rows:
        if str(r.get("id_informe", "")).strip() == str(id_informe).strip():
            return r
    return None

# -----------------------------------------
# PROYECTOS
# -----------------------------------------
def list_projects() -> List[Dict[str, Any]]:
    """
    Retorna todos los proyectos de la hoja Proyectos (nueva).
    Encabezados esperados:
      proyecto_id, nombre_proyecto, promotor_representante, licencia_ambiental,
      sector_productivo, ubicacion_politica, area
    """
    return _get_all_records(GSHEET_TAB_PROYECTOS)

def get_project_by_id(proyecto_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca un proyecto por su proyecto_id en la hoja Proyectos (nueva).
    """
    if not proyecto_id:
        return None
    rows = list_projects()
    for r in rows:
        if str(r.get("proyecto_id", "")).strip() == str(proyecto_id).strip():
            return r
    return None

def add_project(project: Dict[str, Any]) -> str:
    """
    Inserta un proyecto en la hoja Proyectos.
    Requiere scope de escritura en Sheets.
    """
    ws = _open_ws(GSHEET_TAB_PROYECTOS)
    headers = ws.row_values(1)  # respetar orden de columnas
    row_to_append = [project.get(h, "") for h in headers]
    ws.append_row(row_to_append)
    return str(project.get("proyecto_id", "")) or ""
