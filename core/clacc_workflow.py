"""
Questo modulo implementa l'automazione delle azioni sul portale WebCLACC.
Gestisce l'interazione con l'interfaccia web (Ajax/ASP.NET) per eseguire
operazioni di approvazione, investigazione o invio in draft dei CLACC.
"""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Optional
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import re

from .webclacc import ExportClacc, WebCLACCEndpoints, CLACC_EXPOSED_COLS

# --- Costanti per richieste HTTP --- #
HEADERS_BASE = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'it,en-US;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

HEADERS_FORM = HEADERS_BASE | {
    'Cache-Control': 'max-age=0',
    'Referer': 'https://clacc.deloitte.it/DefaultPage.aspx',
    'Sec-Fetch-Site': 'same-origin',
}

HEADERS_POST = HEADERS_FORM | {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://clacc.deloitte.it',
}

HEADERS_AJAX = {
    'Accept': '*/*',
    'Accept-Language': 'it,en-US;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'https://clacc.deloitte.it',
    'Referer': 'https://clacc.deloitte.it/Modules/Monitoring/CheckApprovers.aspx',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': HEADERS_BASE['User-Agent'],
    'X-MicrosoftAjax': 'Delta=true',
    'X-Requested-With': 'XMLHttpRequest',
    'sec-ch-ua': HEADERS_BASE['sec-ch-ua'],
    'sec-ch-ua-mobile': HEADERS_BASE['sec-ch-ua-mobile'],
    'sec-ch-ua-platform': HEADERS_BASE['sec-ch-ua-platform'],
}

PARAMS_QUEST = (
    ('CheckApprovers', 'true'),
    ('KeyUser', 'true'),
)

