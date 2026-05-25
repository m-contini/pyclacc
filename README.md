# PyCLACC: Automation Tool

[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Panoramica

PyCLACC è una soluzione di automazione progettata per ottimizzare il processo di screening dei **CLACC** (Risk Assessment preliminari alla revisione legale dei bilanci).
Il sistema funge da ponte intelligente tra Salesforce (**DForce1**) e il portale **WebCLACC**, eliminando l'onere delle verifiche manuali incrociate e garantendo la coerenza dei dati tra le piattaforme.

## Vantaggio dell'automazione

Il processo di screening dei risk assessment è storicamente caratterizzato da un'alta intensità di lavoro manuale.  
PyCLACC trasforma radicalmente questo workflow.

Senza tool, un operatore dovrebbe infatti:

| Attività Manuale | Validazione Automatizzata |
| :--- | :--- |
| **Accesso frammentato:** Apertura manuale di decine di schede browser tra Salesforce e WebCLACC. | **Aggregazione Unificata:** Tutti i dati necessari sono pronti in un'unica schermata interattiva. |
| **Cross-Check visivo:** Confronto umano di nomi, ruoli (Partner/Manager) e anni fiscali per ogni pratica. | **Highlighting delle Anomalie:** Il sistema evidenzia istantaneamente discrepanze e incongruenze logiche. |
| **Data Entry ripetitivo:** Inserimento manuale di esiti e motivazioni sui portali istituzionali. | **One-Click Action:** Esecuzione massiva di azioni (Approvazione/Rigetto) sincronizzata via API/Web. |

## Funzionalità Principali

Il successo dell'automazione poggia su due processi coordinati che garantiscono l'integrità del dato e la velocità di esecuzione:

### 1. Estrazione dati (`Download.py`)

Questo script è configurato nel **Task Scheduler** di Windows per l'esecuzione oraria.  
**Prerequisiti:** Connessione VPN attiva e credenziali configurate nel file di sicurezza `.env`.

* **Cosa fa:** Si autentica sui portali, scarica le estrazioni aggiornate e sincronizza i dati con quelli locali.
* **Obiettivo:** Garantire che l'utente lavori sempre su dati reali senza dover attendere tempi tecnici di download manuale e ripetute pulizie manuali delle estrazioni ricavate via browser.

### 2. Flusso di Review dei CLACC (`ReadWeb.py`)

* **Cosa fa:** Carica i dati aggiornati, effettua il "matching" automatico tra CLACC e Salesforce e presenta a schermo delle schede informative sintetiche esaustive.
* **Azioni:** Abilita la validazione dei dati e l'invio di comandi diretti al portale WebCLACC (Approvazione, Rigetto, Invio in Draft) senza mai uscire dall'interfaccia.

## Risultati Ottenuti

* **Efficienza Operativa:** Riduzione drastica dei tempi di elaborazione, permettendo di gestire volumi elevati di pratiche con meno risorse.
* **Qualità del Dato:** Eliminazione degli errori di svista nel confronto tra sistemi diversi.

---

## Configurazione locale

Prima del primo avvio, bisogna personalizzare il file `config.yaml`:

* Impostare il proprio `DESKTOP_PATH` (es. `C:\Users\m-contini\Desktop`).
* Verificare ed eventualmente aggiornare i parametri di business (leaders, LMU, ecc.) per adattare il tool al proprio caso.

## Avvio

L'ambiente locale deve disporre delle librerie installate:

```bash
pip install -r requirements.txt
```

1. Assicurarsi di essere connessi alla VPN aziendale.
2. Configurare le credenziali nel file `.env`.
3. Per avviare la sessione di review:

   ```bash
   # Scarica dati aggiornati in tempo reale prima di avviare la sessione
   python ./scripts/ReadWeb.py csv
   # Continua dal punto in cui si è interrotta la precedente sessione
   python ./scripts/ReadWeb.py
   ```

4. Seguire la procedura guidata per validare i CLACC in coda.
5. **Output:** Alla chiusura, il sistema genererà automaticamente un report Excel (`XLSX`) pronto per stakeholder e manager, contenente il riepilogo analitico delle attività svolte e i relativi tempi di esecuzione.

Per avviare manualmente l'istanza di download massivo:

```bash
# Download sequenziale
python ./scripts/Download.py
# Download parallelo
python ./scripts/Download.py concurrent
