"""
Questo modulo contiene la classe DForce1 e il relativo Parser per l'estrazione dei dati.
"""
from typing import Any, Optional
from bs4 import BeautifulSoup, Tag
import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from core import Clacc, logger
from core.exceptions import SessionExpired

from .const import LEGAL_ENTITY, DFORCE1_URL
from .dtypes import AccountType, RiskType, OpportunityType, DFSearchResults, SummaryType
from .session import DFSession

logging = logger.getLogger(__name__)

class Parser:

    @staticmethod
    def _appendable(df: pd.DataFrame) -> bool:
        """
        Verifica se il DataFrame estratto è una delle tabelle Salesforce di interesse
        (Opportunities, Risks o Accounts) basandosi sulle intestazioni delle colonne.
        """
        for col in df.columns:
            if col == 'Action':
                df.drop(col, axis=1, inplace=True)
                continue

            if col == df.columns[0]:  # prima colonna → determinazione tipo
                if col not in DForce1.labels:
                    return False
                df.index.name = DForce1.labels[col]

            if col in ['Opportunity Number', 'Total Fees (â‚¬)', 'Potential Amount (â‚¬)', 'DST Id', 'Fiscal Year']:
                # Nota: 'â‚¬' viene utilizzato per gestire l'encoding ISO-8859-1 
                # spesso restituito dai sistemi legacy di Salesforce in formato HTML.
                try:
                    df[col] = df[col].astype('int64')
                    df.sort_values(by='Fiscal Year', ascending=False, inplace=True)
                except Exception:
                    pass

        return True

    @staticmethod
    def _clean_tag_text(tr: Tag) -> str:
        """Pulisce il testo contenuto in un tag HTML rimuovendo spazi non standard e simboli valuta."""
        raw: str = tr.get_text()
        return raw.replace("\xa0", " ").replace("â‚¬", "").strip()

    @staticmethod
    def get_dataframes(html: str) -> list[pd.DataFrame]:
        """
        Estrae i DataFrame dalle tabelle HTML presenti nella pagina di ricerca Salesforce.
        Filtra solo le tabelle che corrispondono ai tipi definiti in DForce1.labels.
        """

        soup = BeautifulSoup(html, 'html.parser')
        dfs: list[pd.DataFrame] = []

        for divtbl in soup.find_all('div', {'class': 'pbBody'}):
            if not divtbl.get('id'):
                continue

            rows: list[list[str]] = []
            for tr in divtbl.find_all('tr'):
                cells = list(map(Parser._clean_tag_text, tr.find_all(['th', 'td'])))
                if cells:
                    rows.append(cells)

            if len(rows) < 2:
                continue

            df = pd.DataFrame(rows[1:], columns=rows[0]).astype('int', errors='ignore')
            if not Parser._appendable(df):
                continue

            dfs.append(df)

        return dfs

