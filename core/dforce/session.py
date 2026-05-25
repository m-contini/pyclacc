"""
Gestione della sessione HTTP per DForce1 (Salesforce).
Include la logica di persistenza dei cookie e la rigenerazione automatica tramite Selenium.
"""
import json
from threading import Lock
import requests

from core import ASSETS_DIR, logger

from .const import SupportFiles, DFORCE1_URL
from .dtypes import CookieType

logging = logger
_cookie_lock = Lock()

class DFSession:
    """
    Classe base per gestire la sessione HTTP verso DForce1 (Salesforce).
    Gestisce il caricamento e la rigenerazione dei cookie tramite Selenium in modalità headless.
    """

    # Percorso file contenente cookies
    _cookie_file = SupportFiles.DFORCE1_COOKIES_JSON.value

    def __init__(self) -> None:
        self.retries = 0
        self.session = requests.Session()
        self.refresh_session()

    @staticmethod
    def _load_cookie_file() -> list[CookieType]:
        """Carica i cookie dal file JSON locale."""
        
        path = DFSession._cookie_file
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logging.error(f"File {path.name} non trovato o corrotto.")
            raise RuntimeError from e

    @staticmethod
    def _cookie_regen() -> list[CookieType]:
        """
        Rigenera i cookie di sessione utilizzando Selenium in modalità headless.
        Accede alla URL di DForce1 per autenticarsi (in base profilo locale)
        e salva i nuovi cookie in un file JSON.
        """
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.options import Options

        logging.info("Getting cookies (via Selenium)...\n")

        chrome_options = Options()

        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Profilo dedicato (utilizzo obbligatorio)
        temp_dir = ASSETS_DIR / 'selenium_profile'
        temp_dir.mkdir(parents=True, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={temp_dir}")

        service = Service(ChromeDriverManager().install())

        driver = webdriver.Chrome(
            service=service,
            options=chrome_options
        )

        # Richiesta GET a Salesforce
        driver.get(DFORCE1_URL)

        # Lista di cookies
        cookies: list[CookieType] = driver.get_cookies() # type: ignore

        # Salvataggio cookies
        DFSession._cookie_file.parent.mkdir(exist_ok=True)
        with open(DFSession._cookie_file, 'w') as f:
            json.dump(cookies, f, indent=4)

        driver.quit()

        logging.info(f"Cookie salvati su {DFSession._cookie_file}\n")
        return cookies

    def refresh_session(self) -> None:
        """
        Aggiorna i cookie della sessione corrente.
        Se retries > 0, forza la rigenerazione tramite Selenium.
        """
        with _cookie_lock:
            if self.retries > 0:
                logging.info("Rigenerazione cookie...")
                cookielist = self._cookie_regen()
            else:
                try:
                    # Caricamento da file
                    cookielist = self._load_cookie_file()
                except RuntimeError:
                    logging.warning("Cookie non validi o mancanti. Avvio Selenium...")
                    cookielist = self._cookie_regen()

            # Aggiorna la sessione esistente
            self.session.cookies.update({
                c['name']: c['value'] for c in cookielist
            })
            self.retries = 0
