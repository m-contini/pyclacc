"""
Questo modulo definisce la classe Clacc, che rappresenta l'entità principale
del questionario CLACC.

Gestisce la logica di validazione degli approvatori,
le regole di business e la coerenza dei dati.
"""
from typing import Optional, cast
from datetime import datetime
import re
import pandas as pd

from core import (
    AUDIT_BUSINESS_LEADER, 
    OLD_AUDIT_RISK_LEADERS, 
    NEW_AUDIT_RISK_LEADERS, 
    EQUIVALENT_LMU
)

class Clacc:

    # Data oltre la quale cambiano i nominativi di
    # Audit Risk Leader, Area Risk Leader, Supporting Partner (Approver 2)
    APPROVAL_FLOW_THRESHOLD = datetime(2025, 6, 23)

    # Nomi noti
    AUDIT_BUSINESS_LEADER = AUDIT_BUSINESS_LEADER
    OLD_AUDIT_RISK_LEADERS = OLD_AUDIT_RISK_LEADERS
    NEW_AUDIT_RISK_LEADERS = NEW_AUDIT_RISK_LEADERS

    # LMU equivalenti
    EQUIVALENT_LMU = EQUIVALENT_LMU

    def __init__(
        self,
        clacc_id: Optional[int],
        row: pd.Series,
        first_submit_ser: pd.Series,
        approvers_df: pd.DataFrame,
    ) -> None:

        if clacc_id is None:
            clacc_id = cast(int, row.name)

        self.clacc_id = int(clacc_id)

        # Dati esposti del questionario
        self._clacc_data: dict[str, str] = cast(dict[str, str], row.to_dict())

        # Approvatori attesi
        self._expected_tmp_approvers: dict[str, str] = self.flusso_approvativo(
            first_submit_ser, approvers_df
        )

    def flusso_approvativo(
        self,
        submit_ser: pd.Series,
        appr_df: pd.DataFrame
    ) -> dict[str, str]:

        try:
            # Confronta data di primo submit con data soglia definita a livello di classe
            is_new_flow = submit_ser.loc[self.clacc_id] >= Clacc.APPROVAL_FLOW_THRESHOLD
        except KeyError:
            # Se la data non esiste, allora è nuovo flusso
            is_new_flow = True

        flow_key = "NEW" if is_new_flow else "OLD"

        try:
            # Ricava terna di nomi in base a LMU
            values = appr_df.loc[
                (flow_key, self.lmu),
                ['Audit Risk Leader', 'Area Risk Leader', 'Approver 2']
            ]
            return cast(dict[str, str], values.to_dict())
        except (KeyError, pd.errors.IndexingError) as e:
            raise ValueError(
                f"Combinazione flusso='{flow_key}' e LMU='{self.lmu}' non trovata fra i flussi approvativi."
            ) from e

    @property
    def fy(self) -> int:
        return int(self._clacc_data['Fiscal Year'])

    @property
    def client_code(self) -> int:
        return int(self._clacc_data['Client Code'])

    @property
    def client_name(self) -> str:
        return self._clacc_data['Client Name']

    @property
    def is_new_client(self) -> bool:
        return self._clacc_data['New Client'] == 'Yes'

    @property
    def audit_rl(self) -> str:
        return self._clacc_data['Audit Risk Leader']

    @property
    def area_rl(self) -> str:
        return self._clacc_data['Area Risk Leader']

    def _fix_name(self, name: str | float) -> str:
        if not isinstance(name, str):
            return ""
        return name.replace('CAMOSCI VITTORIO GIOVANNI', 'CAMOSCI VITTORIO')

    @property
    def approver2(self) -> str:
        return self._fix_name(self._clacc_data['Approver 2'])

    @property
    def approver3(self) -> str:
        return self._fix_name(self._clacc_data['Approver 3'])

    @property
    def year_end_date(self) -> str:
        return self._clacc_data['Year End Date']

    @property
    def sector(self) -> str:
        return self._clacc_data['Sector']

    @property
    def perform_o(self) -> str:
        return self._clacc_data['Codice Perform Office']

    @property
    def risk(self) -> str:
        return self._clacc_data['Final Risk Class.']

    @property
    def eng_mgr(self) -> str:
        return self._clacc_data['Eng. Manager']

    @property
    def eng_prt(self) -> str:
        return self._clacc_data['Eng. Partner']

    @property
    def director(self) -> str:
        return self._clacc_data['Director']

    @property
    def SEC_reg(self) -> str:
        return self._clacc_data['SEC Reg or Subsidiary']

    @property
    def ownership(self) -> str:
        return self._clacc_data['Ownership']

    @property
    def EQR_exemption(self) -> str:
        return self._clacc_data['EQR Exemption']

    @property
    def EQR_name(self) -> str:
        return self._clacc_data['EQR']

    @property
    def lmu(self) -> str:
        try:
            return Clacc.EQUIVALENT_LMU[self._clacc_data['LMU']]
        except KeyError:
            return self._clacc_data['LMU']

    def _ics_adjust_approver2(self) -> str:
        """Associa il Supporting Partner corretto in base al Performing Office"""
        if self.perform_o in ['BO', 'FI', 'PR']:
            return 'BANDINI NERI'
        elif self.perform_o in ['VR', 'PD', 'TV', 'UD']:
            return 'NACCHI CRISTIANO'
        return self.approver2

    @staticmethod
    def _alt_aurl(name: str) -> str:
        """
        Funzione che scambia i nomi degli Audit Risk Leader
        per porli come approvatori alternativi, se necessario.
        """
        for pair in (Clacc.OLD_AUDIT_RISK_LEADERS, Clacc.NEW_AUDIT_RISK_LEADERS):
            if name not in pair:
                continue
            return next(iter(pair - {name}))
        return ""

    @property
    def expected_approvers(self) -> dict[str, str]:
        expected = self._expected_tmp_approvers.copy()

        # Caso Eng Partner speciale
        # Se l'Audit Business Leader è l'Eng. Partner -> Approver 2 diventa l'Area Risk Leader
        if self.eng_prt == Clacc.AUDIT_BUSINESS_LEADER:
            expected['Approver 2'] = expected['Area Risk Leader']

        # Regole ICS
        elif self.sector == 'ICS':
            expected['Approver 2'] = self._ics_adjust_approver2()

        # Se Approver 2 coincide con Eng. Partner
        if expected['Approver 2'] == self.eng_prt:
            expected['Approver 2'] = expected['Area Risk Leader']

        # Approver 3 rischio Normal
        if self.risk == 'Normal':
            expected['Approver 3'] = ''
        # Approver 3 rischio maggiore di Normal
        else:
            candidates = (
                expected['Area Risk Leader'],
                expected['Audit Risk Leader'],
                self._alt_aurl(expected['Audit Risk Leader'])
            )
            for c in candidates:
                # Il primo nome non nullo che non sia né partner né Approver 2
                if c and c not in (self.eng_prt, expected['Approver 2']):
                    expected['Approver 3'] = c
                    break

        return expected

    @property
    def check_approvers(self) -> dict[str, bool]:
        """
        Controlla la correttezza logica dei principali dati del CLACC
        (Approvatori, Director, Engagement Partner)
        """
        exp = self.expected_approvers
        return {
            'Audit Risk Leader': self.audit_rl == exp['Audit Risk Leader'],
            'Area Risk Leader': self.area_rl == exp['Area Risk Leader'],
            'Approver 2': self.approver2 == exp['Approver 2'],
            'Approver 3': self.approver3 == exp['Approver 3'],
            'Director': self.director != self.eng_prt,
            'Engagement Partner': bool(self.eng_prt),
        }

    @property
    def _check_eqcr(self) -> bool:
        """
        Controlla la coerenza dei campi 'EQR Exemption' ed 'EQR'
        """
        name = self.EQR_name
        if not name:
            return self.EQR_exemption == 'Yes'
        if name != self.eng_prt:
            return self.EQR_exemption in ('No', 'Partial')
        return False

    @property
    def summary(self) -> dict[str, bool]:
        """
        Restituisce summary come lista di records.
        Utile per la stampa tramite tabulate.
        """
        return self.check_approvers | {
            'Ownership': (self.SEC_reg == 'Yes') == self.ownership.startswith('h.'),
            'LMU': not bool(re.search(r"ICS \w{2}\-.*", self._clacc_data['LMU'])),
            'EQR': self._check_eqcr,
        }

    @property
    def printable_table(self) -> list[tuple[str, bool]]:
        """
        Restituisce summary come lista di records.
        Utile per la stampa tramite tabulate.
        """
        return list(self.summary.items())
