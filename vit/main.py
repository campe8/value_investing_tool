"""API web (FastAPI) + interfaccia statica.

Avvio:  .venv\\Scripts\\python -m uvicorn vit.main:app --reload
Poi aprire http://127.0.0.1:8000
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import data_provider
from .analysis import Settings, analyze
from .portfolio import build_portfolio
from .universes import UNIVERSES

app = FastAPI(title="Value Investing Tool", version="0.1.0")


class SettingsIn(BaseModel):
    discount_rate: float = Field(0.10, ge=0.04, le=0.25)
    target_return: float = Field(0.15, ge=0.0, le=0.5)
    min_margin_of_safety: float = Field(0.25, ge=0.0, le=0.9)
    max_growth: float = Field(0.15, ge=0.0, le=0.4)
    terminal_growth: float = Field(0.03, ge=0.0, le=0.05)
    exit_multiple: float = Field(15.0, ge=5, le=40)

    def to_settings(self) -> Settings:
        if self.terminal_growth >= self.discount_rate - 0.01:
            raise HTTPException(422, "La crescita perpetua deve essere almeno 1 punto sotto il tasso di sconto")
        return Settings(**self.model_dump())


class ScreenIn(BaseModel):
    universe: Optional[str] = None
    tickers: list[str] = []
    settings: SettingsIn = SettingsIn()
    refresh: bool = False


class PortfolioIn(ScreenIn):
    capital: float = Field(10000, gt=0)
    base_currency: str = "EUR"
    max_positions: int = Field(10, ge=1, le=30)
    max_weight: float = Field(0.20, gt=0, le=1)
    max_sector: float = Field(0.35, gt=0, le=1)


def _analyze_ticker(ticker: str, s: Settings, refresh: bool = False) -> dict:
    try:
        co = data_provider.get_company(ticker, use_cache=not refresh)
        return analyze(co, s)
    except data_provider.DataError as e:
        return {"ticker": ticker.upper(), "error": str(e)}
    except Exception as e:  # un titolo problematico non deve bloccare lo screening
        return {"ticker": ticker.upper(), "error": f"Errore inatteso: {e}"}


def _resolve_tickers(req: ScreenIn) -> list[str]:
    tickers = [t.strip().upper() for t in req.tickers if t.strip()]
    if req.universe:
        if req.universe not in UNIVERSES:
            raise HTTPException(404, f"Universo '{req.universe}' sconosciuto")
        tickers += UNIVERSES[req.universe]["tickers"]
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        raise HTTPException(400, "Specificare un universo o una lista di ticker")
    if len(tickers) > 150:
        raise HTTPException(400, "Massimo 150 titoli per volta")
    return tickers


def _screen(req: ScreenIn) -> list[dict]:
    s = req.settings.to_settings()
    with ThreadPoolExecutor(max_workers=6) as ex:
        return list(ex.map(lambda t: _analyze_ticker(t, s, req.refresh), _resolve_tickers(req)))


@app.get("/api/universes")
def universes():
    return [{"id": k, "name": v["name"], "count": len(v["tickers"])} for k, v in UNIVERSES.items()]


@app.get("/api/analyze/{ticker}")
def analyze_one(ticker: str, discount_rate: float = 0.10, target_return: float = 0.15,
                min_margin_of_safety: float = 0.25, max_growth: float = 0.15,
                terminal_growth: float = 0.03, exit_multiple: float = 15.0, refresh: bool = False):
    s = SettingsIn(discount_rate=discount_rate, target_return=target_return, min_margin_of_safety=min_margin_of_safety,
                   max_growth=max_growth, terminal_growth=terminal_growth, exit_multiple=exit_multiple).to_settings()
    r = _analyze_ticker(ticker, s, refresh)
    if "error" in r:
        raise HTTPException(404, r["error"])
    return r


@app.post("/api/screen")
def screen(req: ScreenIn):
    results = _screen(req)
    ok = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]
    order = {"COMPRA": 0, "OSSERVA": 1, "VALUE SPECULATIVO": 2, "EVITA": 3, "DATI INSUFFICIENTI": 4}
    ok.sort(key=lambda r: (order.get(r["verdict"], 9), -((r["scores"] or {}).get("totale") or 0)))
    slim = [{k: r[k] for k in ("ticker", "name", "currency", "price", "sector", "verdict", "scores")}
            | {"metrics": {k: r["metrics"].get(k) for k in ("intrinsic_value", "margin_of_safety", "expected_return",
                                                              "buy_below_price", "pe_normalized", "growth_used")}}
            for r in ok]
    return {"results": slim, "errors": errors}


@app.post("/api/portfolio")
def portfolio(req: PortfolioIn):
    results = [r for r in _screen(req) if "error" not in r]
    try:
        return build_portfolio(results, req.capital, req.base_currency.upper(), data_provider.fx_rate,
                               req.max_positions, req.max_weight, req.max_sector)
    except data_provider.DataError as e:
        raise HTTPException(502, str(e))


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
