import pandas as pd
from typing import Any, Hashable, Optional, TypeAlias, TypedDict

# Alias per gli oggetti usati in DForce
AccountType: TypeAlias = tuple[Optional[str], Optional[int], Optional[str]]
RiskType: TypeAlias = list[dict[Hashable, Any]]
OpportunityType: TypeAlias = list[dict[Hashable, Any]]
CookieType: TypeAlias = dict[str, Any]

class DForceReportType(TypedDict):
    name: str
    id: str

# Definito in questo modo così da poter avere spazi nelle chiavi
SummaryType = TypedDict('SummaryType', {
    'Has Opportunity': bool,
    'Has Risk': bool,
    'Same Name': bool,
    'Same Code': bool,
    'New Client': bool,
    'Same LCSP': bool,
    'IT LCSP': str | None,
    'Eng. Partner': str | None,
    'Pipeline Stages': str,
    'Under Inv.': bool,
    'Lost': bool,
})

class DFSearchResults:
    """Rappresenta i risultati di ricerca su Salesforce tramite chiave (Client Name o Client Code)"""

    __slots__ = ('Accounts', 'Risks', 'Opportunities')

    def __init__(self, **kwargs: pd.DataFrame) -> None:
        for s in self.__slots__:
            # Disponibili soltanto:
            # self.Accounts, self.Risks, self.Opportunities
            # i rispettivi valori saranno DataFrame
            setattr(self, s, kwargs.get(s, pd.DataFrame()))

    def __bool__(self):
        # True se almeno un DataFrame non è vuoto
        return any((not getattr(self, s).empty for s in self.__slots__))

    def to_dict(self) -> dict[str, pd.DataFrame]:
        # Chiavi: 'Accounts', 'Risks', 'Opportunities'
        # Valori: rispettivi DataFrame
        return dict(
            zip(self.__slots__,
                (self.Accounts, self.Risks, self.Opportunities))
        )
