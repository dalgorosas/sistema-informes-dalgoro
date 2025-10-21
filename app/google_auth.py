from pathlib import Path
from typing import Optional, Dict, Any

import base64
import json
import os
import textwrap

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


def _coerce_private_key(info: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza el campo private_key para evitar errores comunes."""
    info = dict(info)
    key = info.get("private_key")
    if isinstance(key, str):
        # Render (y otros PaaS) suelen almacenar el JSON con '\\n'.
        # Si detectamos que no hay saltos de línea reales, los restauramos.
        if "\\n" in key and "\n" not in key:
            info["private_key"] = key.replace("\\n", "\n")

        # Normalizar fin de línea y eliminar espacios extra para evitar firmas inválidas.
        normalized = info["private_key"].replace("\r\n", "\n").strip()
                
        # Asegurarnos de que comience y termine correctamente para evitar firmas inválidas.
        if "-----BEGIN" not in normalized or "-----END" not in normalized:
            raise RuntimeError("El private_key del servicio no parece un PEM válido. Revisa el JSON de credenciales.")

        begin_marker = "-----BEGIN PRIVATE KEY-----"
        end_marker = "-----END PRIVATE KEY-----"

        if begin_marker in normalized and end_marker in normalized:
            # Si todo está en una sola línea (caso común al copiar desde variables de entorno)
            # reconstruimos un PEM válido con saltos de línea cada 64 caracteres.
            body = normalized
            if "\n" not in normalized or normalized.count("\n") < 2:
                body = normalized.replace(begin_marker, "").replace(end_marker, "")
                body = body.replace("\n", "").replace("\r", "")
                wrapped = "\n".join(textwrap.wrap(body.strip(), 64))
                normalized = f"{begin_marker}\n{wrapped}\n{end_marker}\n"
            else:
                # Aseguramos fin de archivo con salto de línea por compatibilidad.
                if not normalized.endswith("\n"):
                    normalized = f"{normalized}\n"

        info["private_key"] = normalized    
    return info


def _credentials_from_info(info: Dict[str, Any]):
    return service_account.Credentials.from_service_account_info(_coerce_private_key(info), scopes=SCOPES)


def _credentials_from_json_str(raw_json: str):
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON no contiene un JSON válido. "
            "Si lo guardaste en Base64 usa GOOGLE_SERVICE_ACCOUNT_JSON_B64."
        ) from exc
    return _credentials_from_info(info)


def get_credentials():
    
    json_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_env:
        return _credentials_from_json_str(json_env)

    json_env_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "").strip()
    if json_env_b64:
        try:
            decoded = base64.b64decode(json_env_b64)
        except Exception as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON_B64 no es un Base64 válido.") from exc
        return _credentials_from_json_str(decoded.decode("utf-8"))        

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

    with path_obj.open("r", encoding="utf-8") as fh:
        info = json.load(fh)
    return _credentials_from_info(info)    

def get_sheets_client():
    creds = get_credentials()
    return gspread.authorize(creds)

def get_drive_service():
    creds = get_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)