class DForce1(DFSession):
    """
    Classe che rappresenta DForce1 (Salesforce).
    Si occupa di interrogare DForce1 tramite ricerca testuale (per Client Name o Client Code)
    e di validare la coerenza dei dati rispetto a un oggetto Clacc.
    """

    labels: dict[str, str] = {
        'Opportunity Title':                'Opportunities',
        'Risk Name':                        'Risks',
        'Corporate Name (Ragione Sociale)': 'Accounts',
    }

    def __init__(self, clacc_object: Clacc, session: Optional[requests.Session] = None) -> None:
        super().__init__()

        if session is None:
            # Inizializza la sessione
            adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
            self.session.mount("https://", adapter)
            self.refresh_session()
        else:
            self.session = session

        self.clacc: Clacc = clacc_object

        # Ricerca su DForce1 tramite Client Name e Client Code
        self.dicts: DFSearchResults = self.get_websearch_results()
        # L'assenza di risultati fa supporre che il Clacc vada messo "Under Investigation"
        self._under_inv = not self.dicts

        # Anagrafica cliente
        self.client_name, self.dst_id, self.lcsp = self._fetch_accounts(self.dicts.Accounts)
        self.risks: RiskType = self._fetch_risks(self.dicts.Risks)
        self.opportunities: OpportunityType = self._fetch_opportunities(self.dicts.Opportunities)

    @property
    def summary(self) -> SummaryType:
        """
        Restituisce un dizionario di riepilogo delle proprietà del CLACC
        rispetto a quelle di DForce1.
        """
        return {
            'Has Opportunity': self.has_opportunities,
            'Has Risk': self.has_risks,
            'Same Name': self._same_name,
            'Same Code': self._same_code,
            'New Client': self._new_client,
            'Same LCSP': self._same_lcsp,
            'IT LCSP': self.lcsp,
            'Eng. Partner': self.clacc.eng_prt,
            'Pipeline Stages': ', '.join(self._pipeline_stages) or '',
            'Under Inv.': self._under_inv,
            'Lost': self._lost,
        }

    @property
    def printable_table(self) -> list[tuple[str, Any]]:
        """
        Restituisce summary come lista di records.
        Utile per la stampa tramite tabulate.
        """
        tbl = self.summary.copy()
        tbl['New Client'] = tbl['New Client'] == self.clacc.is_new_client
        return list(tbl.items())

    def get_websearch_results(self) -> DFSearchResults:
        """
        Esegue una ricerca globale su Salesforce utilizzando sia il Client Code che il Client Name.
        Restituisce un oggetto DFSearchResults contenente i DataFrame per Accounts, Opportunities e Risks.
        """
        try:
            if self.retries > 0:
                logging.info("RETRYING...")
            result: dict[str, pd.DataFrame] = {
                # Risultati di ricerca per Client Code
                **self._search_by_keyword(self.clacc.client_code).to_dict(),
                # Risultati di ricerca per Client Name
                **self._search_by_keyword(self.clacc.client_name).to_dict()
            }
            # Ordina le chiavi alfabeticamente (Accounts, Opportunities, Risks)
            # prima di restituire i risultati
            return DFSearchResults(**{k: result[k] for k in sorted(result.keys())})

        except SessionExpired:
            self.retries = 1
            self.refresh_session()
            return self.get_websearch_results()

        except requests.ConnectionError:
            input("\033[31m\nAttivare connessione internet e VPN e premere Enter...\n\033[0m")
            return self.get_websearch_results()

    def _search_by_keyword(self, key: int | str) -> DFSearchResults:
        """
        Esegue la chiamata GET ai servizi di ricerca di Salesforce.
        Parsa la risposta per identificare tabelle di Accounts, Risks o Opportunities.
        """
        params: dict[str, Any] = {
            'searchType': '2',
            'sen': ['001', 'a0T', '500', '005', 'a1W', 'a0X', '00O'],
            'str': f'"{key}"'
        }

        resp = self.session.get(
            url= DFORCE1_URL + "_ui/search/ui/UnifiedSearchResults",
            params=params
        )

        df_list = Parser.get_dataframes(resp.text)

        results = DFSearchResults()

        # Caso sessione scaduta
        if not df_list and 'No matches found' not in resp.text:
            if self.retries == 0:
                raise SessionExpired
            return results

        # Filtra DataFrame validi
        for df in df_list:
            name = str(df.index.name)
            if name in results.__slots__:
                setattr(results, name, df)

        return results

    def _fetch_accounts(self, df: pd.DataFrame) -> AccountType:
        """
        Recupera dai risultati di ricerca DForce1 gli Accounts trovati
        """
        try:
            vals = df.loc[
                df['Status'].isin(['Client', 'Prospect']),
                ['Corporate Name (Ragione Sociale)', 'DST Id', 'IT LCSP']
            ]
            if vals.empty:
                raise ValueError

            rag_soc, dst_id, lcsp = vals.iloc[0]
            return (
                str(rag_soc).strip(),
                int(dst_id),
                str(lcsp).replace('N/a N/a', '')
            )

        except (KeyError, ValueError):
            # Se non ci sono Accounts, perciò il cliente non è censito,
            # allora il CLACC è potenzialmente da mettere Under Investigation
            self._under_inv = True
            return (None, None, None)

    def _fetch_risks(self, df: pd.DataFrame) -> RiskType:
        """
        Recupera dai risultati di ricerca DForce1 i Risks trovati
        """
        try:
            vals = df.loc[df['Opportunity Final Account'] == self.client_name]
            vals.set_index('Fiscal Year', inplace=True)
            self.has_risks = True
            return vals.to_dict(orient='records')

        except KeyError:
            # Se non vengono trovati Risks
            self.has_risks = False
            return []

    def _fetch_opportunities(self, df: pd.DataFrame) -> OpportunityType:
        """
        Recupera dai risultati di ricerca DForce1 le Opportunities trovate
        """
        try:
            ok: pd.DataFrame = df.loc[
                (df['Account Name (End Client)'] == self.client_name) &
                (df['Deloitte Legal Entity'] == LEGAL_ENTITY)
            ]

            ppline = ok.loc[
                ok['Fiscal Year'] == self.clacc.fy, 'Pipeline Stage'
            ]
            if ppline.empty:
                raise KeyError

            stages = ppline.values if not isinstance(ppline, str) else [ppline]
            self._pipeline_stages = sorted(set(stages), reverse=True)

            # Under Investigation?
            ref = {'Won', 'Proposal Submitted', 'Identified', 'Lost', 'Abandoned'}
            self._under_inv = not bool(ref.intersection(self._pipeline_stages))

            # Lost?
            self._lost = bool({'Lost', 'Abandoned'}.intersection(self._pipeline_stages))

            self.has_opportunities = True
            return ok.to_dict(orient='records')

        except KeyError:
            # Se non vengono trovate Opportunities
            self._pipeline_stages = []
            self._under_inv = True
            self._lost = False
            self.has_opportunities = False
            return []

    @property
    def _same_name(self) -> bool:
        """Il nome coincide col Client Name del CLACC?"""
        if self.client_name is None:
            return False

        def _norm(x: str) -> str:
            parts = x.lower().strip().split()
            if len(parts) > 1:
                parts = parts[:-1]
            return ' '.join(parts)

        return _norm(self.client_name) == _norm(self.clacc.client_name)

    @property
    def _same_code(self) -> bool:
        """Il nome coincide col Client Code del CLACC?"""
        if self.dst_id is None:
            return False

        return self.dst_id == self.clacc.client_code

    @property
    def _same_lcsp(self) -> bool:
        """IT LCSP coincide con il Partner del CLACC?"""
        if self.lcsp is None:
            return False

        def _norm(x: str) -> str:
            return ' '.join(sorted(word.lower() for word in x.split()))

        return bool(_norm(self.lcsp) == _norm(self.clacc.eng_prt))

    @property
    def _new_client(self) -> bool:
        """Risulta essere New Client secondo DF1?"""
        try:
            fy_risks = self.dicts.Risks['Fiscal Year'].tolist()
            fy_opps  = self.dicts.Opportunities['Fiscal Year'].tolist()
            prev_fy  = self.clacc.fy - 1

            return any((
                prev_fy not in (fy_risks + fy_opps),
                not self._same_code,
                not self.risks and not self.opportunities,
            ))
        except KeyError:
            return True
