"""
Modulo per l'elaborazione dei dati di una singola riga (CLACC).
Gestisce il recupero delle informazioni da DForce1 e la preparazione
degli oggetti per la visualizzazione.
"""
from io import StringIO
import requests
from bs4 import BeautifulSoup
import pandas as pd
from typing import Any
import re

from tabulate import tabulate

from core.clacc_workflow import ClaccWorkflow
from core.colours import *
from core.dforce import DFORCE1_URL, DForce1, LEGAL_ENTITY
from core.webclacc import Clacc, load_approvers_tbl, load_submit_dates

from .renderer import ClaccRowRenderer

class RowProcessor:
    """
    Classe che si occupa di recuperare i dati (scraping da Salesforce)
    e gestire lo stato del singolo CLACC.

    Non stampa nulla, ma prepara i dati per la UI.
    """

    submit_dates: pd.Series = load_submit_dates()
    approvers_tbl: pd.DataFrame = load_approvers_tbl()

    def __init__(self, session: requests.Session, row: pd.Series) -> None:
        self.session = session
        
        # UI
        self.ui = ClaccRowRenderer(row)
        
        # Il CLACC è stato già mandato in draft?
        self.sent_back_in_draft: bool = row['Sent Back In Draft'].strip().lower() == 'yes'

        # CLACC
        self.clacc_obj = Clacc(
            clacc_id=row['ID_CLACC'],
            row=row,
            first_submit_ser=RowProcessor.submit_dates,
            approvers_df=RowProcessor.approvers_tbl
        )

        # DForce1
        self.dforce_obj = DForce1(self.clacc_obj)

    def render(self, opportunity_risk_map: pd.DataFrame, fiscal_year: int) -> None:
        """
        Coordina il rendering a terminale di tutte le informazioni relative al CLACC.
        Visualizza i dati del questionario, le tabelle di validazione, i dettagli
        Salesforce (Opportunity e Risk) e i risultati della ricerca globale.
        """

        # Rendering del questionario CLACC
        print(self.ui.render_main_table())
        # Rendering esito CLACC summary (table)
        print(self.ui.render_validation_table(self.clacc_obj))
        # Rendering esito DForce1 summary (table)
        print(self.ui.render_validation_table(self.dforce_obj))

        if self.clacc_obj.clacc_id in opportunity_risk_map.index:
            opp_id, risk_id = opportunity_risk_map.loc[self.clacc_obj.clacc_id]

            # Rendering dettaglio Opportunity
            self.ui.print_dforce_table(self._fetch_opportunity(str(opp_id), fiscal_year), table_kind='Opportunity')
            # Rendering dettaglio Risk
            self.ui.print_dforce_table(self._fetch_risk(str(risk_id), fiscal_year), table_kind='Risk')

        # Rendering risultati di ricerca
        dforce_summary = self.ui.build_dforce_summary_tables(self.dforce_obj, fiscal_year)
        for name, data in dforce_summary.items():
            print(f"\n=== {name.upper()} ===")
            print(tabulate(data.to_dict(orient='records'), headers='keys', tablefmt='psql', showindex=False))

        # Link di ricerca su Salesforce (Client Name)
        print(self.ui.build_salesforce_link(self.clacc_obj.client_name))
        # Link di ricerca su Salesforce (ID_CLACC)
        print(self.ui.build_salesforce_link(self.clacc_obj.clacc_id))

        # Copia ID_CLACC negli appunti
        self._clacc_to_clipboard()
        print(f"\n{CYAN}(ID_CLACC copiato negli appunti){RESET}\n")

        # Flow speciale
        if self.sent_back_in_draft:
            print(f"{YELLOW}⚠️  Attenzione: CLACC già inviato in Draft:{RESET}\n")
            button = ClaccWorkflow(self.clacc_obj.clacc_id)
            button.preload_search_result()
            approvers_tab = button.fetch_approvers_tab()
            if approvers_tab.empty:
                print(f'{self.clacc_obj.clacc_id} - Tab "Approvers" non trovata...')
                return
            print(tabulate(approvers_tab.map(ClaccRowRenderer.wrap_text).to_dict(orient='records'), tablefmt='grid'))


    def _clacc_to_clipboard(self) -> None:
        """Copia ID_CLACC negli appunti."""
        pd.Series([self.clacc_obj.clacc_id]).to_clipboard(index=False, header=False)

    def _pb_body_map(self, opportunity_id: str) -> dict[str, str]:
        """Mappa gli ID dei div HTML di Salesforce ai nomi delle tabelle logiche."""
        return {
            f"{opportunity_id}_00Nw0000008Op5P_body": "Opportunity Team Members",
            f"{opportunity_id}_00Nw0000008Op5O_body": "Opportunity Line Items",
            # f"{opportunity_id}_00N6900000KfbHn_body": "Budget Groups",
            # f"{opportunity_id}_00N6900000KfbJN_body": "Jobs",
            # f"{opportunity_id}_00N6900000KfbLn_body": "Risks",
        }

    @staticmethod
    def _format_name(fullname: Any) -> Any:
        """Formatta 'Cognome, Nome' in 'NOME COGNOME'"""
        if not isinstance(fullname, str):
            return fullname
        return ' '.join(fullname.split(', ')).upper()

    def _fetch_opportunity(self, opportunity_id: str, fiscal_year: int) -> dict[str, pd.DataFrame]:
        """
        Recupera i dettagli di un'opportunità specifica da Salesforce tramite scraping HTML.
        Estrae i membri del team e le Line Items, filtrando per l'anno fiscale corrente.
        """

        # Pagina web dell'opportunità (da scrapare)
        response = self.session.get(DFORCE1_URL + opportunity_id)

        # Pattern per individuare elementi rilevanti (tabelle)
        pattern = r"<!-- Begin (?:Related)?ListElement -->(.*?)<!-- End (?:Related)?ListElement -->"
        matches = re.findall(pattern, response.text, re.DOTALL)
        if not matches:
            print(f"\n{YELLOW}Nessun blocco HTML trovato per {MAGENTA}{opportunity_id}{RESET}")
            return {}

        pbBodyMap = self._pb_body_map(opportunity_id)
        matching_tables: dict[str, pd.DataFrame] = {}
        for block in matches:
            if opportunity_id not in block:
                continue

            soup_block = BeautifulSoup(block, "lxml")
            div = soup_block.find("div", class_="pbBody")
            if not div:
                continue

            div_id: str = str(div.get("id") or "")
            tbl_name: str = pbBodyMap.get(str(div_id), "")
            if not tbl_name:
                continue

            try:
                # Tabelle trovate nella pagina dell'opportunità
                tables: list[pd.DataFrame] = pd.read_html(StringIO(str(div)))
            except ValueError:
                print(f"Nessuna tabella trovata in {div_id}")
                continue

            for table in tables:
                if 'Action' not in table.columns:
                    continue
                table = table.drop(columns=["Action"])
                matching_tables[tbl_name] = table

        # Colonne da rimuovere (irrilevanti)
        to_drop = [
            # Opportunity Team Members
            "Opportunity Team Member: Opportunity Team Member Name", "Percentage (%)", "Description",
                "To Delete", "Opportunity Team Member: Last Modified By", "Opportunity Team Member: Last Modified Date",
            # Opportunity Line Items
            "Opportunity Line Item Name", "Deloitte Legal Entity", "Continua Next Year (%)"
        ]
        dfs: dict[str, pd.DataFrame] = {}
        for name, tbl in matching_tables.items():

            tbl = tbl.drop(columns=to_drop, errors='ignore')
            if name == 'Opportunity Team Members':
                # Surname, Name -> Name Surname
                # per uniformare al CLACC
                tbl["Name"] = tbl["Name"].apply(self._format_name)
                # Filtro su incarico corrente
                tbl = tbl[(tbl["Starting FY"] <= fiscal_year) & (tbl["Ending FY"] >= fiscal_year)].copy()

                # Colorazione nomi Prt e Mgr se diversi da quelli nel CLACC
                tbl['Name'] = tbl.apply(
                    ClaccRowRenderer.highlight_role_mismatch,
                    args=(self.clacc_obj.eng_mgr, self.clacc_obj.eng_prt),
                    axis=1
                )

            if "Deloitte Legal Entity" in tbl.columns:
                # Filtro per "DELOITTE & TOUCHE SPA" -> "DELOITTE TOUCHE SPA"
                tbl = tbl[tbl["Deloitte Legal Entity"] == LEGAL_ENTITY.replace(' & ', ' ')].copy()
            if "Fiscal Year" in tbl.columns:
                # Filtro al solo Fiscal Year corrente
                tbl = tbl[tbl["Fiscal Year"].astype(str).str.contains(str(fiscal_year), na=False)]
                # Colorazione
                tbl["Fiscal Year"] = tbl["Fiscal Year"].apply(ClaccRowRenderer.highlight_fiscal_year, args=("Fiscal Year", fiscal_year))
                if 'Material (Local Client Service Level)' in tbl.columns:
                    tbl['Material (Local Client Service Level)'] = tbl['Material (Local Client Service Level)'].apply(ClaccRowRenderer.color_yellow)

            dfs[name] = tbl.fillna('')

        return dfs

    @staticmethod
    def _is_risk_detail(table: pd.DataFrame):
        """Requisito da soddisfare per trovare una tabella Risk"""
        return table.shape[1] == 4

    def _fetch_risk(self, risk_id: str, fiscal_year: int) -> pd.DataFrame:
        """
        Recupera i dettagli di un Risk specifico da Salesforce tramite scraping HTML.
        Formatta i dati in una tabella a due colonne affiancate e applica la colorazione.
        """

        # Pagina web del Risk (da scrapare)
        response = self.session.get(DFORCE1_URL + risk_id)

        try:
            # Filtra tabelle trovate per eliminare quelle irrilevanti
            table = next(
                filter(self._is_risk_detail, pd.read_html(StringIO(response.text)))
            )
        except (ValueError, StopIteration):
            print(f"\n{YELLOW}Nessuna tabella RISK trovata per {MAGENTA}{risk_id}{RESET}")
            return pd.DataFrame()

        # Rinomina colonne
        table.columns = ["Attribute_A", "Value_A", "Attribute_B", "Value_B"]

        # Applica colorazioni condizionali
        table["Value_A"] = [self.ui.color_risk(attr, val, fiscal_year, self.clacc_obj.clacc_id) for attr, val in zip(table["Attribute_A"], table["Value_A"])]
        table["Value_B"] = [self.ui.color_risk(attr, val, fiscal_year, self.clacc_obj.clacc_id) for attr, val in zip(table["Attribute_B"], table["Value_B"])]

        return table.fillna('')
