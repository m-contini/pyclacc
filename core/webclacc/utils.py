"""
Utility per il caricamento di file di supporto relativi a WebCLACC.
Include funzioni per la lettura dei flussi approvativi e delle date di sottomissione.
"""
import pandas as pd

from core import logger

from .const import SupportFiles

logging = logger.getLogger(__name__)

def load_approvers_tbl() -> pd.DataFrame:
    """
    Carica la tabella degli approvatori dal file CSV.
    La tabella viene indicizzata per tipo di flusso (Ante/Post 23/06/2025) e LMU.
    """
    path = SupportFiles.APPROVATORI_CSV.value

    try:
        return pd.read_csv(path, sep=';', index_col=['New/Old', 'LMU'])
    except (FileNotFoundError, PermissionError) as e:
        logging.error(path, 'non esistente o non accessibile.')
        raise e

def load_submit_dates() -> pd.Series:
    """
    Carica le date del primo invio dei CLACC.
    Restituisce una Serie indicizzata per ID_CLACC contenente oggetti datetime.
    """
    path = SupportFiles.SUBMIT_DATES_CSV.value

    try:
        return (
            # Dataframe con data di primo submit dei CLACC
            pd.read_csv(path, sep=';', parse_dates=['Prima data invio'], dayfirst=True)
            # Se un CLACC è duplicato, si mantiene la data di submit più vecchia (la prima)
            .sort_values('Prima data invio', ascending=True)
            .drop_duplicates('ID_CLACC', keep='first')
            .set_index('ID_CLACC')
            .loc[:, 'Prima data invio']
        )
    except (FileNotFoundError, ValueError) as e:
        raise e
