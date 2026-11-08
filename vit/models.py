"""Strutture dati normalizzate, indipendenti dal fornitore dei dati."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Optional


@dataclass
class YearData:
    """Dati di bilancio annuali (valori monetari nella valuta di quotazione)."""

    year: int
    # Conto economico
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ebit: Optional[float] = None
    net_income: Optional[float] = None
    interest_expense: Optional[float] = None
    pretax_income: Optional[float] = None
    tax_provision: Optional[float] = None
    diluted_shares: Optional[float] = None
    # Stato patrimoniale
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    equity: Optional[float] = None
    goodwill_intangibles: Optional[float] = None
    shares: Optional[float] = None
    # Flussi di cassa
    operating_cf: Optional[float] = None
    capex: Optional[float] = None  # valore positivo = denaro speso
    fcf: Optional[float] = None
    dividends_paid: Optional[float] = None  # valore positivo = denaro distribuito
    buybacks: Optional[float] = None  # valore positivo = denaro speso
    sbc: Optional[float] = None
    d_and_a: Optional[float] = None


@dataclass
class CompanyData:
    ticker: str
    name: str
    currency: str
    price: Optional[float]
    shares_outstanding: Optional[float]
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    dividend_per_share: Optional[float] = None
    years: list[YearData] = field(default_factory=list)  # dal più vecchio al più recente

    @property
    def is_financial(self) -> bool:
        text = f"{self.sector or ''} {self.industry or ''}".lower()
        return any(k in text for k in ("financial", "bank", "insurance", "capital markets"))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CompanyData":
        d = dict(d)
        yfields = {f.name for f in fields(YearData)}
        d["years"] = [YearData(**{k: v for k, v in y.items() if k in yfields}) for y in d.get("years", [])]
        cfields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in cfields})
