"""
Modulo per la gestione dei file di input/output della sessione di screening.
Gestisce il caricamento di file Excel esistenti, il salvataggio dei progressi
e si interfaccia con i dati scaricati da WebCLACC e DForce1.
"""
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
import pandas as pd

from core import logger

from .dforce import ReportDForce
from .webclacc import ExportClacc
from .webclacc.const import CLACC_CHECK_DIR

logging = logger.getLogger(__name__)

class Explorer:
    """
    Gestisce il caricamento e il salvataggio dei dati per la sessione di screening.
    Permette di riprendere il lavoro da un file Excel esistente o di inizializzare
    una nuova sessione scaricando i dati aggiornati.
    """

    clacc_check_dir = CLACC_CHECK_DIR

    def __init__(self, fiscal_year: int) -> None:
        try:
            self.clacc_check_dir.mkdir(exist_ok=True, parents=True)
        except PermissionError:
            logging.error(f"Permesso negato sulla cartella {self.clacc_check_dir}. Verificare i permessi di scrittura.")
            raise

        self.fiscal_year: int = fiscal_year

        # File di input (XLSX) da cui leggere
        try:
            self.input_file: Path | None = sorted(
                self.clacc_check_dir.rglob(f'*{self._fname_pattern}'), reverse=True
            )[0]
        except IndexError:
            self.input_file = None

        # File di output (XLSX) da salvare
        self.output_file: Optional[Path] = None

        # Timestamp
        self.date, self.time = datetime.now().strftime("%Y-%m-%d %H-%M").split()

    @property
    def _fname_pattern(self) -> str:
        """Parte terminale del nome del file (dipende dal fiscal year)"""
        return f"FY{self.fiscal_year}_CLACC_Check.xlsx"

    def save_progress(self, df: pd.DataFrame) -> None:
        """
        Salva lo stato attuale della sessione di screening in un file XLSX.
        Crea una sottocartella basata sulla data corrente all'interno della directory di check.
        """

        # Nome file XLSX
        output_dir = self.clacc_check_dir / self.date
        output_dir.mkdir(exist_ok=True, parents=True)
        # Es. "C:\{output_dir}\2026-05-22\2026-05-22_18-09_FY2027_CLACC_Check.xlsx"
        output_file: Path = output_dir / '_'.join((self.date, self.time, self._fname_pattern))

        # Salvataggio
        df.to_excel(output_file, sheet_name=output_file.stem[:31], index=False) # pyright: ignore[reportUnknownMemberType]
        logging.info(f'[CHECKPOINT] Progressi salvati in XLSX: {output_file.parent}')
        self.output_file = output_file

    @staticmethod
    def clean_str(s: Any) -> str:
        """Rimuove caratteri di controllo (come _x000D_) dalle stringhe caricate da Excel."""
        if not isinstance(s, str):
            return s
        return s.replace('_x000D_', '').strip()

    @staticmethod
    def _get_input_dataframe(file: Path):
        """
        Legge un file Excel esistente e ne restituisce il contenuto come DataFrame.
        Formatta le date e pulisce le stringhe dai caratteri di controllo.
        """

        df = pd.read_excel(file, sheet_name=0, index_col='ID_CLACC', engine='openpyxl') # pyright: ignore[reportUnknownMemberType]

        df['Year End Date'] = pd.to_datetime(df['Year End Date'], dayfirst=True, errors='coerce').dt.strftime('%d/%m/%Y')

        # Rimuove la sequenza testuale _x000D_ (carriage return \r) da tutte le celle stringa
        df = df.map(Explorer.clean_str)

        logging.info(f"File XLSX caricato: {file.name}")
        return df

    @staticmethod
    def load_dataframe(obj: ExportClacc | ReportDForce, file: Optional[Path] = None) -> None:
        """
        Carica i dati nel DataFrame dell'oggetto fornito (ExportClacc o ReportDForce).
        Se viene passato un file XLSX, i dati vengono letti da lì, altrimenti si tenta
        la lettura dall'ultimo CSV disponibile o si avvia un nuovo download.
        """
        if file:
            try:
                # Setta l'attributo dataframe di ExportClacc o ReportDForce
                # leggendo i dati da file XLSX
                obj.dataframe = Explorer._get_input_dataframe(file)
                return
            except PermissionError:
                # Se il file risulta aperto, propone di chiuderlo e ripete.
                input(f"File '{file.name}' aperto in Excel. Chiuderlo e premere Enter: ")
                return Explorer.load_dataframe(obj, file)
        try:
            # Lettura da CSV
            return obj.read_csv()
        except (FileNotFoundError, IndexError) as e:
            logging.error(f'Errore: {str(e)}')
            return obj.download()
