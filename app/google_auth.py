from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread
from .config import GOOGLE_SERVICE_ACCOUNT_FILE

# Scopes: lectura Drive; y Sheets con ESCRITURA (no solo readonly)
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

def _default_credentials_path() -> Optional[str]:
    """Retorna la ruta por defecto al JSON si existe en ./credentials."""
    candidate = Path(__file__).resolve().parent.parent / "credentials" / "service_account.json"
    if candidate.exists():
        return str(candidate)
    return None


def get_credentials():
    import os
    import json
    json_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_env:
        info = json.loads(json_env)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    service_account_file = (GOOGLE_SERVICE_ACCOUNT_FILE or "").strip() or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not service_account_file:
        service_account_file = _default_credentials_path() or ""

    if not service_account_file:
        raise RuntimeError(
            "No se encontró GOOGLE_SERVICE_ACCOUNT_JSON ni GOOGLE_SERVICE_ACCOUNT_FILE. "
            "Configura una de las variables o coloca el archivo en credentials/service_account.json."
        )

    path_obj = Path(service_account_file)
    if not path_obj.is_file():
        raise RuntimeError(
            f"El archivo de credenciales no existe en la ruta proporcionada: {service_account_file}. "
            "Verifica el valor de GOOGLE_SERVICE_ACCOUNT_FILE."
        )

    return service_account.Credentials.from_service_account_file(str(path_obj), scopes=SCOPES)

def get_sheets_client():
    creds = get_credentials()
    return gspread.authorize(creds)

def get_drive_service():
    creds = get_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)
