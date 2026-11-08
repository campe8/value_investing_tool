"""Recupero dati da Yahoo Finance (yfinance) con cache su disco.

Il resto dell'applicazione usa solo `get_company()` e `fx_rate()`: per passare
in futuro a un fornitore a pagamento (es. 10+ anni di storico) basta
reimplementare queste due funzioni.
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Optional

from .models import CompanyData, YearData

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_TTL_SECONDS = 24 * 3600

# Valute quotate in sottounità (es. pence): (valuta reale, divisore)
SUBUNIT_CURRENCIES = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ILA": ("ILS", 100), "ZAc": ("ZAR", 100)}

INCOME_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported", "EBIT"],
    "ebit": ["EBIT", "Operating Income"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "pretax_income": ["Pretax Income"],
    "tax_provision": ["Tax Provision"],
    "diluted_shares": ["Diluted Average Shares", "Basic Average Shares"],
}
BALANCE_MAP = {
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "total_liabilities": ["Total Liabilities Net Minority Interest"],
    "total_debt": ["Total Debt"],
    "cash": ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"],
    "equity": ["Stockholders Equity", "Common Stock Equity"],
    "goodwill_intangibles": ["Goodwill And Other Intangible Assets", "Goodwill"],
    "shares": ["Ordinary Shares Number", "Share Issued"],
}
CASHFLOW_MAP = {
    "operating_cf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure", "Purchase Of PPE"],
    "fcf": ["Free Cash Flow"],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "buybacks": ["Repurchase Of Capital Stock", "Common Stock Payments"],
    "sbc": ["Stock Based Compensation"],
    "d_and_a": ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
}
# Campi che vanno girati di segno (uscite di cassa riportate come negative)
OUTFLOW_FIELDS = {"capex", "dividends_paid", "buybacks"}
NON_MONETARY_FIELDS = {"year", "diluted_shares", "shares"}

_lock = threading.Lock()


class DataError(Exception):
    pass


def _clean(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _cache_path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return CACHE_DIR / f"{safe}.json"


def _cache_get(key: str, ttl: int = CACHE_TTL_SECONDS):
    p = _cache_path(key)
    try:
        if p.exists() and time.time() - p.stat().st_mtime < ttl:
            return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def _cache_set(key: str, value) -> None:
    with _lock:
        CACHE_DIR.mkdir(exist_ok=True)
        _cache_path(key).write_text(json.dumps(value), encoding="utf-8")


def _extract(df, mapping: dict, by_year: dict) -> None:
    if df is None or getattr(df, "empty", True):
        return
    for col in df.columns:
        year = int(getattr(col, "year", 0) or 0)
        if not year:
            continue
        row = by_year.setdefault(year, {"year": year})
        for fname, labels in mapping.items():
            if row.get(fname) is not None:
                continue
            for label in labels:
                if label in df.index:
                    val = _clean(df.at[label, col])
                    if val is not None:
                        if fname in OUTFLOW_FIELDS:
                            val = abs(val)
                        row[fname] = val
                        break


def fx_rate(src: str, dst: str) -> float:
    """Tasso per convertire 1 unità di `src` in `dst`."""
    if not src or not dst or src.upper() == dst.upper():
        return 1.0
    src, dst = src.upper(), dst.upper()
    key = f"fx_{src}{dst}"
    cached = _cache_get(key, ttl=6 * 3600)
    if cached is not None:
        return cached
    import yfinance as yf

    hist = yf.Ticker(f"{src}{dst}=X").history(period="5d")
    if hist is None or hist.empty:
        raise DataError(f"Tasso di cambio {src}/{dst} non disponibile")
    rate = float(hist["Close"].dropna().iloc[-1])
    _cache_set(key, rate)
    return rate


def get_company(ticker: str, use_cache: bool = True) -> CompanyData:
    ticker = ticker.strip().upper()
    if not ticker:
        raise DataError("Ticker vuoto")
    if use_cache:
        cached = _cache_get(f"co_{ticker}")
        if cached is not None:
            return CompanyData.from_dict(cached)

    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception as e:  # yfinance solleva eccezioni eterogenee
        raise DataError(f"Impossibile scaricare i dati di {ticker}: {e}") from e

    price = _clean(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    if price is None:
        raise DataError(f"Ticker {ticker} non trovato o senza prezzo")

    currency = info.get("currency") or "USD"
    market_cap = _clean(info.get("marketCap"))
    if currency in SUBUNIT_CURRENCIES:
        currency, div = SUBUNIT_CURRENCIES[currency]
        price /= div
        # Nota: Yahoo riporta il market cap già nella valuta principale (es. GBP, non pence)

    by_year: dict[int, dict] = {}
    try:
        _extract(t.income_stmt, INCOME_MAP, by_year)
        _extract(t.balance_sheet, BALANCE_MAP, by_year)
        _extract(t.cashflow, CASHFLOW_MAP, by_year)
    except Exception as e:
        raise DataError(f"Bilanci di {ticker} non disponibili: {e}") from e

    years = [YearData(**row) for _, row in sorted(by_year.items())]
    # Scarta anni quasi vuoti (yfinance a volte aggiunge una colonna parziale)
    years = [y for y in years if y.revenue is not None or y.net_income is not None]

    fin_currency = info.get("financialCurrency") or currency
    if fin_currency in SUBUNIT_CURRENCIES:
        fin_currency, div = SUBUNIT_CURRENCIES[fin_currency]
        years = [_scale(y, 1 / div) for y in years]
    if fin_currency.upper() != currency.upper():
        rate = fx_rate(fin_currency, currency)
        years = [_scale(y, rate) for y in years]

    # Azioni "implicite" = capitalizzazione / prezzo: gestisce correttamente ADR e
    # classi multiple (es. BRK-B), dove sharesOutstanding non è confrontabile col prezzo.
    shares = _clean(info.get("sharesOutstanding"))
    if market_cap and price:
        implied = market_cap / price
        # Protezione da incoerenze di unità (pence/sterline ecc.): se l'implicito differisce
        # di ~100x dal dato ufficiale, si usa il dato ufficiale.
        if not shares or 0.2 < implied / shares < 5:
            shares = implied
    if shares and price:
        market_cap = shares * price

    div_rate = _clean(info.get("dividendRate"))
    co = CompanyData(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        currency=currency,
        price=price,
        shares_outstanding=shares,
        market_cap=market_cap,
        sector=info.get("sector"),
        industry=info.get("industry"),
        country=info.get("country"),
        dividend_per_share=div_rate,
        years=years,
    )
    _cache_set(f"co_{ticker}", co.to_dict())
    return co


def _scale(y: YearData, factor: float) -> YearData:
    d = y.__dict__.copy()
    for k, v in d.items():
        if k not in NON_MONETARY_FIELDS and v is not None:
            d[k] = v * factor
    return YearData(**d)
