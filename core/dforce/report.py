"""
Questo modulo gestisce lo scaricamento e la lettura di report personalizzati da DForce1 (Salesforce).
Utilizza le credenziali della sessione per effettuare una richiesta di esportazione CSV.
"""
from datetime import datetime
from io import StringIO
import json
import re
from bs4 import BeautifulSoup
import pandas as pd
from typing import Optional
from pathlib import Path

from core import SessionExpired, OUTPUT_DIR, DFORCE1_URL, logger

from .const import SupportFiles
from .session import DFSession

logging = logger.getLogger(__name__)

class ReportDForce(DFSession):
    """
    Istanza per scaricare in CSV un certo report di DForce1 con un dato id.
    """

    # Colonne da convertire in tipo int/Int64
    _integer_columns = [
        'Opportunity Number',
        'Codice CLACC',
        'Account Name (End Client): DST Id',
        'Opportunity Fiscal Year',
        'Risk Fiscal Year',
        'DRMS ID'
    ]

    def __init__(self, report_id: str) -> None:
        # Inizializza la sessione base
        super().__init__()

        self._id: str = report_id
        self.dataframe = pd.DataFrame()
        self._headers = self._read_headers()
        self._payload = self._read_payload()

    def __len__(self) -> int:
        return len(self.dataframe)

    def _read_headers(self) -> dict[str, str]:
        """Carica gli header HTTP necessari per le richieste a Salesforce"""
        try:
            with open(SupportFiles.DFORCE1_HEADERS_JSON.value, 'r', encoding='utf-8') as f:
                return json.load(f)
        except RuntimeError:
            return {}

    def _read_payload(self) -> dict[str, str]:
        """Carica il payload della richiesta necessario al download"""
        try:
            with open(SupportFiles.DFORCE1_PAYLOADS_JSON.value, 'r', encoding='utf-8') as f:
                return json.load(f)[self._id]
        except (KeyError, RuntimeError):
            return {'cust_name': 'N/A', 'cust_desc': 'N/A'}

    @property
    def name(self) -> str:
        # Nome del report
        return self._payload['cust_name']

    @property
    def description(self) -> str:
        # Descrizione testuale del report
        return self._payload['cust_desc']

    def _run_report(self):
        """
        Esegue il workflow di esportazione su Salesforce:
        1. Richiesta della pagina di esecuzione. 2. Richiesta di esportazione CSV. 3. Parsing del risultato.
        """
        # Carica il report
        response = self.session.post(
            url=DFORCE1_URL + self._id,
            headers=self._headers,
            data=self._payload | {
                'break0': '',
                'csvsetup': 'Export Details',
                'runPageAction': '',
                'eirb': 'eirb',
                'op': 'op',
                'nav': '',
                'deletefilter': '',
                'deleteObjfilter': ''
            }
        )

        soup = BeautifulSoup(response.text[:500], 'html.parser')
        try:
            self.name in soup.find('title').get_text(strip=True) # type: ignore
        except (KeyError, AttributeError):
            if self.retries == 0:
                raise SessionExpired
            raise KeyError("Pagina finale malformata")

        # Download del report
        response = self.session.post(
            url=DFORCE1_URL + self._id,
            headers=self._headers,
            data=self._payload | {
                'enc': 'UTF-8',
                'xf': 'localecsv',
                'export': 'Export'
            }
        )

        def _is_valid_response(text: str) -> bool:
            text = text[:100]
            return (';' in text) != ('<table>' in text)

        if not _is_valid_response(response.text):
            raise AttributeError("Rivedere payload importato")

        # Lettura del report
        df = pd.read_csv(
            filepath_or_buffer=StringIO(response.text),
            sep=';',
            encoding='utf-8',
            engine='python'
        ).dropna(subset='Opportunity Number')

        # Rimozione spazi da DRMS ID
        if 'DRMS ID' in df.columns:
            df['DRMS ID'] = df['DRMS ID'].replace(' ', '')

        # Conversione tipi
        for col in self._integer_columns:
            if col not in df.columns:
                continue
            df[col] = df[col].astype('Int64', errors='ignore')

        return df

    def download(self, directory: Optional[Path] = None) -> None:
        """Esegue il download del report e opzionalmente lo salva su disco in formato CSV."""

        args = locals().copy()
        del args['self']

        try:
            # Download dati da DForce1
            self.dataframe = self._run_report()
        except SessionExpired as e:
            logging.error(e)
            self.retries = 1
            self.refresh_session()
            return self.download(**args)
        except (KeyError, AttributeError) as e:
            logging.error(e)
            raise RuntimeError("Errore durante download") from e

        logging.info(f"[ReportDForce] Estrazione aggiornata al {datetime.now().strftime('%d/%m/%Y, %H:%M')}")

        # Salvataggio
        if directory:
            self.to_csv(directory)

    def to_csv(self, dir: Path) -> None:
        """Esporta il DataFrame corrente in un file CSV con timestamp e ID report."""

        dir.mkdir(parents=True, exist_ok=True)

        # Nome file CSV
        fpath = dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M')}_{self._id}_DForce1Report.csv"
        
        # Salvataggio
        self.dataframe.to_csv(fpath, sep=';', encoding='utf-8', index=False)
        logging.info(f"[CSV] - {len(self):,} righe salvate: {fpath.relative_to(dir.parent)}")

    def read_csv(self, directory: Optional[Path] = None) -> None:

        if directory is None:
            directory = OUTPUT_DIR

        try:
            if not directory.is_dir():
                raise FileNotFoundError(f"Cartella '{directory}' inesistente.")

            # Lista di file csv già salvati in passato
            csv_list = sorted(list(directory.glob(f'*{self._id}*.csv')), key=lambda x: x.stat().st_mtime)
            if not csv_list:
                raise IndexError(f"Nessuna estrazione con id '{self._id}' trovata in '{directory}'.")

            # Ultimo file csv
            latest_path = csv_list[-1]
            match = re.search(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}', latest_path.stem)

            if match is None:
                raise ValueError(f"Nome file '{latest_path.name}' non contiene data valida.")

            updated_at = datetime.strptime(match.group(), "%Y-%m-%d_%H-%M")
            logging.info(f"[ReportDForce] Estrazione {latest_path.name} aggiornata al {updated_at.strftime('%d/%m/%Y, %H:%M')}")

            # Lettura file csv
            df = pd.read_csv(latest_path, sep=';', encoding='utf-8') # pyright: ignore[reportUnknownMemberType]
            for col in self._integer_columns:
                if col not in df.columns:
                    continue
                df[col] = df[col].astype('Int64', errors='ignore')

            # Assegnazione
            self.dataframe = df
        except (FileNotFoundError, IndexError) as e:
            logging.error(e)
            raise RuntimeError from e
