from enum import Enum

from core import ASSETS_DIR, DESKTOP_PATH, WEBCLACC_URL

# Cartella contenente file di supporto
class SupportFiles(Enum):
    APPROVATORI_CSV = ASSETS_DIR / "Approvatori.csv"
    SUBMIT_DATES_CSV = ASSETS_DIR / "2025-07-07_Clacc_submit_1_date_FY26.csv"
    VIEWSTATE_TXT = ASSETS_DIR / "viewstate.txt"

# Cartella Desktop
assert DESKTOP_PATH.stem == "Desktop", f"Il percorso '{DESKTOP_PATH}' non sembra essere il Desktop."

# Cartella con i progressi di ReadWeb.py
CLACC_CHECK_DIR = DESKTOP_PATH / "CLACC_Check"

# Numero di colonne esposte nella vista principale di WebCLACC
CLACC_EXPOSED_COLS = 70

# Dominio WebCLACC + endpoints
DOMAIN: str = WEBCLACC_URL
class WebCLACCEndpoints(Enum):
    FORM    = DOMAIN + "Modules/Monitoring/CheckApprovers.aspx"
    LOGIN   = DOMAIN + "Login.aspx"
    DEFAULT = DOMAIN + "DefaultPage.aspx"
    QUEST   = DOMAIN + "Modules/MyClacc/NewQuestionnaire_Compile.aspx"
