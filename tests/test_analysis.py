from vit.analysis import Settings, analyze, dcf_value, expected_return, price_for_return
from vit.models import CompanyData, YearData
from vit.portfolio import build_portfolio


def make_company(price=50.0, growth=0.08, sector="Consumer Defensive", ni0=1000.0, years=5) -> CompanyData:
    ys = []
    for i in range(years):
        f = (1 + growth) ** i
        rev = 5000 * f
        ni = ni0 * f
        ys.append(YearData(
            year=2020 + i, revenue=rev, gross_profit=rev * 0.6, operating_income=rev * 0.28, ebit=rev * 0.28,
            net_income=ni, interest_expense=20, pretax_income=ni * 1.25, tax_provision=ni * 0.25,
            diluted_shares=1000 - i * 10, total_assets=8000, current_assets=3000, current_liabilities=1500,
            total_liabilities=3000, total_debt=1000, cash=800, equity=5000, shares=1000 - i * 10,
            operating_cf=ni * 1.2, capex=ni * 0.25, fcf=ni * 0.95, dividends_paid=ni * 0.3, sbc=ni * 0.02,
        ))
    return CompanyData(ticker="TEST", name="Test SpA", currency="EUR", price=price,
                       shares_outstanding=960, market_cap=price * 960, sector=sector, years=ys)


def test_irr_matches_price_for_return():
    s = Settings()
    p = price_for_return(2.0, 0.08, 0.15, s)
    assert abs(expected_return(p, 2.0, 0.08, s) - 0.15) < 1e-6


def test_dcf_increases_with_growth():
    s = Settings()
    assert dcf_value(1.0, 0.10, s) > dcf_value(1.0, 0.02, s)


def test_cheap_quality_company_is_buy():
    r = analyze(make_company(price=12.0))
    assert r["verdict"] == "COMPRA", r["verdict_reason"]
    assert r["metrics"]["margin_of_safety"] > 0.25
    assert r["scores"]["qualita"] >= 65


def test_expensive_quality_company_is_watch():
    r = analyze(make_company(price=200.0))
    assert r["verdict"] == "OSSERVA"
    assert r["metrics"]["buy_below_price"] < 200


def test_loss_making_company_is_avoid():
    co = make_company(price=10.0)
    for y in co.years:
        y.net_income = -100
        y.fcf = -50
    r = analyze(co)
    assert r["verdict"] == "EVITA"


def test_insufficient_data():
    r = analyze(make_company(years=2))
    assert r["verdict"] == "DATI INSUFFICIENTI"


def test_financials_skip_industrial_checks():
    r = analyze(make_company(price=12.0, sector="Financial Services"))
    ids = {c["id"] for c in r["checks"]}
    assert "current_ratio" not in ids and "roa" in ids


def test_portfolio_caps_and_cash():
    results = []
    for i, price in enumerate([10.0, 11.0, 12.0]):
        r = analyze(make_company(price=price))
        r["ticker"] = f"T{i}"
        results.append(r)
    p = build_portfolio(results, 10000, "EUR", lambda a, b: 1.0, max_weight=0.2, max_sector=1.0)
    assert len(p["positions"]) == 3
    assert all(pos["weight"] <= 0.2 + 1e-9 for pos in p["positions"])
    assert p["cash"] >= 10000 * 0.4 - 1e-6


def test_portfolio_sector_cap():
    results = []
    for i, sec in enumerate(["A", "A", "B", "C", "D"]):
        r = analyze(make_company(price=10.0 + i, sector=sec))
        r["ticker"] = f"T{i}"
        results.append(r)
    p = build_portfolio(results, 100000, "EUR", lambda a, b: 1.0, max_weight=0.3, max_sector=0.35)
    sec_a = sum(pos["target_weight"] for pos in p["positions"] if pos["sector"] == "A")
    assert sec_a <= 0.35 + 1e-6
