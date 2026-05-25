"""
Script per la gestione della sessione di screening interattiva dei CLACC.
Permette di caricare i dati da Excel o CSV, visualizzare i dettagli di ogni CLACC
e delle relative opportunità su DForce1, ed eseguire azioni di approvazione
o invio in draft direttamente su WebCLACC.
"""
import os
import sys
from pathlib import Path
import pandas as pd
from requests import RequestException

# Per permettere lettura della cartella core
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core import (
    ClaccReviewSession,
    Explorer,
    BadExtraction,
    ExportClacc,
    ReportDForce,
    OUTPUT_DIR,
    CURRENT_FY,
    logger
)

logging = logger.getLogger(__name__)

def main():

    # Prompt per inserimento Fiscal Year
    while True:
        try:
            fiscal_year = int(input(f"Inserire FY ({CURRENT_FY} o {CURRENT_FY + 1}): ").strip())
            if fiscal_year in (CURRENT_FY, CURRENT_FY + 1):
                break
            raise ValueError
        except ValueError:
            print("Valore non valido...\n")
            continue

    # ReportDForce da scaricare in base al Fiscal Year inserito
    report_ids: dict[int, str] = {
        CURRENT_FY:     "00OVl00000kYAAX",
        CURRENT_FY + 1: "00OVl00000mwlPV"
    }
    report_id = report_ids[fiscal_year]

    # Inizializzazione istanze
    clacc_exporter = ExportClacc(fiscal_year, 'To check', 'Approved')
    dforce = ReportDForce(report_id)

    explorer = Explorer(fiscal_year)

    # Con argomento `csv` lo script scarica prima i dati dal web (e li salva su disco)
    # altrimenti legge direttamente da disco l'ultimo XLSX salvato
    # contenente i progressi del precedente screening
    DOWNLOAD_CSV: bool = 'csv' in sys.argv
    if DOWNLOAD_CSV:
        logging.info("Download CSV...")

        try:
            # Download
            clacc_exporter.download(OUTPUT_DIR)
            # Lettura file appena scaricato
            clacc_exporter.read_csv()
        except BadExtraction:
            logging.error("Estrazione vuota o fallita!")
            return
        except (FileNotFoundError, IndexError, RequestException) as e:
            logging.error(e)
            return
    # Altrimenti legge da file senza scaricare nuovi dati
    if not DOWNLOAD_CSV:
        # Setta dataframe WebCLACC
        explorer.load_dataframe(clacc_exporter, explorer.input_file)

    # Setta dataframe DForce
    explorer.load_dataframe(dforce)

    # ----- INIZIO SESSIONE SCREENING ----- #
    reader = ClaccReviewSession(clacc_exporter, dforce)
    reader.process_queue(fiscal_year)
    # -----           FINE            ----- #

    # Salvataggio progressi
    print(f"\nVuoi scrivere i risultati su un file XLSX? [Enter per confermare, altrimenti qualsiasi carattere]")
    if not input().strip():
        explorer.save_progress(
            pd.concat([reader.webclacc_df, reader.skipped_rows], axis=0, ignore_index=True)
            .drop_duplicates(subset='ID_CLACC', keep='first')
        )

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        logging.info("Addio")
        os._exit(0)
    except (RuntimeError, PermissionError) as e:
        logging.error(f"Errore fatale: [{e.__class__.__name__}] {e}")
