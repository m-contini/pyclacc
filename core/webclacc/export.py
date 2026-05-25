"""
Questo modulo gestisce l'esportazione dei dati da WebCLACC.
Si occupa dell'autenticazione, della navigazione tra i form e del parsing dei risultati di ricerca.
"""
from pathlib import Path
import re
from typing import Optional
from bs4 import BeautifulSoup
import requests
import pandas as pd
from datetime import datetime

from core import CURRENT_FY, OUTPUT_DIR, ASSETS_DIR, ENV_FILE, logger

from .const import CLACC_EXPOSED_COLS, SupportFiles, WebCLACCEndpoints
from .dtypes import ApproverCheckStatusType, ClaccStatusType
from core.exceptions import BadExtraction, NoCredentials

logging = logger

class DefaultParams:
    fiscal_year: int = CURRENT_FY
    approver_check_status: ApproverCheckStatusType = 'To check'
    status_clacc: ClaccStatusType = 'Approved'

class CheckStatusMap:
    All = -1
    To_check = 1
    checked = 2
    Under_Investigation = 3

class ClaccStatusMap:
    All = -1
    Draft = 1
    To_Approve = 2
    Approved_0 = 3
    Approved_1 = 4
    Approved_2 = 5
    Approved = 6
    Rejected = 7
    Overwritten = 9
    Overwritten_Approved = 10
    Proposal_Refused = 11

