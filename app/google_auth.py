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

def _log_sa_info(source: str, info: Dict[str, Any]):
    try:
        print(f"[GOOGLE_AUTH] Source={source} client_email={info.get('client_email')} key_id={info.get('private_key_id')}")
    except Exception:
        pass

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
    _log_sa_info("ENV_JSON", info)
    return _credentials_from_info(info)


def get_credentials():
    # 1) INTENTO: JSON plano en variable de entorno
    json_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_env:
        try:
            info = json.loads(json_env)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON no contiene un JSON válido."
            ) from exc
        _log_sa_info("ENV_JSON", info)
        return _credentials_from_info(info)

    # 2) INTENTO: JSON en Base64 en variable de entorno
    json_env_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "").strip()
    if json_env_b64:
        try:
            decoded = base64.b64decode(json_env_b64)
            info = json.loads(decoded.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_B64 no es un Base64/JSON válido."
            ) from exc
        _log_sa_info("ENV_B64", info)
        return _credentials_from_info(info)

    # 3) INTENTO: archivo en ruta (env o por defecto en ./credentials/service_account.json)
    service_account_file = (GOOGLE_SERVICE_ACCOUNT_FILE or "").strip() or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not service_account_file:
        service_account_file = _default_credentials_path() or ""

    if not service_account_file:
        # Guardarraíl: no hay JSON, no hay B64 y tampoco ruta a archivo.
        raise RuntimeError(
            "No se encontró GOOGLE_SERVICE_ACCOUNT_JSON ni GOOGLE_SERVICE_ACCOUNT_JSON_B64 ni GOOGLE_SERVICE_ACCOUNT_FILE. "
            "Define una de ellas o coloca el archivo en credentials/service_account.json."
        )

    path_obj = Path(service_account_file)
    if not path_obj.is_file():
        raise RuntimeError(
            f"El archivo de credenciales no existe en la ruta proporcionada: {service_account_file}. "
            "Verifica GOOGLE_SERVICE_ACCOUNT_FILE o utiliza GOOGLE_SERVICE_ACCOUNT_JSON(_B64)."
        )

    with path_obj.open("r", encoding="utf-8") as fh:
        info = json.load(fh)
    _log_sa_info("FILE", info)
    return _credentials_from_info(info)

from google.auth.transport.requests import Request

def get_sheets_client():
    creds = get_credentials()
    # Fuerza validación temprana del JWT y del token:
    try:
        creds.refresh(Request())
    except Exception as e:
        # Log explícito para identificar invalid_grant y su origen
        print(f"[GOOGLE_AUTH] Token refresh failed: {e}")
        raise
    return gspread.authorize(creds)


def get_drive_service():
    creds = get_credentials()
    try:
        creds.refresh(Request())
    except Exception as e:
        print(f"[GOOGLE_AUTH] Token refresh failed (drive): {e}")
        raise
    return build("drive", "v3", credentials=creds, cache_discovery=False)