def pick_tokens_any(text: str, eventtarget: Optional[str] = "", eventargument: Optional[str] = "") -> dict[str, str]:
    """
    Estrae i token di sessione (__VIEWSTATE, __VIEWSTATEGENERATOR, ecc.) e i valori dei campi
    da una risposta HTML.
    Permette di forzare i valori di __EVENTTARGET e __EVENTARGUMENT.
    """

    def _pick_tokens_html(html: str) -> dict[Any, Any]:
        soup = BeautifulSoup(html, "html.parser")
        fields: dict[Any, Any] = {}

        for input_ in soup.find_all("input"):
            name = input_.get("name")
            if name:
                fields[name] = input_.get("value", "")

        for textarea in soup.find_all("textarea"):
            name = textarea.get("name")
            if name:
                fields[name] = textarea.text

        for select in soup.find_all("select"):
            name = select.get("name")
            if name:
                opt = select.find("option", selected=True)
                if opt:
                    fields[name] = opt.get("value", "")

        return fields

    def _pick_tokens_msajax_delta(html: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for m in re.finditer(r"hiddenField\|([^|]+)\|([^|]*)", html):
            name, value = m.group(1), m.group(2)
            fields[name] = value
        return fields

    if "hiddenField|" in text:
        fields = _pick_tokens_msajax_delta(text)
    else:
        fields = _pick_tokens_html(text)

    if eventtarget is not None:
        fields["__EVENTTARGET"] = eventtarget
    if eventargument is not None:
        fields["__EVENTARGUMENT"] = eventargument
    
    # Ritorna il set completo di token necessari per la prossima richiesta POST
    return fields

def make_form_base_from(text: str, id_clacc: str, **kwargs: str) -> dict[str, str]:
    """
    Estrae i token di sessione e i campi necessari per costruire il payload di una richiesta POST.
    Configura i parametri di ricerca per filtrare i CLACC in base all'ID fornito.
    """
    base = pick_tokens_any(text, **kwargs)
    
    # Sovrascrive i campi del form di ricerca per isolare il singolo ID_CLACC
    base.update({
        "ctl00$ContentPlaceHolder1$DropDownList_Questionnaire": "1",
        "ctl00$ContentPlaceHolder1$DropDownList_FiscalYear": "-1",
        "ctl00$ContentPlaceHolder1$DropDownList_Manager": "-1",
        "ctl00$ContentPlaceHolder1$DropDownList_FinalRisk": "-1",
        "ctl00$ContentPlaceHolder1$DropDownList_ApproverCheckStatus": "-1",
        "ctl00$ContentPlaceHolder1$DropDownList_CLACCStatus": "-1",
        "ctl00$ContentPlaceHolder1$TextBox_Client": "",
        "ctl00$ContentPlaceHolder1$TextBox_IdClacc": id_clacc,
        "ctl00$ContentPlaceHolder1$DropDownList_ChooseApprover": "-1",
        "ctl00$ContentPlaceHolder1$DropDownList_QuestionnairesPerPage": "10",
        "ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_RadioButton": "GridView_RadioButton",
        "__EVENTTARGET": kwargs.get("eventtarget", ""),
        "__EVENTARGUMENT": kwargs.get("eventargument", ""),
        "__LASTFOCUS": "",
        "__SCROLLPOSITIONX": "0",
        "__SCROLLPOSITIONY": "0",
        "__ASYNCPOST": "true",
    })
    return base

def parse_search_results(html: str) -> dict[str, str]:
    """
    Parsa la risposta HTML/Ajax per estrarre i dati del questionario CLACC.
    Restituisce un dizionario mappando le intestazioni delle colonne ai valori della riga trovata.
    """
    soup3 = BeautifulSoup(html, "html.parser")

    cols: list[str] = []
    for tr in soup3.select("tr"):
        col_cells = [th.get_text(strip=True) for th in tr.find_all("th")][1:]
        if len(col_cells) == CLACC_EXPOSED_COLS:
            cols = col_cells
            break

    if not 'ID_CLACC' in cols:
        print(f"[ERROR] - Nessun CLACC trovato con questo id.")
        raise KeyError

    rows: list[str] = []
    for tr in soup3.select("tr"):
        row_cells = [td.get_text(strip=True) for td in tr.find_all("td")][1:]
        if len(row_cells) == CLACC_EXPOSED_COLS:
            rows = row_cells

    return dict(zip(cols, rows))

def soup_to_df(html: str) -> pd.DataFrame:
    """
    Parsing dell'HTML della pagina di dettaglio del CLACC per estrarre la tab con lo storico delle approvazioni.
    Cerca le tabelle con classe 'gridViewBorderTable_ApprovalProcess' e le converte in DataFrame.
    """
    soup = BeautifulSoup(html, 'html.parser')
    approval = soup.find_all('table', class_="gridViewBorderTable_ApprovalProcess")

    rows: list[list[str]]= []
    for table in approval:
        for row in table.find_all('tr'):
            cols = row.find_all(['td', 'th'])
            cols = [ele.text.strip() for ele in cols]
            rows.append(cols)
    return pd.DataFrame(rows)

def fetch_login_page(session: requests.Session) -> str:
    """
    Esegue il login al portale WebCLACC.
    Gestisce il reindirizzamento automatico e verifica di essere atterrati sulla pagina corretta.
    """
    
    headers_login = {
        **HEADERS_BASE,
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Host': 'clacc.deloitte.it'
    }
    try:
        response = session.get(WebCLACCEndpoints.LOGIN.value, headers=headers_login)
        response.raise_for_status()
    except requests.RequestException:
        raise SystemExit("[ERROR] - Attiva la VPN e/o fornisci un certificato valido (SSL Error)")
    except Exception as e:
        raise SystemExit(f"[ERROR] - Si è verificato un errore: {e}") from e

    assert (
        response.history[0].status_code == 302
        and response.url == WebCLACCEndpoints.DEFAULT.value
        and len(response.history) == 1
    ), f"[ERROR] - Login.aspx: (Status {response.status_code}, Landed on {response.url})"
    assert response.history[0].ok
    return response.text

# Azioni possibili via WebCLACC
class Action(StrEnum):
    CHECK = "Check"
    UNDER_INV = "Under Inv."
    DRAFT = "Draft"
    REJECTED = "Rejected"
    # Dubbio: prosegue senza azione
    DUBBIO = "Dubbio"

# Parametro da passare ai payload
@dataclass(frozen=True)
class ActionConfig:
    button_name: str
    x: str
    y: str

@dataclass(frozen=True)
class Step:
    """
    Rappresenta un singolo passaggio nel workflow di automazione WebCLACC.
    Incapsula il metodo HTTP, l'URL, gli header e la logica di generazione del payload.
    """

    method: str
    url: str
    headers: dict[str, str]
    data_func: Optional[Callable[[requests.Response], dict[str, str] | None]] = None
    kwargs: dict[str, str] = field(default_factory=dict) # type: ignore
    assert_func: Optional[Callable[[requests.Response], None]] = None

    @staticmethod
    def prepare_menu_payload(response: requests.Response) -> dict[str, str]:
        d = pick_tokens_any(
            response.text,
            eventtarget="ctl00$Menu_WebClacc",
            eventargument="Monitoring\\Check Approvers"
        )
        d.pop("ctl00$ImageButton_GoToDeloitteIntranet", None)
        d.pop("ctl00$ImageButton_GoToHomePage", None)
        return d

    @staticmethod
    def assert_valid_session(response: requests.Response) -> None:
        tokens = pick_tokens_any(response.text)
        assert "__VIEWSTATE" in tokens, "__VIEWSTATE assente!"
        assert "__VIEWSTATEGENERATOR" in tokens, "__VIEWSTATEGENERATOR assente!"

    @staticmethod
    def prepare_search_payload(response: requests.Response, **kwargs: str) -> dict[str, str]:
        return {
            **make_form_base_from(response.text, kwargs.get('clacc_id', '')),
            "ctl00$ContentPlaceHolder1$ScriptManager1":
                quote_plus("ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|ctl00$ContentPlaceHolder1$Button_Search"),
            "ctl00$ContentPlaceHolder1$Button_Search": "Search",
        }

    @staticmethod
    def prepare_select_row_payload(response: requests.Response, **kwargs: str) -> dict[str, str]:
        return {
            **make_form_base_from(response.text, kwargs.get('clacc_id', '')),
            "ctl00$ContentPlaceHolder1$ScriptManager1":
                quote_plus("ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_RadioButton"),
            "ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_RadioButton": "GridView_RadioButton",
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_RadioButton",
        }

    @staticmethod
    def prepare_action_payload(response: requests.Response, **kwargs: str) -> dict[str, str]:
        return {
            **make_form_base_from(response.text, kwargs.get('clacc_id', '')),
            "ctl00$ContentPlaceHolder1$ScriptManager1":
                quote_plus(f"ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|ctl00$ContentPlaceHolder1${kwargs.get('button')}"),
            f"ctl00$ContentPlaceHolder1${kwargs.get('button')}.x": f"{kwargs.get('x')}",
            f"ctl00$ContentPlaceHolder1${kwargs.get('button')}.y": f"{kwargs.get('y')}",
        }

    @staticmethod
    def prepare_modal_ok_payload(response: requests.Response, **kwargs: str) -> dict[str, str]:
        return {
            **make_form_base_from(response.text, kwargs.get('clacc_id', '')),
            "ctl00$ContentPlaceHolder1$ScriptManager1":
                quote_plus(f"ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|ctl00$ContentPlaceHolder1${kwargs.get('button')}"),
            f"ctl00$ContentPlaceHolder1${kwargs.get('button')}": "Ok",
        }

class ClaccWorkflow:
    """
    Gestisce il workflow di automazione sul portale WebCLACC per il singolo CLACC.
    Esegue ricerca e cambia lo stato (Checked, Under Investigation, Rejected)
    o invia il CLACC in Draft con una motivazione.
    """

    # Parametri per i payload
    ACTION_CONFIGS = {
        Action.CHECK: ActionConfig("ImageButton_Check", "8", "8"),
        Action.UNDER_INV: ActionConfig("ImageButton_UnderInvest", "8", "8"),
        Action.REJECTED: ActionConfig("ImageButton_ProposalRefused", "7", "12"),
    }

    def __init__(self, id_clacc: int) -> None:
        # Sessione autenticata
        self.session = ExportClacc.auth()
        self.clacc_id: str = str(id_clacc)

    def preload_search_result(self) -> None:
        """
        Esegue la ricerca iniziale del CLACC sul portale per popolare i token di sessione.
        Utilizzato per garantire che il sistema sia pronto a ricevere comandi POST.
        """
        try:
            self.search_response_html = self._search_by_id()
        except RuntimeError:
            pass

    @property
    def _payload(self) -> dict[str, str]:
        """
        Configura i parametri del form ASP.NET necessari per la ricerca filtrata per ID_CLACC.
        """
        return {
            "ctl00$ContentPlaceHolder1$ScriptManager1":
                "ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|"
                "ctl00$ContentPlaceHolder1$Button_Search",
            "ctl00$ContentPlaceHolder1$Button_Search": "Search",
            "ctl00$ContentPlaceHolder1$DropDownList_Questionnaire": "1",
            "ctl00$ContentPlaceHolder1$DropDownList_FiscalYear": "-1",
            "ctl00$ContentPlaceHolder1$DropDownList_Manager": "-1",
            "ctl00$ContentPlaceHolder1$DropDownList_FinalRisk": "-1",
            "ctl00$ContentPlaceHolder1$DropDownList_ApproverCheckStatus": "-1",
            "ctl00$ContentPlaceHolder1$DropDownList_CLACCStatus": "-1",
            "ctl00$ContentPlaceHolder1$TextBox_Client": "",
            "ctl00$ContentPlaceHolder1$TextBox_IdClacc": str(self.clacc_id),
            "ctl00$ContentPlaceHolder1$DropDownList_ChooseApprover": "-1",
            "ctl00$ContentPlaceHolder1$DropDownList_QuestionnairesPerPage": "10",
        }

    @staticmethod
    def parse_status(html: str) -> tuple[str, str]:
        """
        Parsing dell'HTML della risposta di ricerca per estrarre
        `Appr. Check Status` e `Status CLACC`
        """        
        try:
            questionnaire = parse_search_results(html)
            return (
                questionnaire['Appr. Check Status'],
                questionnaire['Status CLACC']
            )
        except (SystemExit, ValueError, KeyError) as e:
            raise RuntimeError from e

    def _run_steps(self, steps: list[Step]) -> None:
        """
        Esegue sequenzialmente una lista di passaggi per automatizzare il flusso.
        Gestisce le chiamate GET e POST, passando i dati tra i vari steps.
        """
        last_response: Optional[requests.Response] = None
        for step in steps:
            step: Step
            url, headers = step.url, step.headers
            if step.method == "get":
                last_response = self.session.get(url, headers=headers)
            elif step.method == "post":
                data_func, kwargs = step.data_func, step.kwargs
                if data_func and last_response:
                    data = data_func(last_response, **kwargs)
                else:
                    data = None
                last_response = self.session.post(url, headers=headers, data=data)
            if step.assert_func is not None:
                step.assert_func(last_response if last_response else requests.Response())

    def switch_tab(self, html: str, tab_index: int) -> str:
        """
        Simula il cambio tab nella pagina dettaglio CLACC.
        Replica il comportamento funzionante della versione OLD.
        """

        payload = make_form_base_from(
            text=html,
            id_clacc=self.clacc_id,
            eventtarget='ctl00$ContentPlaceHolder1$TabContainer1',
            eventargument=f'activeTabChanged:{tab_index}',
        )
        
        # Rimuove il selettore della riga per evitare conflitti con l'evento di cambio tab
        payload.pop('ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_RadioButton', None)

        # ClientState è richiesto dal controllo TabContainer di ASP.NET per mantenere lo stato dei pannelli
        payload['ctl00_ContentPlaceHolder1_TabContainer1_ClientState'] = '{"ActiveTabIndex":' + str(tab_index) + ',"TabState":[true,true,true,true,true,true,true,true]}'

        response = self.session.post(
            WebCLACCEndpoints.QUEST.value,
            headers=HEADERS_AJAX,
            params=PARAMS_QUEST,
            data=payload
        )

        return response.text

    def send_back_in_draft(self, motivation: str) -> bool:
        """
        Esegue la procedura per rimandare il CLACC in stato 'Draft'.
        Richiede l'inserimento di una motivazione obbligatoria che viene inviata
        tramite una finestra modale sul portale.
        """

        # Login
        _ = self.session.get(
            WebCLACCEndpoints.LOGIN.value,
            headers=HEADERS_BASE
        )

        # Default page
        response = self.session.get(
            WebCLACCEndpoints.DEFAULT.value,
            headers=HEADERS_BASE
        )
        _ = self.session.post(
            WebCLACCEndpoints.DEFAULT.value,
            headers=HEADERS_POST,
            data=Step.prepare_menu_payload(response)
        )

        #  CheckApprovers
        resp_form = self.session.get(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_FORM
        )
        Step.assert_valid_session(resp_form)

        # STEP 1 – Seleziona riga / aggiungi motivation
        resp1 = self.session.post(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_AJAX,
            data={
                **Step.prepare_select_row_payload(resp_form, clacc_id=self.clacc_id),
                "ctl00$ContentPlaceHolder1$TextBox_BodyWriteMotivation": motivation
            }
        )

        # STEP 2 – Click SendBackInDraft
        # Nota: ASP.NET ImageButton richiede le coordinate X e Y del click nel payload
        button = ActionConfig("ImageButton_SendBackInDraft", "15", "12")
        resp2 = self.session.post(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_AJAX,
            data=Step.prepare_action_payload(
                resp1,
                clacc_id=self.clacc_id,
                button=button.button_name,
                x=button.x,
                y=button.y
            )
        )

        # STEP 3 - Conferma motivation
        _ = self.session.post(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_AJAX,
            data={
                **Step.prepare_modal_ok_payload(resp2, clacc_id=self.clacc_id, button='Button_WriteMotivation_OK'),
                "ctl00$ContentPlaceHolder1$TextBox_BodyWriteMotivation": motivation
            }
        )

        return True

    def _build_base_steps(self) -> list[Step]:
        """
        Costruisce la sequenza iniziale di passaggi comuni a tutti i workflow.
        Include login, navigazione alla home e accesso al form di monitoraggio.
        """
        return [
            Step("get", WebCLACCEndpoints.LOGIN.value, HEADERS_BASE),
            Step("get", WebCLACCEndpoints.DEFAULT.value, HEADERS_BASE),
            Step("post", WebCLACCEndpoints.DEFAULT.value, HEADERS_POST, data_func=Step.prepare_menu_payload),
            Step("get", WebCLACCEndpoints.FORM.value, HEADERS_FORM, assert_func=Step.assert_valid_session),
        ]

    def execute_action(self, action: Action) -> bool:
        """
        Esegue l'azione specificata (Check, Under Investigation o Rejected) sul portale WebCLACC.
        Il workflow prevede la ricerca del CLACC, la selezione della riga, il click sul pulsante
        di azione e la conferma dei messaggi di sistema.
        """
        if action == Action.DRAFT:
            raise ValueError(
                "Usare 'send_back_in_draft()' per mandare in Draft il CLACC."
            )

        config = self.ACTION_CONFIGS[action]
        steps = [
            *self._build_base_steps(),
            Step("post", WebCLACCEndpoints.FORM.value, HEADERS_AJAX, data_func=Step.prepare_search_payload, kwargs={'clacc_id': self.clacc_id}),
            Step("post", WebCLACCEndpoints.FORM.value, HEADERS_AJAX, data_func=Step.prepare_select_row_payload, kwargs={'clacc_id': self.clacc_id}),
            Step("post", WebCLACCEndpoints.FORM.value, HEADERS_AJAX, data_func=Step.prepare_action_payload, kwargs={'clacc_id': self.clacc_id, 'button': config.button_name, 'x': config.x, 'y': config.y}),
            Step("post", WebCLACCEndpoints.FORM.value, HEADERS_AJAX, data_func=Step.prepare_modal_ok_payload, kwargs={'clacc_id': self.clacc_id, 'button': 'Button_ModalPanelOK_Cancel_OK'}),
            Step("post", WebCLACCEndpoints.FORM.value, HEADERS_AJAX, data_func=Step.prepare_modal_ok_payload, kwargs={'clacc_id': self.clacc_id, 'button': 'buttonOk'})
        ]

        # Esecuzione steps
        self._run_steps(steps)
        return True

    def fetch_approvers_tab(self) -> pd.DataFrame:
        """
        Recupera la tabella degli approvatori e lo storico delle azioni per il CLACC corrente.
        Naviga nei dettagli del CLACC e, se necessario, forza il cambio di tab verso 'Approvers'.
        """
        self.search_response_html = self._search_by_id()
        response_txt = self.open_clacc_details(self.search_response_html)
        df = soup_to_df(response_txt)
        if df.empty:
            response_tab = self.switch_tab(response_txt, 6)
            df = soup_to_df(response_tab)
        return df

    def open_clacc_details(self, html: str) -> str:
        """
        Esegue il salto dalla lista dei risultati alla pagina di dettaglio (questionario) del CLACC.
        """

        payload = make_form_base_from(
            text=html,
            id_clacc=self.clacc_id,
            eventtarget="ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_LinkButton",
            eventargument="",
        )

        # Pulizia payload: ASP.NET non accetta contemporaneamente la selezione della riga 
        # e il comando di redirect via LinkButton in una singola richiesta Ajax.
        # Rimuoviamo __ASYNCPOST per forzare una risposta che contenga il redirect standard.
        payload.pop("ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_RadioButton", None)
        payload.pop("__ASYNCPOST", None)

        payload["ctl00$ContentPlaceHolder1$ScriptManager1"] = (
            "ctl00$ContentPlaceHolder1$UpdatePanel_CheckApprovers|"
            "ctl00$ContentPlaceHolder1$GridView_CheckApprovers$ctl03$GridView_LinkButton"
        )

        response = self.session.post(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_POST,
            data=payload,
            allow_redirects=True
        )

        return response.text

    def _search_by_id(self) -> str:
        """
        Effettua handshake completo con il portale WebCLACC.

        Sequenza: Login -> Home (DefaultPage) -> Navigazione Menu -> Form di Ricerca.
        Necessario per ottenere i token __VIEWSTATE validi per il contesto 'Monitoring'.
        """

        self.session.get(
            WebCLACCEndpoints.LOGIN.value,
            headers=HEADERS_BASE
        )

        resp_default = self.session.get(
            WebCLACCEndpoints.DEFAULT.value,
            headers=HEADERS_BASE
        )

        self.session.post(
            WebCLACCEndpoints.DEFAULT.value,
            headers=HEADERS_POST,
            data=Step.prepare_menu_payload(resp_default)
        )

        resp_form = self.session.get(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_FORM
        )

        if "SessioneScaduta.aspx" in resp_form.url:
            raise RuntimeError("Sessione scaduta durante bootstrap")

        data = {
            **make_form_base_from(resp_form.text, self.clacc_id),
            **self._payload
        }

        response = self.session.post(
            WebCLACCEndpoints.FORM.value,
            headers=HEADERS_AJAX,
            data=data
        )

        if "pageRedirect" in response.text:
            print("[DEBUG] redirect nel search POST")

        if "0|error|500||" in response.text:
            raise ValueError(
                f"Richiesta malformata per il CLACC {self.clacc_id}"
            )

        return response.text
