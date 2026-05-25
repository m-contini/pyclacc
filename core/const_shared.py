from typing import Any

import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

# Caricamento configurazioni da YAML
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        _config: dict[str, Any] = yaml.safe_load(f) or {}
except Exception:
    _config = {}

CURRENT_FY = _config.get("CURRENT_FY", 2026)
LOGGING_FILE = ROOT / _config.get("LOGGING_FILE", "pyclacc.log")
DESKTOP_PATH = Path(_config.get("DESKTOP_PATH", ""))

OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
ENV_FILE = ROOT / _config.get("ENV_FILE", ".env")

DFORCE1_URL = _config.get("DFORCE1_URL", "https://dforce1.my.salesforce.com/")
WEBCLACC_URL = _config.get("WEBCLACC_URL", "https://clacc.deloitte.it/")
LEGAL_ENTITY = _config.get("LEGAL_ENTITY", "DELOITTE & TOUCHE SPA")
AUDIT_BUSINESS_LEADER = _config.get("AUDIT_BUSINESS_LEADER", "BRAMBILLA VALERIA")
OLD_AUDIT_RISK_LEADERS = set(_config.get("OLD_AUDIT_RISK_LEADERS", []))
NEW_AUDIT_RISK_LEADERS = set(_config.get("NEW_AUDIT_RISK_LEADERS", []))
EQUIVALENT_LMU = _config.get("EQUIVALENT_LMU", {})
