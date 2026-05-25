"""
Questo modulo fornisce la classe Downloader per automatizzare il download
di report multipli sia da WebCLACC che da DForce1.
Gestisce la parallelizzazione dei download per minimizzare i tempi di esecuzione.
"""
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
    Future
)
from typing import Optional

from core import OUTPUT_DIR, logger

from .webclacc import ExportClacc, WebCLACCParamsType
from .dforce import ReportDForce, DForceReportType

logging = logger.getLogger(__name__)

class Downloader:
    """
    Gestisce il download massivo di report da WebCLACC e DForce1.
    Supporta l'esecuzione sequenziale o parallela tramite ThreadPoolExecutor.
    """

    def __init__(
        self,
        webclacc_params_list: WebCLACCParamsType | list[WebCLACCParamsType],
        dforce_params_list: DForceReportType | list[DForceReportType],
        max_workers: Optional[int] = None
    ) -> None:
        if not isinstance(webclacc_params_list, list):
            webclacc_params_list = [webclacc_params_list]
        if not isinstance(dforce_params_list, list):
            dforce_params_list = [dforce_params_list]

        # Lista di parametri di download
        self.webclacc_params_list = webclacc_params_list
        self.dforce_params_list = dforce_params_list

        # Numero di workers simultanei
        # se non passato, viene eguagliato al numero totale
        # di estrazioni da eseguire
        self.max_workers: int = max_workers or (len(webclacc_params_list) + len(dforce_params_list))

    def run(self, concurrent: bool) -> None:
        """
        Avvia il processo di download per tutti i report configurati.
        """

        # Modalità sequenziale
        if not concurrent:
            logging.info("Download: modalità sequenziale")
            for args in self.webclacc_params_list:
                self._run_exportclacc(args)
            for arg in self.dforce_params_list:
                self._run_dforce(arg)
            return

        # Modalità in parallelo
        logging.info("Download: modalità concorrenziale")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:

            futures: list[Future[None]] = [
                    executor.submit(self._run_exportclacc, args) for args in self.webclacc_params_list
                ] + [
                    executor.submit(self._run_dforce, args) for args in self.dforce_params_list
                ]

            # Aspetta completamento
            for future in as_completed(futures):
                future.result()

    def _run_exportclacc(self, args: WebCLACCParamsType) -> None:
        """Esegue il download di un report da WebCLACC."""
        try:
            logging.info(f"[WebCLACC] Processing {', '.join(map(str, args))}")
            webclacc = ExportClacc(*args)
            webclacc.download(OUTPUT_DIR)
        except KeyboardInterrupt:
            logging.error(f"[WebCLACC] Interrotto {args}")
        except Exception as e:
            logging.error(f"[WebCLACC] Errore {args}: {e}")

    def _run_dforce(self, args: DForceReportType) -> None:
        """Esegue il download di un report da DForce1."""
        try:
            name, id = args['name'], args['id']
            logging.info(f"[DForce] Processing '{name}': '{id}'")
            dforce = ReportDForce(id)
            dforce.download(OUTPUT_DIR)
        except KeyboardInterrupt:
            logging.error(f"[DForce] Interrotto ({args})")
        except Exception as e:
            logging.error(f"[DForce] Errore ({args}): {e}")
