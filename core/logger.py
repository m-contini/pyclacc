import logging
from pathlib import Path
import sys

from .const_shared import LOGGING_FILE

# Configurazione centralizzata del logging per tutti gli altri file
def _setup_logging(file: Path) -> None:
    root_logger = logging.getLogger()

    # Evita di aggiungere handler multipli se il modulo viene importato più volte
    if not root_logger.hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s',
            handlers=[
                logging.FileHandler(file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )

_setup_logging(LOGGING_FILE)
logger = logging.getLogger("pyclacc")
