"""
Script per l'automazione del download massivo di report da WebCLACC e DForce1.
Permette di scaricare simultaneamente o sequenzialmente i dati necessari
per alimentare la sessione di screening dei CLACC.
"""
import os
import sys
from pathlib import Path
from time import perf_counter

# Per permettere lettura della cartella core
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core import (
    Downloader,
    WebCLACCParamsType,
    DForceReportType,
    logger
)

logging = logger

exportclacc_args_list: list[WebCLACCParamsType] = [
    (2026, 'All', 'All'),
    (2027, 'All', 'All'),
    # (2026, 'To check', 'Approved'),
    # (2027, 'To check', 'Approved'),
]

dforce_args_list: list[DForceReportType] = [
    {'name': 'Opp_FY26 con Opp_id e Risk_id', 'id': '00OVl00000kYAAX'},
    {'name': 'Opp_FY27 con Opp_id e Risk_id', 'id': '00OVl00000mwlPV'},
    {'name': '[Default] WON+PropSubmitted',   'id': '00OVl00000U4E4j'},
    {'name': 'WON+PropSubmitted FY27',        'id': '00OVl00000mwfDp'},
]

def main() -> None:
    # Controlla se lo script è stato chiamato con flag `concurrent`
    CONCURRENT = 'concurrent' in sys.argv
    if not CONCURRENT:
        print("[HINT] Usare opzione 'concurrent' per eseguire i download in parallelo")

    try:
        # Istanza propedeutica al download massivo
        downloader = Downloader(exportclacc_args_list, dforce_args_list, max_workers=8)

        # Avvia i download
        start = perf_counter()
        downloader.run(concurrent=CONCURRENT)

        logging.info(f"Tempo totale: {perf_counter() - start:.2f} secondi")
    except (KeyboardInterrupt, EOFError):
        logging.info("Addio")
        os._exit(0)

if __name__ == '__main__':
    main()
