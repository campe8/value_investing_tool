"""Costruzione del portafoglio a partire dai titoli analizzati.

Filosofia: portafoglio concentrato (Munger: "la diversificazione è una protezione
contro l'ignoranza"), ma con tetti per singolo titolo e per settore. Se pochi
titoli superano i criteri, la parte restante resta in liquidità: Buffett preferisce
aspettare piuttosto che comprare a prezzi sbagliati.
"""
from __future__ import annotations

from typing import Callable, Optional


def rank_key(r: dict) -> float:
    er = (r.get("metrics") or {}).get("expected_return") or 0
    q = (r.get("scores") or {}).get("qualita") or 0
    return er * (q / 100)


def _apply_caps(weights: dict[str, float], sectors: dict[str, str], max_weight: float, max_sector: float) -> dict[str, float]:
    w = dict(weights)
    for _ in range(100):
        changed = False
        for k in w:
            if w[k] > max_weight + 1e-9:
                w[k] = max_weight
                changed = True
        by_sector: dict[str, float] = {}
        for k, v in w.items():
            by_sector[sectors[k]] = by_sector.get(sectors[k], 0) + v
        for sec, tot in by_sector.items():
            if tot > max_sector + 1e-9:
                f = max_sector / tot
                for k in w:
                    if sectors[k] == sec:
                        w[k] *= f
                changed = True
        # Ridistribuisce l'eccedenza sui titoli che hanno ancora spazio
        free = 1 - sum(w.values())
        by_sector = {}
        for k, v in w.items():
            by_sector[sectors[k]] = by_sector.get(sectors[k], 0) + v
        room = [k for k in w if w[k] < max_weight - 1e-9 and by_sector[sectors[k]] < max_sector - 1e-9]
        if free > 1e-6 and room:
            base = sum(weights[k] for k in room)
            for k in room:
                w[k] += free * weights[k] / base
            changed = True
        if not changed:
            break
    return w


def build_portfolio(results: list[dict], capital: float, base_currency: str,
                    fx: Callable[[str, str], float], max_positions: int = 10,
                    max_weight: float = 0.20, max_sector: float = 0.35,
                    cash_return: float = 0.02) -> dict:
    candidates = sorted((r for r in results if r.get("verdict") == "COMPRA"), key=rank_key, reverse=True)
    selected = candidates[:max_positions]
    watch = sorted((r for r in results if r.get("verdict") == "OSSERVA"), key=lambda r: (r.get("scores") or {}).get("totale") or 0,
                   reverse=True)[:10]

    if not selected:
        return {"positions": [], "cash": capital, "cash_weight": 1.0, "invested": 0.0, "base_currency": base_currency,
                "expected_return_invested": None, "expected_return_total": cash_return,
                "watchlist": [_watch_row(r) for r in watch],
                "message": "Nessun titolo soddisfa oggi tutti i criteri. Meglio restare liquidi e attendere prezzi migliori."}

    raw = {r["ticker"]: max(rank_key(r), 1e-6) for r in selected}
    total = sum(raw.values())
    raw = {k: v / total for k, v in raw.items()}
    sectors = {r["ticker"]: r.get("sector") or "Altro" for r in selected}
    weights = _apply_caps(raw, sectors, max_weight, max_sector)

    positions, invested = [], 0.0
    for r in selected:
        rate = fx(r["currency"], base_currency)
        price_base = r["price"] * rate
        target_amount = capital * weights[r["ticker"]]
        n = int(target_amount // price_base) if price_base > 0 else 0
        amount = n * price_base
        invested += amount
        m = r["metrics"]
        positions.append({
            "ticker": r["ticker"], "name": r["name"], "sector": sectors[r["ticker"]], "currency": r["currency"],
            "price": r["price"], "price_base": price_base, "shares": n, "amount": amount,
            "target_weight": weights[r["ticker"]], "weight": amount / capital if capital else 0,
            "expected_return": m.get("expected_return"), "margin_of_safety": m.get("margin_of_safety"),
            "intrinsic_value": m.get("intrinsic_value"), "buy_below_price": m.get("buy_below_price"),
            "quality": r["scores"]["qualita"], "score": r["scores"]["totale"],
        })
    cash = capital - invested
    er_inv = sum(p["amount"] * (p["expected_return"] or 0) for p in positions) / invested if invested else None
    er_tot = ((er_inv or 0) * invested + cash_return * cash) / capital if capital else None
    msg = None
    if len(selected) < 5:
        msg = (f"Solo {len(selected)} titoli superano tutti i criteri: la quota non investita resta in liquidità "
               "in attesa di nuove opportunità.")
    return {"positions": positions, "cash": cash, "cash_weight": cash / capital if capital else 0, "invested": invested,
            "base_currency": base_currency, "expected_return_invested": er_inv, "expected_return_total": er_tot,
            "watchlist": [_watch_row(r) for r in watch], "message": msg}


def _watch_row(r: dict) -> dict:
    m = r.get("metrics") or {}
    return {"ticker": r["ticker"], "name": r["name"], "currency": r["currency"], "price": r["price"],
            "buy_below_price": m.get("buy_below_price"), "expected_return": m.get("expected_return"),
            "quality": (r.get("scores") or {}).get("qualita")}
