"""Motore di analisi value investing.

Combina tre scuole di pensiero:
- Benjamin Graham: stabilità degli utili, solidità patrimoniale, prezzo basso
  rispetto a utili e patrimonio (P/E, P/B, Graham Number, net-net).
- Warren Buffett: business eccellenti (alto ROE/ROIC, margini elevati e stabili,
  poco capitale richiesto, debito ripagabile in pochi anni) comprati con margine
  di sicurezza rispetto al valore intrinseco (owner earnings scontati).
- Charlie Munger: qualità prima del prezzo ("un'azienda meravigliosa a un prezzo
  equo"), diffidenza verso diluizione e stock option, concentrazione.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from .models import CompanyData, YearData


@dataclass
class Settings:
    discount_rate: float = 0.10  # rendimento minimo richiesto per scontare i flussi
    target_return: float = 0.15  # rendimento annuo atteso minimo per "COMPRA"
    min_margin_of_safety: float = 0.25  # sconto minimo sul valore intrinseco
    max_growth: float = 0.15  # tetto alla crescita stimata (prudenza)
    terminal_growth: float = 0.03
    exit_multiple: float = 15.0  # multiplo owner earnings a cui si ipotizza di rivendere
    horizon_years: int = 10
    min_quality: float = 65.0
    min_strength: float = 60.0


# --------------------------------------------------------------------------- utilità

def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _vals(years: list[YearData], fn: Callable[[YearData], Optional[float]]) -> list[float]:
    out = []
    for y in years:
        try:
            v = fn(y)
        except (TypeError, ZeroDivisionError):
            v = None
        if v is not None and not math.isnan(v):
            out.append(v)
    return out


def _mean(xs: list[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def cagr(first: Optional[float], last: Optional[float], periods: int) -> Optional[float]:
    if first is None or last is None or periods <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / periods) - 1


def _series_cagr(years: list[YearData], fn) -> Optional[float]:
    pts = [(y.year, fn(y)) for y in years]
    pts = [(yr, v) for yr, v in pts if v is not None]
    if len(pts) < 3:
        return None
    return cagr(pts[0][1], pts[-1][1], pts[-1][0] - pts[0][0])


def _eps(y: YearData) -> Optional[float]:
    return _div(y.net_income, y.diluted_shares or y.shares)


def _fcf(y: YearData) -> Optional[float]:
    if y.fcf is not None:
        return y.fcf
    if y.operating_cf is not None and y.capex is not None:
        return y.operating_cf - y.capex
    return None


def _owner_earnings(y: YearData) -> Optional[float]:
    """FCF meno compensi in azioni: Buffett e Munger considerano le stock option un costo reale."""
    f = _fcf(y)
    if f is None:
        return None
    return f - (y.sbc or 0)


def _tax_rate(y: YearData) -> float:
    r = _div(y.tax_provision, y.pretax_income)
    if r is None or r < 0 or r > 0.5:
        return 0.21
    return r


def _roic(y: YearData) -> Optional[float]:
    ebit = y.ebit if y.ebit is not None else y.operating_income
    if ebit is None or y.equity is None:
        return None
    invested = (y.total_debt or 0) + y.equity - (y.cash or 0)
    if invested <= 0:
        return None
    return ebit * (1 - _tax_rate(y)) / invested


# ----------------------------------------------------------------- valutazione

def project_cash_flows(base: float, growth: float, s: Settings) -> list[float]:
    """Flussi annui: crescita `growth` per metà orizzonte, poi convergenza lineare a quella terminale."""
    flows, cf = [], base
    half = s.horizon_years // 2
    for t in range(1, s.horizon_years + 1):
        if t <= half:
            g = growth
        else:
            frac = (t - half) / (s.horizon_years - half)
            g = growth + (s.terminal_growth - growth) * frac
        cf *= 1 + g
        flows.append(cf)
    return flows


def dcf_value(base: float, growth: float, s: Settings) -> float:
    flows = project_cash_flows(base, growth, s)
    r, tg = s.discount_rate, s.terminal_growth
    pv = sum(cf / (1 + r) ** t for t, cf in enumerate(flows, 1))
    terminal = flows[-1] * (1 + tg) / (r - tg)
    return pv + terminal / (1 + r) ** len(flows)


def price_for_return(base: float, growth: float, rate: float, s: Settings) -> float:
    """Prezzo massimo da pagare oggi per ottenere il rendimento `rate` (uscita al multiplo ipotizzato)."""
    flows = project_cash_flows(base, growth, s)
    pv = sum(cf / (1 + rate) ** t for t, cf in enumerate(flows, 1))
    return pv + flows[-1] * s.exit_multiple / (1 + rate) ** len(flows)


def expected_return(price: float, base: float, growth: float, s: Settings) -> Optional[float]:
    """Rendimento annuo atteso (IRR): compro a `price`, incasso gli owner earnings, rivendo al multiplo di uscita."""
    if price <= 0 or base <= 0:
        return None
    lo, hi = -0.9, 2.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if price_for_return(base, growth, mid, s) > price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def estimate_growth(co: CompanyData, s: Settings) -> tuple[float, dict]:
    ys = co.years
    rev_g = _series_cagr(ys, lambda y: y.revenue)
    eps_g = _series_cagr(ys, _eps)
    oe_g = _series_cagr(ys, _owner_earnings) if not co.is_financial else None
    candidates = [g for g in (rev_g, eps_g, oe_g) if g is not None]
    hist = statistics.median(candidates) if candidates else 0.0

    # Crescita sostenibile = ROE x quota di utili reinvestita
    roes = _vals(ys[-3:], lambda y: _div(y.net_income, y.equity) if (y.equity or 0) > 0 else None)
    payout = _mean(_vals(ys[-3:], lambda y: _div((y.dividends_paid or 0) + (y.buybacks or 0), y.net_income)))
    sustainable = None
    if roes and payout is not None:
        sustainable = _mean(roes) * max(0.0, 1 - min(payout, 1.0))

    g = hist
    # La crescita sostenibile limita quella storica solo se l'azienda non distribuisce quasi tutto
    # (chi riacquista azioni cresce per azione anche senza reinvestire).
    if sustainable is not None and sustainable > 0.03:
        g = min(g, sustainable)
    g = max(0.0, min(g, s.max_growth))
    return g, {"revenue_cagr": rev_g, "eps_cagr": eps_g, "owner_earnings_cagr": oe_g,
               "sustainable_growth": sustainable, "historical_median": hist if candidates else None}


# ----------------------------------------------------------------- checklist

def _check(cid, category, source, label, value, passed, weight, explanation, fmt="pct", threshold=""):
    return {"id": cid, "category": category, "source": source, "label": label, "value": value,
            "passed": passed, "weight": weight, "explanation": explanation, "format": fmt,
            "threshold": threshold}


def _all(xs: list[float], cond) -> Optional[bool]:
    return all(cond(x) for x in xs) if xs else None


def build_checks(co: CompanyData, m: dict, s: Settings) -> list[dict]:
    ys = co.years
    fin = co.is_financial
    c = []

    # ---- QUALITÀ DEL BUSINESS (Buffett / Munger)
    roes = _vals(ys, lambda y: _div(y.net_income, y.equity) if (y.equity or 0) > 0 else None)
    neg_equity = any((y.equity or 0) <= 0 for y in ys if y.equity is not None)
    roe_ok = None if (not roes or neg_equity) else (_mean(roes) >= 0.15 and min(roes) >= 0.10)
    c.append(_check("roe", "qualita", "Buffett", "ROE medio ≥ 15% e mai sotto il 10%", _mean(roes), roe_ok, 2,
                    "Un rendimento sul capitale proprio alto e costante è il segno di un vantaggio competitivo duraturo (moat)."
                    + (" Patrimonio netto negativo (spesso per forti riacquisti): ROE non significativo, si usa il ROIC." if neg_equity else ""),
                    threshold="≥ 15%"))
    if not fin:
        roics = _vals(ys, _roic)
        c.append(_check("roic", "qualita", "Buffett/Munger", "ROIC medio ≥ 12%", _mean(roics),
                        None if not roics else _mean(roics) >= 0.12, 2,
                        "Rendimento sul capitale investito: misura quanto valore crea ogni euro reinvestito nel business.",
                        threshold="≥ 12%"))
        gms = _vals(ys, lambda y: _div(y.gross_profit, y.revenue))
        c.append(_check("gross_margin", "qualita", "Buffett", "Margine lordo medio ≥ 40%", _mean(gms),
                        None if not gms else _mean(gms) >= 0.40, 1,
                        "Margini lordi elevati indicano potere di prezzo: il cliente paga per il marchio o il prodotto, non solo per il costo.",
                        threshold="≥ 40%"))
    oms = _vals(ys, lambda y: _div(y.operating_income, y.revenue))
    stdev = statistics.pstdev(oms) if len(oms) >= 3 else None
    c.append(_check("margin_stability", "qualita", "Buffett", "Margine operativo stabile (dev. std ≤ 5 punti)", stdev,
                    None if stdev is None else stdev <= 0.05, 1,
                    "Margini prevedibili rendono prevedibili gli utili futuri, condizione necessaria per stimarne il valore.",
                    threshold="≤ 5 pt"))
    nis = _vals(ys, lambda y: y.net_income)
    c.append(_check("earnings_stability", "qualita", "Graham", "Utile netto positivo in tutti gli anni", len([x for x in nis if x > 0]),
                    _all(nis, lambda x: x > 0), 2,
                    "Graham richiedeva utili positivi ogni anno: le aziende che vanno in perdita sono difficili da valutare.",
                    fmt="years", threshold=f"{len(nis)}/{len(nis)} anni"))
    if not fin:
        fcfs = _vals(ys, _fcf)
        c.append(_check("fcf_positive", "qualita", "Buffett", "Free cash flow positivo in tutti gli anni", len([x for x in fcfs if x > 0]),
                        _all(fcfs, lambda x: x > 0), 2,
                        "Gli utili contabili contano poco se non diventano cassa: Buffett guarda agli 'owner earnings'.",
                        fmt="years", threshold=f"{len(fcfs)}/{len(fcfs)} anni"))
        capex_ratio = _mean(_vals(ys, lambda y: _div(y.capex, y.net_income) if (y.net_income or 0) > 0 else None))
        c.append(_check("capex_light", "qualita", "Buffett", "Capex ≤ 50% dell'utile netto", capex_ratio,
                        None if capex_ratio is None else capex_ratio <= 0.5, 1,
                        "Un business che non deve reinvestire gran parte degli utili per restare competitivo può distribuirli o farli crescere.",
                        threshold="≤ 50%"))
    rev_g = m["growth_detail"]["revenue_cagr"]
    c.append(_check("revenue_growth", "qualita", "Buffett", "Ricavi in crescita", rev_g,
                    None if rev_g is None else rev_g > 0, 1,
                    "Un'azienda con moat tende ad aumentare le vendite nel tempo.", threshold="> 0%"))
    eps_g = m["growth_detail"]["eps_cagr"]
    c.append(_check("eps_growth", "qualita", "Graham/Buffett", "Utile per azione in crescita ≥ 5% annuo", eps_g,
                    None if eps_g is None else eps_g >= 0.05, 1,
                    "La crescita dell'utile per azione è ciò che, nel lungo periodo, fa salire il valore dell'azione.",
                    threshold="≥ 5%"))
    sh = [y.diluted_shares or y.shares for y in ys if (y.diluted_shares or y.shares)]
    sh_change = cagr(sh[0], sh[-1], len(sh) - 1) if len(sh) >= 2 else None
    c.append(_check("no_dilution", "qualita", "Munger", "Numero di azioni stabile o in calo", sh_change,
                    None if sh_change is None else sh_change <= 0.005, 1,
                    "Riacquisti di azioni a prezzi sensati aumentano la quota di ogni azionista; le emissioni la diluiscono.",
                    threshold="≤ +0,5%/anno"))
    if not fin:
        sbc_ratio = _mean(_vals(ys, lambda y: _div(y.sbc, _fcf(y)) if (_fcf(y) or 0) > 0 and y.sbc is not None else None))
        c.append(_check("sbc", "qualita", "Munger", "Compensi in azioni ≤ 10% del free cash flow", sbc_ratio,
                        None if sbc_ratio is None else sbc_ratio <= 0.10, 0.5,
                        "Munger considerava le stock option un costo nascosto che trasferisce valore dagli azionisti al management.",
                        threshold="≤ 10%"))

    # ---- SOLIDITÀ FINANZIARIA (Graham / Buffett)
    last = ys[-1] if ys else YearData(year=0)
    if not fin:
        cr = _div(last.current_assets, last.current_liabilities)
        c.append(_check("current_ratio", "solidita", "Graham", "Current ratio ≥ 1,5", cr, None if cr is None else cr >= 1.5, 1,
                        "Attività correnti ampiamente superiori alle passività a breve: l'azienda paga i debiti senza affanni. (Graham chiedeva 2.)",
                        fmt="x", threshold="≥ 1,5"))
        de = None
        if last.total_debt is not None and last.equity is not None:
            de = _div(last.total_debt, last.equity) if last.equity > 0 else float("inf")
        c.append(_check("debt_equity", "solidita", "Graham/Buffett", "Debito / patrimonio netto ≤ 0,5", None if de == float("inf") else de,
                        None if de is None else de <= 0.5, 1,
                        "Poco debito significa poter attraversare le crisi senza dover emettere azioni a prezzi stracciati.",
                        fmt="x", threshold="≤ 0,5"))
        avg_oe = m["owner_earnings_avg"]
        net_debt = (last.total_debt or 0) - (last.cash or 0)
        yrs = None
        if net_debt <= 0:
            yrs = 0.0
        elif avg_oe and avg_oe > 0:
            yrs = net_debt / avg_oe
        c.append(_check("debt_payback", "solidita", "Buffett", "Debito netto ripagabile in ≤ 4 anni di cassa", yrs,
                        None if (yrs is None and not avg_oe) else (yrs is not None and yrs <= 4), 2,
                        "Buffett preferisce aziende che potrebbero estinguere i debiti con pochi anni di flussi di cassa.",
                        fmt="years_num", threshold="≤ 4 anni"))
        ebit = last.ebit if last.ebit is not None else last.operating_income
        cov = None
        if ebit is not None:
            cov = 999.0 if not last.interest_expense else ebit / abs(last.interest_expense)
        c.append(_check("interest_coverage", "solidita", "Graham", "Copertura interessi (EBIT / interessi) ≥ 8", cov,
                        None if cov is None else cov >= 8, 1,
                        "Gli interessi devono essere una frazione piccola del reddito operativo.", fmt="x", threshold="≥ 8x"))
    else:
        roas = _vals(ys, lambda y: _div(y.net_income, y.total_assets))
        c.append(_check("roa", "solidita", "Buffett", "ROA medio ≥ 1% (banche/assicurazioni)", _mean(roas),
                        None if not roas else _mean(roas) >= 0.01, 2,
                        "Per le istituzioni finanziarie un ROA ≥ 1% indica redditività senza leva eccessiva.", threshold="≥ 1%"))
        eq_assets = _div(last.equity, last.total_assets)
        c.append(_check("capital_ratio", "solidita", "Graham", "Patrimonio / attivo ≥ 6%", eq_assets,
                        None if eq_assets is None else eq_assets >= 0.06, 1,
                        "Un cuscinetto di capitale adeguato protegge da perdite sui crediti o sugli investimenti.", threshold="≥ 6%"))
    divs = [y.dividends_paid for y in ys]
    div_ok = None if not ys else all((d or 0) > 0 for d in divs)
    c.append(_check("dividend_record", "solidita", "Graham", "Dividendo pagato in tutti gli anni", sum(1 for d in divs if (d or 0) > 0),
                    div_ok, 0.5,
                    "Graham richiedeva una storia ininterrotta di dividendi come prova di solidità (Buffett non lo considera essenziale).",
                    fmt="years", threshold=f"{len(divs)}/{len(divs)} anni"))

    # ---- VALUTAZIONE (prezzo vs valore)
    mos = m["margin_of_safety"]
    c.append(_check("margin_of_safety", "valutazione", "Graham/Buffett",
                    f"Margine di sicurezza ≥ {s.min_margin_of_safety:.0%} sul valore intrinseco", mos,
                    None if mos is None else mos >= s.min_margin_of_safety, 3,
                    "Comprare con ampio sconto sul valore stimato protegge dagli errori di stima e dalla sfortuna.",
                    threshold=f"≥ {s.min_margin_of_safety:.0%}"))
    er = m["expected_return"]
    c.append(_check("expected_return", "valutazione", "Buffett", f"Rendimento annuo atteso ≥ {s.target_return:.0%}", er,
                    None if er is None else er >= s.target_return, 3,
                    f"Stima del rendimento annuo comprando oggi, incassando gli owner earnings e rivendendo dopo {s.horizon_years} anni a {s.exit_multiple:.0f}x.",
                    threshold=f"≥ {s.target_return:.0%}"))
    pe = m["pe_normalized"]
    c.append(_check("pe", "valutazione", "Graham", "P/E (utile medio 3 anni) ≤ 15", pe, None if pe is None else 0 < pe <= 15, 1,
                    "Graham non pagava più di 15 volte gli utili medi recenti.", fmt="x", threshold="≤ 15"))
    pb = m["pb"]
    prod = pe * pb if (pe and pb and pe > 0 and pb > 0) else None
    c.append(_check("graham_product", "valutazione", "Graham", "P/E × P/B ≤ 22,5", prod, None if prod is None else prod <= 22.5, 1,
                    "Regola di Graham: consente un P/E più alto se il prezzo è vicino al patrimonio netto, e viceversa.",
                    fmt="x", threshold="≤ 22,5"))
    gn = m["graham_number"]
    c.append(_check("graham_number", "valutazione", "Graham", "Prezzo ≤ Graham Number", gn, None if gn is None else co.price <= gn, 1,
                    "Graham Number = √(22,5 × EPS × valore contabile per azione): prezzo massimo per un investitore difensivo.",
                    fmt="money", threshold=f"prezzo {co.price:,.2f}" if co.price else ""))
    ncav = m["ncav_per_share"]
    c.append(_check("net_net", "valutazione", "Graham", "Net-net: prezzo ≤ 2/3 del capitale circolante netto", ncav,
                    None if ncav is None or fin else co.price <= ncav * 2 / 3, 0,
                    "Il criterio più estremo di Graham (raro oggi). Informativo: non pesa sul punteggio.", fmt="money"))
    return c


# ----------------------------------------------------------------- analisi completa

QUALITATIVE_QUESTIONS = [
    ("Munger", "Capisco davvero come guadagna questa azienda? È nel mio cerchio di competenza?"),
    ("Buffett", "Ha un vantaggio competitivo duraturo (marchio, costi bassi, effetto rete, costi di cambiamento, licenze)?"),
    ("Buffett", "Sarà ancora rilevante e redditizia tra 10-20 anni? Rischia di essere resa obsoleta dalla tecnologia?"),
    ("Buffett", "Il management è onesto, capace e alloca bene il capitale (riacquisti sotto valore, acquisizioni sensate)?"),
    ("Munger", "Gli incentivi del management sono allineati con gli azionisti?"),
    ("Munger", "Inversione: cosa potrebbe distruggere questo business? Quanto è probabile?"),
    ("Graham", "Se la Borsa chiudesse per 5 anni, sarei tranquillo a possederla?"),
]


def analyze(co: CompanyData, s: Optional[Settings] = None) -> dict:
    s = s or Settings()
    ys = co.years
    out: dict = {
        "ticker": co.ticker, "name": co.name, "currency": co.currency, "price": co.price,
        "sector": co.sector, "industry": co.industry, "country": co.country, "market_cap": co.market_cap,
        "is_financial": co.is_financial, "years_available": len(ys), "settings": asdict(s),
        "qualitative_questions": [{"source": a, "question": q} for a, q in QUALITATIVE_QUESTIONS],
    }
    if len(ys) < 3 or not co.price or not co.shares_outstanding:
        out.update(verdict="DATI INSUFFICIENTI", verdict_reason="Servono almeno 3 anni di bilanci, prezzo e numero di azioni.",
                   scores={"qualita": None, "solidita": None, "valutazione": None, "totale": None},
                   metrics={}, checks=[], history=_history(ys), notes=[])
        return out

    shares = co.shares_outstanding
    recent = ys[-3:]
    # Base dei flussi: owner earnings (FCF - SBC) per le aziende industriali, utile netto per le finanziarie
    if co.is_financial:
        base_total = _mean(_vals(recent, lambda y: y.net_income))
        base_label = "Utile netto medio 3 anni"
    else:
        base_total = _mean(_vals(recent, _owner_earnings))
        base_label = "Owner earnings medi 3 anni (FCF − compensi in azioni)"
    base_ps = _div(base_total, shares)
    growth, gdetail = estimate_growth(co, s)

    intrinsic = er = buy_below = mos = None
    if base_ps and base_ps > 0:
        intrinsic = dcf_value(base_ps, growth, s)
        er = expected_return(co.price, base_ps, growth, s)
        buy_below = min(intrinsic * (1 - s.min_margin_of_safety), price_for_return(base_ps, growth, s.target_return, s))
        mos = (intrinsic - co.price) / intrinsic

    eps_avg = _div(_mean(_vals(recent, lambda y: y.net_income)), shares)
    last = ys[-1]
    bvps = _div(last.equity, shares)
    graham_number = math.sqrt(22.5 * eps_avg * bvps) if (eps_avg and bvps and eps_avg > 0 and bvps > 0) else None
    ncav = None
    if last.current_assets is not None and last.total_liabilities is not None:
        ncav = (last.current_assets - last.total_liabilities) / shares

    metrics = {
        "base_label": base_label,
        "owner_earnings_avg": base_total,
        "owner_earnings_per_share": base_ps,
        "owner_earnings_yield": _div(base_ps, co.price),
        "growth_used": growth,
        "growth_detail": gdetail,
        "intrinsic_value": intrinsic,
        "margin_of_safety": mos,
        "expected_return": er,
        "buy_below_price": buy_below,
        "pe_normalized": _div(co.price, eps_avg),
        "pb": _div(co.price, bvps),
        "graham_number": graham_number,
        "ncav_per_share": ncav,
        "dividend_yield": _div(co.dividend_per_share, co.price),
    }
    checks = build_checks(co, metrics, s)

    scores = {}
    for cat in ("qualita", "solidita", "valutazione"):
        applicable = [ch for ch in checks if ch["category"] == cat and ch["passed"] is not None and ch["weight"] > 0]
        tot = sum(ch["weight"] for ch in applicable)
        scores[cat] = round(100 * sum(ch["weight"] for ch in applicable if ch["passed"]) / tot, 1) if tot else None
    q, st, v = (scores[k] or 0 for k in ("qualita", "solidita", "valutazione"))
    scores["totale"] = round(0.45 * q + 0.20 * st + 0.35 * v, 1)

    quality_ok = q >= s.min_quality and st >= s.min_strength
    value_ok = mos is not None and er is not None and mos >= s.min_margin_of_safety and er >= s.target_return
    if base_ps is None or base_ps <= 0:
        verdict, reason = "EVITA", "Flussi di cassa per l'azionista negativi o assenti: impossibile stimare un valore intrinseco prudente."
    elif quality_ok and value_ok:
        verdict, reason = "COMPRA", "Azienda di qualità, finanziariamente solida, a un prezzo con margine di sicurezza adeguato."
    elif quality_ok:
        verdict, reason = "OSSERVA", "Ottima azienda ma il prezzo attuale non offre abbastanza margine: attendere un prezzo migliore."
    elif value_ok and st >= s.min_strength:
        verdict, reason = "VALUE SPECULATIVO", "Prezzo molto basso ma qualità del business sotto soglia (stile 'cicca di sigaro' di Graham): rischio più alto."
    else:
        verdict, reason = "EVITA", "Non soddisfa insieme i criteri di qualità, solidità e prezzo."

    notes = []
    if len(ys) < 7:
        notes.append(f"Storico disponibile: {len(ys)} anni. Graham e Buffett guardavano 10 anni: verifica la storia completa nei bilanci.")
    if co.is_financial:
        notes.append("Settore finanziario: valutazione basata sugli utili; alcuni indicatori industriali non sono applicabili.")
    if growth >= s.max_growth:
        notes.append(f"La crescita storica è stata limitata al {s.max_growth:.0%} per prudenza.")

    out.update(verdict=verdict, verdict_reason=reason, scores=scores, metrics=metrics, checks=checks,
               history=_history(ys), notes=notes)
    return out


def _history(ys: list[YearData]) -> list[dict]:
    return [{
        "year": y.year,
        "revenue": y.revenue,
        "net_income": y.net_income,
        "eps": _eps(y),
        "fcf": _fcf(y),
        "owner_earnings": _owner_earnings(y),
        "gross_margin": _div(y.gross_profit, y.revenue),
        "operating_margin": _div(y.operating_income, y.revenue),
        "roe": _div(y.net_income, y.equity) if (y.equity or 0) > 0 else None,
        "roic": _roic(y),
        "debt": y.total_debt,
        "shares": y.diluted_shares or y.shares,
    } for y in ys]
