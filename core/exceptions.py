class NoCredentials(Exception):
    """Sollevata se non si riescono a recuperare le credenziali da .env"""
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

    def __str__(self) -> str:
        return super().__str__()

    __repr__ = __str__

class BadExtraction(Exception):
    """Sollevata se l'estrazione da WebCLACC non va a buon fine a causa della malformazione della query."""
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

    def __str__(self) -> str:
        return super().__str__()

    __repr__ = __str__

class SessionExpired(Exception):
    """Sollevata se la sessione DForce1 è scaduta o invalida."""
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

    def __str__(self) -> str:
        return super().__str__()

    __repr__ = __str__
