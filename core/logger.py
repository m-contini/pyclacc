import logging as _logging
from pathlib import Path
import sys

from .const_shared import LOGGING_FILE

# Configurazione centralizzata del logging per tutti gli altri file
def _setup_logging(file: Path) -> None:
    root_logger = _logging.getLogger()

    # Evita di aggiungere handler multipli se il modulo viene importato più volte
    if not root_logger.hasHandlers():
        _logging.basicConfig(
            level=_logging.INFO,
            format='%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s',
            handlers=[
                _logging.FileHandler(file, encoding='utf-8'),
                _logging.StreamHandler(sys.stdout)
            ]
        )

_setup_logging(LOGGING_FILE)
logger = _logging