class ExportClacc:

    # All, To_check, checked, Under_Investigation
    check_status_map = {k.replace('_', ' '): v for k, v in CheckStatusMap.__dict__.items()}
    # All, Draft, Approved, ...
    clacc_status_map = {k.replace('_', ' '): v for k, v in ClaccStatusMap.__dict__.items()}

    def __init__(
        self,
        fiscal_year: int = DefaultParams.fiscal_year,
        approver_check_status: ApproverCheckStatusType = DefaultParams.approver_check_status,
        status_clacc: ClaccStatusType = DefaultParams.status_clacc,
    ) -> None:

        if fiscal_year == -1:
            logging.error(
                f"[ERROR] - fiscal_year non può essere -1. "
                "Per scaricare tutti gli anni, usare script dedicato. "
                f"Scegli un anno specifico (default: {DefaultParams.fiscal_year})."
            )
            raise ValueError

        if approver_check_status not in ApproverCheckStatusType.__args__:
            logging.error(
                f"[ERROR] - Approver Check Status deve essere uno di: "
                f"{ApproverCheckStatusType.__args__} ",
                f"non {approver_check_status}."
            )
            raise ValueError

        if status_clacc not in ClaccStatusType.__args__:
            logging.error(
                f"[ERROR] - Status CLACC deve essere uno di: "
                f"{ClaccStatusType.__args__} "
                f"non {status_clacc}."
            )
            raise ValueError

        self.fiscal_year = fiscal_year
        self.approver_check_status = approver_check_status
        self.status_clacc = status_clacc

        self.args: dict[str, int | str] = locals().copy()
        self.args.pop("self")

        self.dataframe = pd.DataFrame()

    def __len__(self) -> int:
        return len(self.dataframe)

    @property
    def _integer_args(self) -> dict[str, int]:
        """Mappa gli argomenti testuali in numeri"""
        return {
            "FiscalYear": self.fiscal_year,
            "ApproverCheckStatus": ExportClacc.check_status_map[self.approver_check_status],
            "StatusClacc": ExportClacc.clacc_status_map[self.status_clacc],
        }

    @staticmethod
    def auth() -> requests.Session:
        """
        Inizializza una sessione autenticata.
        Le credenziali vengono recuperate dal file .env.
        Gestisce inoltre il caricamento dei certificati SSL se presenti nella cartella assets.
        """
        from dotenv import load_dotenv
        import os
        from requests_ntlm import HttpNtlmAuth
        from urllib3 import disable_warnings
        from urllib3.exceptions import InsecureRequestWarning

        # Carica .env dalla root dir
        load_dotenv(ENV_FILE)

        # Credenziali NTLM
        usr = os.getenv("NTLM_USER", "") # r"dominio\utente"
        psw = os.getenv("NTLM_PASS", "")
        if not (usr or psw):
            logging.error("[ERROR] - Credenziali non fornite, impossibile proseguire.")
            raise NoCredentials

        # Inizializza sessione
        session = requests.Session()
        session.auth = HttpNtlmAuth(username=usr, password=psw)

        # Carica certificati SSL se presenti
        crt_files = list(ASSETS_DIR.glob("*.crt")) if ASSETS_DIR.exists() else []

        if not crt_files:
            session.verify = False
            disable_warnings(InsecureRequestWarning)
        else:
            session.verify = crt_files[0].as_posix()

        return session

    def download(self, directory: Optional[Path] = None) -> None:
        """
        Scarica i dati da WebCLACC effettuando una richiesta POST autenticata.
        I dati vengono poi parsati in un DataFrame e, se specificato, salvati in CSV.
        """
        try:
            response = self._post_request(WebCLACCEndpoints.FORM.value, **self._integer_args)
        except requests.RequestException:
            logging.error("[ERROR] - Problemi di connessione: attiva la VPN e/o verifica il certificato SSL.")
            raise

        if response.text == '0|error|500||':
            logging.error("[ERROR] - Il server ha risposto con errore 500 (form Ajax).")
            raise BadExtraction

        if not response.ok:
            logging.error(f"[ERROR] - Richiesta fallita: {response.status_code} ({response.url})")
            raise BadExtraction

        # Redirect non previste
        if response.history and not all(r.url == response.history[0].url for r in response.history):
            logging.error(f"[ERROR] - Comportamento di redirect anomalo:\n{response.history}")
            raise BadExtraction

        df = self._parse_response(response.text)

        # Nessun dato recuperato
        if df.empty:
            logging.error("[ERROR] - Parsing fallito: nessun dato valido trovato nella risposta.")
            raise BadExtraction

        # Assegnazione
        self.dataframe = df.set_index("ID_CLACC").fillna("")

        logging.info(
            f"[ExportClacc] Estrazione aggiornata al {datetime.now().strftime("%d/%m/%Y, %H:%M")}."
        )

        if directory is not None:
            self.save_to_csv(directory)

    def read_csv(self, directory: Path | None = None) -> None:
        """
        Carica l'ultimo file CSV salvato localmente che corrisponde ai parametri dell'istanza.
        Se non viene fornita una directory, utilizza quella predefinita.
        """
        if directory is None:
            directory = OUTPUT_DIR

        if not directory.is_dir():
            logging.error(f"La directory non esiste: {directory}")
            raise FileNotFoundError

        # Nome file CSV
        pattern = (
            f"*_{self.fiscal_year}"
            f"_{self.approver_check_status}_"
            f"{self.status_clacc}_WebCLACCExtract.csv"
        ).replace(" ", "_")

        # Lista di file aderenti al pattern
        matches = list(directory.glob(pattern))

        if not matches:
            logging.error(
                f"Nessun CSV trovato in {directory} con pattern: {pattern}"
            )
            raise FileNotFoundError

        # Ordina per data ultima modifica
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        # Prende il file più recente
        file_path = matches[0]

        updated_at = self._updated_at(file_path)
        logging.info(f"[ExportClacc] Estrazione {file_path.name} aggiornata al {updated_at}")

        try:
            # Lettura file
            df = pd.read_csv(file_path, index_col='ID_CLACC', sep=';', encoding='utf-8', keep_default_na=False)
        except (FileNotFoundError, pd.errors.ParserError) as e:
            logging.error((f"Errore nella lettura del CSV {file_path.name}: {e}"))
            raise BadExtraction

        # Assegnazione
        self.dataframe = df.fillna("")

    def save_to_csv(self, directory: Path) -> None:
        """
        Salva il DataFrame corrente in un file CSV nella directory specificata.
        Il nome del file include il timestamp, Fiscal Year e stato del CLACC.
        """
        directory.mkdir(parents=True, exist_ok=True)

        # Parametri
        fy = self.fiscal_year
        appr_check_status = self.approver_check_status.replace(" ", "_")
        status_clacc = self.status_clacc.replace(" ", "_")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

        # Nome file CSV
        fname = f"{timestamp}_{fy}_{appr_check_status}_{status_clacc}_WebCLACCExtract.csv"
        path = directory / fname

        # Salvataggio
        self.dataframe.to_csv(path, sep=';', encoding='utf-8', index=True) # pyright: ignore[reportOptionalMemberAccess]
        logging.info(f"[CSV] - {len(self):,} righe salvate: {path.relative_to(directory.parent)}")

    @staticmethod
    def _post_request(url: str, **kwargs: int) -> requests.Response:
        """
        Esegue una richiesta POST a WebCLACC per recuperare i dati dei CLACC.
        Utilizza il viewstate pre-salvato e i parametri di ricerca forniti.
        """
        # Lettura viewstate
        with open(SupportFiles.VIEWSTATE_TXT.value, 'r', encoding='utf-8') as f:
            viewstate = f.read()

        headers = {
            'Accept': '*/*',
            'Accept-Language': 'it,en-US;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://clacc.deloitte.it',
            'Referer': 'https://clacc.deloitte.it/Modules/Monitoring/CheckApprovers.aspx',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/138.0.0.0 Safari/537.36'
            ),
            'X-MicrosoftAjax': 'Delta=true',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

        # Form base
        data: dict[str, str] = {
            'ctl00$ContentPlaceHolder1$ScriptManager1':
                'ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|'
                'ctl00$ContentPlaceHolder1$Button_Search',
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            "__VIEWSTATE": viewstate,
            '__VIEWSTATEGENERATOR': '5F3335C3',
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            'ctl00$ContentPlaceHolder1$DropDownList_Questionnaire': '1',
            'ctl00$ContentPlaceHolder1$DropDownList_FiscalYear': str(kwargs['FiscalYear'])[-2:],
            'ctl00$ContentPlaceHolder1$DropDownList_Manager': '-1',
            'ctl00$ContentPlaceHolder1$DropDownList_FinalRisk': '-1',
            'ctl00$ContentPlaceHolder1$DropDownList_ApproverCheckStatus': str(kwargs['ApproverCheckStatus']),
            'ctl00$ContentPlaceHolder1$DropDownList_CLACCStatus': str(kwargs['StatusClacc']),
            'ctl00$ContentPlaceHolder1$TextBox_Client': '',
            'ctl00$ContentPlaceHolder1$TextBox_IdClacc': '',
            'ctl00$ContentPlaceHolder1$DropDownList_ChooseApprover': '-1',
            'ctl00$ContentPlaceHolder1$DropDownList_QuestionnairesPerPage': '-1',
            '__ASYNCPOST': 'true',
            'ctl00$ContentPlaceHolder1$Button_Search': 'Search',
        }

        try:
            # Risposta HTTP: ricerca su WebCLACC
            session = ExportClacc.auth()
            response = session.post(url, headers=headers, data=data)
            response.raise_for_status()
            return response
        except (requests.RequestException, Exception):
            logging.error(f"[ERROR] - Errore durante la richiesta POST a WebCLACC. Verifica la connessione VPN.")
            raise

    def _parse_response(self, raw_html: str) -> pd.DataFrame:
        """
        Parsa la risposta HTML proveniente da WebCLACC per estrarre la tabella dei risultati.
        Restituisce un DataFrame contenente i CLACC trovati.
        """
        soup = BeautifulSoup(raw_html, "html.parser")

        # Campi
        cols = []
        for tr in soup.select("tr"):
            cols = [th.get_text(strip=True) for th in tr.find_all("th")[1:]]
            if cols and len(cols) == CLACC_EXPOSED_COLS:
                break

        if not cols:
            logging.error(
                "[ERROR] - Nessuna intestazione di tabella trovata nell'HTML. "
                "Estrazione vuota."
            )
            raise BadExtraction

        if not 'ID_CLACC' in cols:
            logging.error("[ERROR] - Nessuna colonna di nome `ID_CLACC` trovata")
            raise BadExtraction

        # Righe
        rows: list[list[str]] = []
        for tr in soup.select("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")[1:]]
            if cells and len(cells) == CLACC_EXPOSED_COLS:
                rows.append(cells)

        return pd.DataFrame(rows, columns=cols).astype({
            'ID_CLACC': 'int',
            'Client Code': 'int',
            'Fiscal Year': 'int',
        }, errors='ignore')

    @staticmethod
    def _updated_at(path: Path) -> Optional[datetime]:

        # Es. '2026-05-24_02:23'
        match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2})', path.stem)
        if match is None:
            return None

        date_str = match.group(1)
        try:
            # Converte nuovamente in datetime
            return datetime.strptime(date_str, "%Y-%m-%d_%H-%M")
        except ValueError:
            return None
