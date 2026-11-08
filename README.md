# Value Investing Tool

Assistente per scegliere azioni da tenere nel medio-lungo periodo secondo i principi di
**Benjamin Graham**, **Warren Buffett** e **Charlie Munger**.

## Cosa fa

- **Analizza titolo**: checklist di oltre 20 criteri (qualità del business, solidità
  finanziaria, prezzo), valore intrinseco (DCF sugli *owner earnings*), margine di sicurezza,
  **rendimento annuo atteso**, prezzo massimo d'acquisto e un giudizio:
  `COMPRA` / `OSSERVA` / `VALUE SPECULATIVO` / `EVITA`.
- **Screener**: analizza in blocco un universo di titoli (USA, FTSE MIB, Europa o una lista personalizzata).
- **Portafoglio**: dato il capitale, sceglie i titoli migliori e indica quante azioni comprare,
  con tetti per singolo titolo e per settore. Quando le opportunità sono poche, la parte restante resta in liquidità.
- **Parametri** modificabili: rendimento obiettivo (es. 20%), margine di sicurezza, tasso di sconto, ecc.

## Avvio

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn vit.main:app --reload
```

Aprire <http://127.0.0.1:8000>.

I ticker sono quelli di Yahoo Finance: `KO`, `AAPL`, `ENI.MI` (Milano), `NESN.SW` (Zurigo),
`ULVR.L` (Londra), `MC.PA` (Parigi), `SAP.DE` (Francoforte).

## Test

```powershell
.venv\Scripts\python -m pytest
```

## Struttura

| File | Ruolo |
|---|---|
| `vit/data_provider.py` | Scarica e normalizza i bilanci (yfinance), cache su disco 24 h, conversioni di valuta |
| `vit/analysis.py` | Metriche, checklist Graham/Buffett/Munger, DCF, rendimento atteso, punteggi, giudizio |
| `vit/portfolio.py` | Selezione e pesatura del portafoglio |
| `vit/universes.py` | Liste di titoli predefinite |
| `vit/main.py` | API REST (FastAPI) e servizio dell'interfaccia |
| `frontend/` | Interfaccia web (HTML/CSS/JS, nessuna build) |

Le API (`/api/analyze/{ticker}`, `/api/screen`, `/api/portfolio`) sono pensate per essere
riutilizzate dalla futura app mobile.

## Limiti noti

- Yahoo Finance gratuito fornisce circa 4–5 anni di bilanci; Graham e Buffett ne guardavano 10+.
  Il fornitore di dati è isolato in `data_provider.py` per poter passare a una fonte più completa.
- Il modello non può valutare management, vantaggio competitivo e cerchio di competenza:
  per questo ogni analisi include le domande qualitative da porsi.
- Un rendimento del 20% annuo è un risultato eccezionale, raggiunto da pochissimi investitori:
  il tool aiuta a cercarlo con disciplina, ma non lo garantisce.

## Possibili sviluppi

- Fonte dati con 10+ anni di storico (es. Financial Modeling Prep, EOD Historical Data)
- Universi più ampi (S&P 500 completo, STOXX 600)
- Monitoraggio del portafoglio reale e avvisi quando un titolo in lista d'attesa scende sotto il prezzo d'acquisto
- App mobile (es. React Native / Flutter) basata sulle stesse API

> Strumento didattico e di supporto alle decisioni. Non costituisce consulenza finanziaria.
