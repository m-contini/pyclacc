from enum import Enum

from core import (
    ASSETS_DIR,
    DFORCE1_URL as _DFORCE1_URL,
    LEGAL_ENTITY as _LEGAL_ENTITY
)

# Cartella contenente file di supporto
class SupportFiles(Enum):
    DFORCE1_PAYLOADS_JSON = ASSETS_DIR / "dforce1_payloads.json"
    DFORCE1_HEADERS_JSON = ASSETS_DIR / "dforce1_headers.json"
    DFORCE1_COOKIES_JSON = ASSETS_DIR / "dforce1_cookies.json"

# Dominio Salesforce
DFORCE1_URL: str = _DFORCE1_URL

# Per scremare i risultati evitando le altre ragioni sociali
LEGAL_ENTITY: str = _LEGAL_ENTITY
