"""
Modulo per la formattazione e la visualizzazione dei dati estratti da WebCLACC e DForce1.
Gestisce la colorazione ANSI, il wrapping del testo e la costruzione di tabelle per il terminale.
"""
import re
import textwrap
from urllib.parse import quote
from tabulate import tabulate
import pandas as pd
from typing import Any, Literal, Optional

from core.colours import *
from core.dforce import DFORCE1_URL, DForce1, LEGAL_ENTITY
from core.webclacc import Clacc

min_width = 100

class ClaccRowRenderer:
    """
    Classe responsabile della presentazione.  

    Contiene logica di formattazione ANSI, colori,
    wrapping del testo, costruzione delle tabelle (tabulate)
    """

    # Servono in colorize_fields per prendere il colore
    CYAN = CYAN
    MAGENTA = MAGENTA
    YELLOW = YELLOW
    RED = RED
    GREEN = GREEN
    RESET = RESET

    _FIELD_COLOR_MAP = {
        'Description': 'CYAN',
        'ID_CLACC': 'YELLOW',
        'Client Code': 'MAGENTA',
        'Client Name': 'MAGENTA',
        'Year End Date': 'CYAN',
        'Audit Risk Leader': 'YELLOW',
        'Area Risk Leader': 'YELLOW',
        'Eng. Partner': 'YELLOW',
        'Approver 2': 'YELLOW',
        'EQR': 'RED'
    }

    DEFAULT_WRAP_WIDTH = min_width

    def __init__(self, row: pd.Series) -> None:
        self.row = row
        self.row = self.row.replace("", pd.NA).dropna()
        self.row = self.row.replace({
            'Yes': f"{GREEN}YES{RESET}",
            'No':  f"{RED}NO{RESET}"
        })
        self.max_width: int = round(ClaccRowRenderer.DEFAULT_WRAP_WIDTH / 1.5, None)

    def colorize_fields(self) -> None:
        """Applica i colori ANSI definiti in _FIELD_COLOR_MAP ai campi della riga."""
        for field, color in self._FIELD_COLOR_MAP.items():
            if field in self.row.index:
                self.row[field] = f"{getattr(self, color)}{self.row[field]}{RESET}"

    @staticmethod
    def truncate_text(text: Any, width: int) -> str:
        """Tronca il testo se supera la larghezza specificata."""
        s = str(text)
        return s[:width-3] + '...' if len(s) > int(width) else s

    @staticmethod
    def wrap_ansi_text(text: Any, min_width: Optional[int] = None) -> str:
        """Wrap ANSI-safe, mantiene il colore su tutte le righe."""
        
        if not isinstance(text, str):
            return text
    
        if min_width is None:
            min_width = ClaccRowRenderer.DEFAULT_WRAP_WIDTH

        # Rimuove sequenze ANSI per calcolare la lunghezza effettiva del testo
        stripped = re.sub(r'\x1b\[[0-9;]*m', "", text)
        lines = textwrap.wrap(stripped, min_width)
        # Estrae il colore originale per riapplicarlo a ogni riga wrappata
        m = re.match(r"(\x1b\[[0-9;]*m)(.*)", text)
        color, reset = (m.group(1), RESET) if m else ("", "")
        colored_lines = [f"{color}{line}{reset}" for line in lines]
        return "\n".join(colored_lines)

    def build_two_column_table(self) -> pd.DataFrame:
        """Trasforma la Series della riga in un DataFrame a due colonne (Campo/Valore) affiancate."""
        df = self.row.reset_index()
        df.columns = ["Campo", "Valore"]

        if "Description" in df["Campo"].values:
            split_idx = df.index[df["Campo"] == "Description"][0] + 1
        else:
            # Fallback se non trova la descrizione: divide a metà
            split_idx = len(df) // 2

        left = df.iloc[:split_idx].reset_index(drop=True)
        right = df.iloc[split_idx:].reset_index(drop=True)

        # Padding destra
        if len(right) < len(left):
            missing = len(left) - len(right)
            right = pd.concat([
                right,
                pd.DataFrame([["", ""]] * missing, columns=right.columns)
            ], ignore_index=True)

        combined = pd.concat([left, right], axis=1).fillna("")
        combined.columns = ["Campo", "Valore", "Campo", "Valore"]

        # Applica wrapping e indici numerici
        combined = combined.map(self.wrap_ansi_text, min_width=self.max_width)
        combined.index = combined.index.map(lambda x: self.wrap_ansi_text(str(x + 1), self.max_width))

        return combined

    def render_main_table(self) -> str:
        """Genera la rappresentazione testuale a griglia della tabella principale del CLACC."""
        self.colorize_fields()
        table = self.build_two_column_table()
        return tabulate(
            table.values,
            tablefmt="grid",
            colalign=("right", "left", "right", "left"),
            showindex=False
        )

    def render_validation_table(self, obj: Clacc | DForce1) -> str:
        """Genera tabella (YES/NO) per oggetti Clacc o DForce1."""
        title = obj.__class__.__name__
        # Se ci sono errori (False) nei primi 6 campi (o tutti per Clacc), mostra la tabella
        if any(x[1] == False for x in obj.printable_table[:6 if title == 'DForce1' else None]):
            colored_table = [(k, self.format_boolean(v)) for k, v in obj.printable_table]
            return tabulate(
                colored_table,
                tablefmt='pretty',
                colalign=('right', 'left')
            )
        return f"{GREEN}{title} Check superato!{RESET}\n"

    @staticmethod
    def build_salesforce_link(keyword: int | str) -> str:
        """Crea un hyperlink ANSI (cliccabile nel terminale) per condurre a link di ricerca su Salesforce."""
        url = DFORCE1_URL + "_ui/search/ui/UnifiedSearchResults?searchType=2&str=" + quote(f'"{keyword}"')
        hyperlink = f"\033]8;;{url}\033\\{keyword}\033]8;;\033\\"
        return f'\n{CYAN}Link di ricerca su Salesforce:{RESET} {hyperlink}'

    @staticmethod
    def format_boolean(value: Any) -> str:
        """Converte booleani in stringhe colorate YES/NO."""
        return (
            f"{GREEN}YES{RESET}" if value is True
            else f"{RED}NO{RESET}" if value is False
            else str(value)
        )

    @staticmethod
    def highlight_role_mismatch(row: pd.Series, eng_mgr: str, eng_prt: str) -> str:
        """Evidenzia in rosso il nome se non corrisponde al Manager o Partner indicato nel CLACC."""
        return (
            f"{RED}{row['Name']}{RESET}"
                if (row['Role'] == 'Engagement Manager' and row['Name'] != eng_mgr)
                or (row['Role'] == 'Engagement Partner' and row['Name'] != eng_prt)
            else row['Name']
        )

    @staticmethod
    def color_yellow(v: Any) -> str:
        """Applica colore giallo"""
        return f"{YELLOW}{v}{RESET}"

    @staticmethod
    def highlight_fiscal_year(value: str, attribute: str, fiscal_year: int) -> str:
        """Evidenzia FY corrente in verde."""
        if pd.isna(value):
            return ""
        # Evidenzia FY corrente in verde
        if attribute == "Fiscal Year" and str(value) == str(fiscal_year):
            return f"{GREEN}{value}{RESET}"
        return str(value)

    @staticmethod
    def build_dforce_summary_tables(dforce_obj: DForce1, fiscal_year: int) -> dict[str, pd.DataFrame]:
        """Costruisce le tabelle di riepilogo (Accounts, Opportunities, Risks) da Salesforce."""

        def color_row_if_contains_year(row: pd.Series, year_str: str) -> pd.Series:
            # Controlla se la riga contiene l'anno
            if any(year_str in str(v) for v in row if str(v).isdigit()):
                # Default colore verde
                color = GREEN
                # Controllo colonna "Pipeline Stage" se esiste
                if "Pipeline Stage" in row.index:
                    stage = str(row["Pipeline Stage"]).strip()
                    if stage in ["Lost", "Abandoned"]:
                        color = RED
                    elif stage not in ["Won", "Proposal Submitted"]:
                        color = YELLOW
                # Colora tutta la riga
                return row.map(lambda v: f"{color}{v}{RESET}")
            return row

        to_drop = [
            'Opportunity Account', 'Grado di Rischio', # Risks
            'Industry', 'VAT ID', 'Street', 'Country', 'Swift ID', # Accounts
            'Contracting Entity (Sold-to)', 'Deloitte Legal Entity', 'Probability of Win (%)', 'Total Fees (€)', 'Potential Amount (€)' # Opportunities
        ]
        results: dict[str, pd.DataFrame] = {}
        _dict = dforce_obj.dicts.to_dict()
        for name, data in _dict.items():

            if name == 'Opportunities':
                try:
                    data = data[data['Deloitte Legal Entity'] == LEGAL_ENTITY].copy()
                except KeyError:
                    pass

            if data.empty:
                continue

            data.columns = data.columns.str.strip()
            data.drop(columns=to_drop, inplace=True, errors='ignore')

            # Wrapping di tutte le celle testuali
            for col in data.columns:
                data[col] = data[col].apply(ClaccRowRenderer.truncate_text, args=(ClaccRowRenderer.DEFAULT_WRAP_WIDTH,))

            results[name] = data.apply(color_row_if_contains_year, args=(str(fiscal_year),), axis=1)

        return results

    @staticmethod
    def print_dforce_table(df_or_dict: pd.DataFrame | dict[str, pd.DataFrame], table_kind: Literal['Opportunity', 'Risk']) -> None:
        """Stampa a video le tabelle Salesforce formattate."""
        if len(df_or_dict) == 0:
            return

        if table_kind not in ('Opportunity', 'Risk'):
            print('\nTipo non valido per la tabella da riassumere.')
            return

        if isinstance(df_or_dict, dict):
            for name in df_or_dict.keys():
                print(f"\n=== {name.upper()} ===")
                ClaccRowRenderer.print_dforce_table(df_or_dict[name], table_kind=table_kind)
        else:
            wrapped = df_or_dict.map(ClaccRowRenderer.wrap_ansi_text, min_width=ClaccRowRenderer.DEFAULT_WRAP_WIDTH)
            if table_kind == 'Opportunity':
                print(tabulate(wrapped.to_dict(orient='records'), headers='keys', tablefmt='psql', showindex=False))
            elif table_kind == 'Risk':
                print(f"\n=== RISK DETAIL ===")
                print(tabulate(wrapped.values, tablefmt='psql', showindex=False))

    @staticmethod
    def wrap_text(x: Any, width: int = 50) -> Any:
        """Semplice wrapping del testo senza gestione ANSI."""
        return '\n'.join(textwrap.wrap(x, width=width))

    @staticmethod
    def color_risk(attribute: str, value: str, fiscal_year: int, clacc_id: int) -> str:
        """Applica colorazione condizionale ai dettagli dei Risks."""

        if pd.isna(value):
            return ""

        # Rosso se self.clacc_obj.clacc_id è diverso da value in "Codice CLACC"
        if attribute == "Codice CLACC" and str(value) != str(clacc_id):
            return f"{RED}{value}{RESET}"

        # Evidenzia FY corrente in verde
        if attribute == "Fiscal Year" and value == str(fiscal_year):
            return f"{GREEN}{value}{RESET}"

        # Giallo per EQR
        if attribute == "EQR":
            return f"{RED}{value}{RESET}"

        # Ciano per Commenti
        if attribute == "Commenti":
            return f"{CYAN}{value}{RESET}"

        # Giallo per Risk Evaluation e Year End Date
        if attribute in ["Risk Evaluation", "Year End Date"]:
            return f"{YELLOW}{value}{RESET}"

        return str(value)