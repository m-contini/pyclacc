"""
Questo modulo gestisce la sessione di screening dei CLACC, interfacciandosi con
i dati provenienti da WebCLACC e DForce1.
"""
import os
from time import time
from typing import Any, Optional
import pandas as pd
from prompt_toolkit import prompt

from core.clacc_workflow import ClaccWorkflow, Action
from core.colours import *
from core.dforce import ReportDForce
from core.webclacc import ExportClacc

from .row_processor import RowProcessor

def pick_choice(iterable: list[Any]) -> Optional[str]:
    """
    Mostra una lista di opzioni numerate e restituisce la scelta dell'utente.
    Se l'utente preme Enter senza digitare nulla, restituisce None.
    """
    for i, x in enumerate(iterable):
        print(f'\t{YELLOW}[{i+1}] {CYAN}{x}{RESET}')

    while True:
        try:
            action: int = int(prompt('Inserire numero (Enter per saltare): ').strip() or 0)
            if not action:
                return None
            action -= 1
            if action in range(len(iterable) + 1):
                chosen_action = iterable[action]
                return chosen_action
            raise ValueError
        except (ValueError, IndexError):
            print(f"{RED}Valore non valido.{RESET}", "Inserire un numero da 1 a", len(iterable))
            continue

class ClaccReviewSession:
    """
    Gestisce il flusso di visualizzazione dei dati di ogni singolo CLACC
    e delle opportunità ad essi associate su Salesforce.
    """

    # Colonne da mostrare in output a schermo
    relevant_cols = [
        'Appr. Check Status',
        'Client Name', 'Client Code', 'Sent Back In Draft',
        'Fiscal Year', 'Year End Date', 'New Client', 'Sector', 'Status CLACC',
        'Status Antiriciclaggio', #'Last Modify Date', 'Approval Date',
        'Audit Risk Leader', 'Area Risk Leader', 'LMU', 'Codice Perform Office',
        'Final Risk Class.', 'Eng. Manager', 'Director', 'Eng. Partner', 'Approver 2',
        'Approver 3', 'EQR', 'EQR Exemption', 'Reason of EQR exemption',
        'Description', 'a.Inc. volontari',
        'b.Inc. di legge', 'Details', 'c.Rep.pack.', 'd.Semestrale Volont.',
        'e.AUP', 'f.Rep ISAE 3400', 'g.Oth. Attest', 'h.Comfort letter',
        'i.SOX', 'j.Foll. Law Req.', 'k.PRO-Forma',
        'l. ISA 800/805', 'm. Compliance with laws',
        'n.Other Eng.', 'PCAOB ?', 'Auditing PCAOB standards?', 'US GAAP?',
        'IAS/IFRS?', 'UK GAAP ?', 'Other Country GAAP?', 'Ownership',
        'Ultimate Parent', 'SEC Reg or Subsidiary',
        'CONSOB communication DAC/RM/96003556 ?', 'Please explain in detail...',
        'Does the client require the implementation of GAAC policies?'
    ]

    # Azioni consentite
    ALLOWED_ACTIONS = list(Action)

    def __init__(self, wc: ExportClacc, dforce: ReportDForce) -> None:
        self.session = dforce.session

        self.dforce_df = dforce.dataframe
        self.dforce_df['Account Name (End Client): DST Id'] = self.dforce_df['Account Name (End Client): DST Id'].astype('Int64')

        self.webclacc_df = wc.dataframe.fillna('').reset_index(drop=False)
        if 'Action' not in self.webclacc_df.columns:
            self.webclacc_df['Action'] = ''
        # Riordinamento colonne
        self.webclacc_df = self.webclacc_df[['ID_CLACC', 'Action', *[col for col in self.relevant_cols]]]

        # Isola righe non gestite in precedenza (che hanno Action vuoto)
        self._processed_mask = self.webclacc_df['Action'].astype(bool)

        # Filtro su LMU (opzionale)
        self._lmu: Optional[str] = self._choose_lmu()

    def __len__(self) -> int:
        return len(self.webclacc_df)

    def process_queue(self, fiscal_year: int) -> None:

        # Righe non processate
        webclacc_df = self._remaining_rows()
        webclacc_df = (
            webclacc_df[webclacc_df['Action'] == '']
            .sort_values(by='ID_CLACC', axis=0)
            .reset_index(drop=True)
        )

        # Mappa Opportunity Id e Risk Id per ciascun clacc
        opportunity_risk_map = self._opportunity_risk_map(fiscal_year)
        for i, row in webclacc_df.iterrows():
            id_clacc: int = row['ID_CLACC']
            action: Optional[str] = row['Action'].strip()
            if action:
                continue

            # Libera il terminale
            self._flush_terminal()
            st = time()

            print(f"\nCLACC {id_clacc} {GREEN}({i+1}/{len(webclacc_df)}){RESET}") # type: ignore
            try:
                # Scraping e rendering delle info sul CLACC attuale
                processor = RowProcessor(self.session, row)
                processor.render(opportunity_risk_map, fiscal_year)
            except KeyboardInterrupt:
                pass
            except ValueError as e:
                print(f"{id_clacc}: {e}")
                input("\nPremere Enter per il CLACC successivo... ")
                continue

            print(f"\nTempo impiegato per recuperare i dati: {CYAN}{time()-st:.1f}s{RESET}\n")

            try:
                # --- Azione da intraprendere --- #
                print(f'{YELLOW}Azione?{RESET}')
                action = self._action_on_clacc(id_clacc)
            except (KeyboardInterrupt, EOFError):
                break

            # Marca l'azione sul CLACC nella riga corrente
            # così da escludere il CLACC nelle sessioni future
            self.webclacc_df.loc[self.webclacc_df['ID_CLACC'] == id_clacc, 'Action'] = action

        else:
            input(f'\n{GREEN}Completato!{RESET} (Premere Enter)')

    @property
    def skipped_rows(self) -> pd.DataFrame:
        """Esclude CLACC con Action già eseguita e con LMU diversa da quella scelta"""
        if self._lmu:
            df = self.webclacc_df[self._processed_mask | (self.webclacc_df['LMU'] != self._lmu)]
        else:
            df = self.webclacc_df[self._processed_mask]
        return df.copy()

    @staticmethod
    def _flush_terminal() -> None:
        """Libera il terminale"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _choose_lmu(self) -> Optional[str]:
        """Filtro su LMU (opzionale)"""
        lmus = self.webclacc_df[~self._processed_mask]['LMU'].unique().tolist()
        if len(lmus) == 1:
            self._lmu = lmus[0]
            return
        print(f'\n{YELLOW}Scegliere una LMU, oppure Enter per includerle tutte:{RESET}')
        return pick_choice(sorted(lmus))

    def _opportunity_risk_map(self, fiscal_year: int) -> pd.DataFrame:
        """
        Mappa gli ID_CLACC agli ID Opportunity e Risk di Salesforce.
        Utilizza sia il Client Code che il Client Name per trovare corrispondenze.
        """
        # Primo tentativo di merge basato sul Client Code (DST Id)
        merge_by_code = pd.merge(
            left=self.webclacc_df,
            right=self.dforce_df,
            how='left',
            left_on='Client Code',
            right_on='Account Name (End Client): DST Id',
        )

        # Identifica i CLACC che non hanno trovato corrispondenza tramite codice
        mask_no_match = merge_by_code.loc[merge_by_code['Opportunity Number'].isna(), 'ID_CLACC']
        wc_df_no_match = self.webclacc_df.set_index('ID_CLACC').loc[mask_no_match]

        # Secondo tentativo di merge basato sulla Ragione Sociale per i CLACC mancanti
        merge_by_name = pd.merge(
            left=wc_df_no_match.reset_index(),
            right=self.dforce_df,
            how='left',
            left_on='Client Name',
            right_on='Account Name (End Client): Corporate Name (Ragione Sociale)'
        ).dropna(subset=['Opportunity ID'])

        # Unisce i risultati e rimuove i duplicati mantenendo la corrispondenza migliore
        merge_df = (
            pd.concat([merge_by_name, merge_by_code], axis=0)
            .sort_values(by=['ID_CLACC', 'Codice CLACC'], ascending=[True, False])
            .drop_duplicates(subset='ID_CLACC', keep='first')
            .dropna(subset=['Opportunity ID'])
        )

        # Filtra per Fiscal Year
        merge_df['Risk Fiscal Year'] = pd.to_numeric(merge_df['Risk Fiscal Year'], errors='coerce')
        merge_df = merge_df[merge_df['Risk Fiscal Year'].le(fiscal_year, fill_value=fiscal_year)]
        merge_df.sort_values(
            by=['Account Name (End Client): DST Id', 'Risk Fiscal Year'],
            ascending=[False, False],
            ignore_index=True,
            inplace=True
        )

        # Merge finale per consolidare gli ID Salesforce
        values = pd.merge(
            merge_df.set_index('ID_CLACC'),
            self.webclacc_df.set_index('ID_CLACC'),
            left_index=True,
            right_index=True
        )
        return values[['Opportunity ID', 'Risk ID']].dropna()

    def _remaining_rows(self) -> pd.DataFrame:
        """Restituisce i CLACC che non sono ancora stati processati."""
        df = self.webclacc_df
        return df[~df['ID_CLACC'].isin(self.skipped_rows['ID_CLACC'])]

    @staticmethod
    def _execute_action(button: ClaccWorkflow, action: Action) -> bool:
        """
        Esegue l'azione selezionata sul portale WebCLACC.
        Se l'azione è DRAFT, richiede una motivazione testuale.
        """
        if action == Action.DRAFT:
            motivation = input(f"\n{YELLOW}Inserisci motivazione per 'Send back in draft': {RESET}").strip()
            return button.send_back_in_draft(motivation=motivation)

        button.execute_action(action)
        return True

    def _action_on_clacc(self, id_clacc: int) -> Optional[Action | str]:
        """
        Gestisce l'input dell'utente per determinare quale azione eseguire sul CLACC corrente.
        Interagisce con ClaccWorkflow per applicare le modifiche sul portale.
        """
        action = pick_choice(self.ALLOWED_ACTIONS)

        if action in (Action.DUBBIO, None):
            return action

        button = ClaccWorkflow(id_clacc)
        button.preload_search_result()
        success = self._execute_action(button, Action(action))
        if not success:
            print(f"\n[\u274C] {RED}'{action}' non completata.{RESET}")
            input("Premere Enter per continuare...")
            return None

        try:
            button.preload_search_result()
            status = ClaccWorkflow.parse_status(button.search_response_html)
            print(f"\n[\u2705] {GREEN}{status[0]}{RESET}")
        except RuntimeError:
            pass

        return action
