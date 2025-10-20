import io
import re
from typing import List, Optional
from googleapiclient.http import MediaIoBaseDownload
from .google_auth import get_drive_service

# --------------------------------------------------------------------------------------
# Patrones para extraer IDs de URLs comunes de Google Drive:
# - https://drive.google.com/file/d/<ID>/view?usp=sharing
# - https://drive.google.com/open?id=<ID>
# - https://drive.google.com/uc?id=<ID>&export=download
# - O directamente el ID (alfanumérico, _ y -)
# --------------------------------------------------------------------------------------
_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]{20,})/"),        # .../file/d/<ID>/...
    re.compile(r"[?&]id=([a-zA-Z0-9_-]{20,})"),     # ...?id=<ID> o &id=<ID>
]
_ID_RAW = re.compile(r"^[a-zA-Z0-9_-]{20,}$")       # El ID puro

def extract_id_from_url(url_or_id: str) -> str:
    """
    Devuelve el ID de Drive desde una URL o un ID directo.
    """
    s = (url_or_id or "").strip()
    if not s:
        return ""
    # Caso: el usuario ya pasó el ID directamente
    if _ID_RAW.fullmatch(s):
        return s
    # Buscar en las URLs conocidas
    for pat in _ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1)
    return ""

def normalize_ids(mixed: List[str]) -> List[str]:
    """
    Recibe una lista con IDs/URLs y devuelve solo IDs válidos.
    """
    out: List[str] = []
    for x in mixed:
        fid = extract_id_from_url(x)
        if fid:
            out.append(fid)
    # Eliminar duplicados preservando el orden
    seen = set()
    unique = []
    for fid in out:
        if fid not in seen:
            unique.append(fid)
            seen.add(fid)
    return unique

def _download_binary_file(service, file_id: str) -> Optional[bytes]:
    """
    Descarga binaria un archivo de Drive mediante files().get_media.
    Retorna bytes o None si hay error (por ejemplo permisos insuficientes).
    """
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception:
        # Silencioso: devolvemos None para que el flujo no se rompa.
        return None

def download_images_by_ids(file_ids: List[str]) -> List[bytes]:
    """
    Descarga una lista de archivos desde Google Drive y devuelve sus contenidos binarios.
    Está pensada para imágenes (JPG/PNG/etc.). Si alguna descarga falla (permiso/ID),
    se omite y continúa con las demás para no interrumpir la generación del informe.
    """
    service = get_drive_service()
    binaries: List[bytes] = []

    for fid in file_ids:
        if not fid:
            continue
        data = _download_binary_file(service, fid)
        if data is not None:
            binaries.append(data)
        # Si es None, se omite silenciosamente

    return binaries
