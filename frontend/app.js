"use strict";

// ---------------------------------------------------------------- parametri
const DEFAULTS = {
  target_return: 0.15, min_margin_of_safety: 0.25, discount_rate: 0.10,
  max_growth: 0.15, terminal_growth: 0.03, exit_multiple: 15,
};
const PCT_FIELDS = ["target_return", "min_margin_of_safety", "discount_rate", "max_growth", "terminal_growth"];

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem("vit-settings") || "{}");
    return { ...DEFAULTS, ...s };
  } catch { return { ...DEFAULTS }; }
}
function saveSettings(s) {
  try { localStorage.setItem("vit-settings", JSON.stringify(s)); } catch { /* storage non disponibile */ }
}
let settings = loadSettings();

// ---------------------------------------------------------------- formattazione
const nf = (d = 2) => new Intl.NumberFormat("it-IT", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtNum = (v, d = 2) => (v == null || !isFinite(v) ? "–" : nf(d).format(v));
const fmtPct = (v, d = 1) => (v == null || !isFinite(v) ? "–" : nf(d).format(v * 100) + "%");
const fmtMoney = (v, cur, d = 2) => (v == null || !isFinite(v) ? "–" : `${nf(d).format(v)} ${cur || ""}`.trim());
function fmtBig(v) {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e12) return nf(2).format(v / 1e12) + " T";
  if (a >= 1e9) return nf(2).format(v / 1e9) + " Mld";
  if (a >= 1e6) return nf(1).format(v / 1e6) + " Mln";
  return nf(0).format(v);
}
const cls = (v) => (v == null ? "" : v >= 0 ? "pos" : "neg");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const verdictClass = (v) => "v-" + String(v).replace(/\s+/g, "-");
const badge = (v, big) => `<span class="badge ${big ? "big " : ""}${verdictClass(v)}">${esc(v)}</span>`;

function fmtCheckValue(c, cur) {
  const v = c.value;
  switch (c.format) {
    case "pct": return fmtPct(v);
    case "x": return v != null && v >= 999 ? "nessun debito" : fmtNum(v, 1) + (v != null ? "x" : "");
    case "years": return v == null ? "–" : `${v} anni`;
    case "years_num": return v == null ? "–" : v === 0 ? "cassa netta" : `${fmtNum(v, 1)} anni`;
    case "money": return fmtMoney(v, cur);
    default: return fmtNum(v);
  }
}

// ---------------------------------------------------------------- API
async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `Errore ${res.status}`);
  return data;
}
const settingsQuery = () => new URLSearchParams(Object.entries(settings).map(([k, v]) => [k, String(v)])).toString();

// ---------------------------------------------------------------- tabs
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  try { localStorage.setItem("vit-tab", name); } catch { /* ignora */ }
}
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));

// ---------------------------------------------------------------- analisi singola
const analyzeForm = document.getElementById("analyze-form");
const analyzeOut = document.getElementById("analyze-result");

async function runAnalyze(ticker) {
  ticker = ticker.trim().toUpperCase();
  if (!ticker) return;
  document.getElementById("ticker-input").value = ticker;
  showTab("analyze");
  analyzeOut.innerHTML = `<div class="loading">Analisi di ${esc(ticker)} in corso…</div>`;
  const refresh = document.getElementById("analyze-refresh").checked;
  try {
    const r = await api(`/api/analyze/${encodeURIComponent(ticker)}?${settingsQuery()}${refresh ? "&refresh=true" : ""}`);
    analyzeOut.innerHTML = renderAnalysis(r);
    bindQuestions(r.ticker);
  } catch (e) {
    analyzeOut.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}
analyzeForm.addEventListener("submit", (e) => { e.preventDefault(); runAnalyze(document.getElementById("ticker-input").value); });

function scoreBar(label, v) {
  const color = v == null ? "var(--muted)" : v >= 70 ? "var(--good)" : v >= 50 ? "var(--warn)" : "var(--bad)";
  return `<div class="score"><div class="row"><span>${label}</span><strong>${v == null ? "–" : nf(0).format(v)}/100</strong></div>
    <div class="bar"><span style="width:${v ?? 0}%;background:${color}"></span></div></div>`;
}

function renderChecks(checks, cat, cur) {
  const items = checks.filter((c) => c.category === cat);
  if (!items.length) return "";
  return items.map((c) => {
    const icon = c.passed === true ? `<span class="icon ok">✓</span>` : c.passed === false ? `<span class="icon ko">✗</span>` : `<span class="icon na">–</span>`;
    return `<div class="check">${icon}
      <div><span class="lbl">${esc(c.label)}</span><span class="src">${esc(c.source)}</span>
        <div class="exp">${esc(c.explanation)}</div></div>
      <div class="v">${fmtCheckValue(c, cur)}${c.threshold ? `<small>soglia ${esc(c.threshold)}</small>` : ""}${c.weight === 0 ? "<small>informativo</small>" : ""}</div>
    </div>`;
  }).join("");
}

function renderAnalysis(r) {
  const m = r.metrics || {};
  const cur = r.currency;
  const s = r.scores || {};
  let html = `<div class="card">
    <div class="company-head">
      <div>
        <h2>${esc(r.name)} <span class="hint">(${esc(r.ticker)})</span></h2>
        <div class="sub">${esc([r.sector, r.industry, r.country].filter(Boolean).join(" · "))} · Capitalizzazione ${fmtBig(r.market_cap)} ${esc(cur)}</div>
      </div>
      <div style="text-align:right">
        <div class="price">${fmtMoney(r.price, cur)}</div>
        ${badge(r.verdict, true)}
      </div>
    </div>
    <div class="verdict-box">${esc(r.verdict_reason)}</div>`;
  if (r.verdict !== "DATI INSUFFICIENTI") {
    html += `<div class="kpis">
      <div class="kpi"><div class="lbl">Valore intrinseco stimato</div><div class="val">${fmtMoney(m.intrinsic_value, cur)}</div></div>
      <div class="kpi"><div class="lbl">Margine di sicurezza</div><div class="val ${cls(m.margin_of_safety)}">${fmtPct(m.margin_of_safety)}</div></div>
      <div class="kpi"><div class="lbl">Rendimento annuo atteso</div><div class="val ${m.expected_return != null && m.expected_return >= settings.target_return ? "pos" : "neg"}">${fmtPct(m.expected_return)}</div></div>
      <div class="kpi"><div class="lbl">Prezzo d'acquisto massimo</div><div class="val">${fmtMoney(m.buy_below_price, cur)}</div></div>
      <div class="kpi"><div class="lbl">Crescita ipotizzata</div><div class="val">${fmtPct(m.growth_used)}</div></div>
      <div class="kpi"><div class="lbl">Rendimento owner earnings</div><div class="val">${fmtPct(m.owner_earnings_yield)}</div></div>
      <div class="kpi"><div class="lbl">P/E normalizzato</div><div class="val">${fmtNum(m.pe_normalized, 1)}</div></div>
      <div class="kpi"><div class="lbl">Graham Number</div><div class="val">${fmtMoney(m.graham_number, cur)}</div></div>
    </div>`;
  }
  html += `</div>`;
  if (r.verdict === "DATI INSUFFICIENTI") return html;

  html += `<div class="card"><h2>Punteggi</h2><div class="scores">
    ${scoreBar("Qualità del business", s.qualita)}${scoreBar("Solidità finanziaria", s.solidita)}
    ${scoreBar("Convenienza del prezzo", s.valutazione)}${scoreBar("Totale", s.totale)}</div></div>`;

  html += `<div class="grid-2">
    <div class="card"><h2>Qualità del business</h2>${renderChecks(r.checks, "qualita", cur)}</div>
    <div>
      <div class="card"><h2>Solidità finanziaria</h2>${renderChecks(r.checks, "solidita", cur)}</div>
      <div class="card"><h2>Prezzo e valutazione</h2>${renderChecks(r.checks, "valutazione", cur)}</div>
    </div>
  </div>`;

  const gd = m.growth_detail || {};
  html += `<div class="card"><h2>Come è stata stimata la crescita</h2>
    <div class="summary-row">
      <span class="pill">Ricavi: ${fmtPct(gd.revenue_cagr)}/anno</span>
      <span class="pill">Utile per azione: ${fmtPct(gd.eps_cagr)}/anno</span>
      <span class="pill">Owner earnings: ${fmtPct(gd.owner_earnings_cagr)}/anno</span>
      <span class="pill">Crescita sostenibile (ROE × reinvestimento): ${fmtPct(gd.sustainable_growth)}</span>
      <span class="pill"><strong>Usata: ${fmtPct(m.growth_used)}</strong></span>
    </div>
    <p class="hint">Base dei flussi: ${esc(m.base_label)} = ${fmtMoney(m.owner_earnings_per_share, cur)} per azione.
      La crescita si mantiene per 5 anni e poi rallenta fino al ${fmtPct(settings.terminal_growth)} perpetuo, con flussi scontati al ${fmtPct(settings.discount_rate)}.</p>
  </div>`;

  html += `<div class="card"><h2>Storico finanziario</h2><div class="table-wrap"><table>
    <thead><tr><th>Anno</th><th class="num">Ricavi</th><th class="num">Utile netto</th><th class="num">EPS</th>
      <th class="num">Free cash flow</th><th class="num">Margine lordo</th><th class="num">Margine operativo</th>
      <th class="num">ROE</th><th class="num">ROIC</th><th class="num">Debito</th><th class="num">Azioni</th></tr></thead><tbody>
    ${r.history.map((h) => `<tr><td>${h.year}</td><td class="num">${fmtBig(h.revenue)}</td><td class="num">${fmtBig(h.net_income)}</td>
      <td class="num">${fmtNum(h.eps)}</td><td class="num">${fmtBig(h.fcf)}</td><td class="num">${fmtPct(h.gross_margin)}</td>
      <td class="num">${fmtPct(h.operating_margin)}</td><td class="num">${fmtPct(h.roe)}</td><td class="num">${fmtPct(h.roic)}</td>
      <td class="num">${fmtBig(h.debt)}</td><td class="num">${fmtBig(h.shares)}</td></tr>`).join("")}
    </tbody></table></div><p class="hint">Valori in ${esc(cur)}.</p></div>`;

  html += `<div class="grid-2">
    <div class="card"><h2>Domande che i numeri non possono rispondere</h2>
      <p class="hint">Rispondi onestamente prima di investire. Le spunte vengono salvate nel browser.</p>
      <ul class="questions" style="list-style:none;padding:0">
      ${r.qualitative_questions.map((q, i) => `<li><label><input type="checkbox" data-q="${i}">
        <span>${esc(q.question)} <span class="hint">(${esc(q.source)})</span></span></label></li>`).join("")}
      </ul></div>
    <div class="card"><h2>Note</h2><ul class="notes">${(r.notes || []).map((n) => `<li>${esc(n)}</li>`).join("") || "<li>Nessuna nota.</li>"}
      <li>Non è consulenza finanziaria: verifica sempre i dati nei bilanci ufficiali.</li></ul></div>
  </div>`;
  return html;
}

function bindQuestions(ticker) {
  const key = "vit-q-" + ticker;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch { /* ignora */ }
  analyzeOut.querySelectorAll("input[data-q]").forEach((cb) => {
    cb.checked = !!saved[cb.dataset.q];
    cb.addEventListener("change", () => {
      saved[cb.dataset.q] = cb.checked;
      try { localStorage.setItem(key, JSON.stringify(saved)); } catch { /* ignora */ }
    });
  });
}

// ---------------------------------------------------------------- universi
async function loadUniverses() {
  try {
    const list = await api("/api/universes");
    const opts = list.map((u) => `<option value="${esc(u.id)}">${esc(u.name)} (${u.count})</option>`).join("");
    document.getElementById("screen-universe").innerHTML = `<option value="">— nessuno (solo ticker aggiuntivi) —</option>` + opts;
    document.getElementById("pf-universe").innerHTML = `<option value="">— nessuno (solo ticker aggiuntivi) —</option>` + opts;
    document.getElementById("screen-universe").value = list[0]?.id || "";
    document.getElementById("pf-universe").value = list[0]?.id || "";
  } catch (e) { console.error(e); }
}
const parseTickers = (s) => s.split(/[\s,;]+/).map((t) => t.trim()).filter(Boolean);

// ---------------------------------------------------------------- screener
document.getElementById("screen-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = document.getElementById("screen-result");
  const btn = e.submitter; btn.disabled = true;
  out.innerHTML = `<div class="loading">Screening in corso… l'operazione può richiedere qualche minuto.</div>`;
  try {
    const data = await api("/api/screen", {
      universe: document.getElementById("screen-universe").value || null,
      tickers: parseTickers(document.getElementById("screen-tickers").value),
      settings,
    });
    out.innerHTML = renderScreen(data);
    out.querySelectorAll("tr[data-ticker]").forEach((tr) => tr.addEventListener("click", () => runAnalyze(tr.dataset.ticker)));
  } catch (err) {
    out.innerHTML = `<div class="error">${esc(err.message)}</div>`;
  } finally { btn.disabled = false; }
});

function renderScreen(data) {
  const counts = {};
  data.results.forEach((r) => (counts[r.verdict] = (counts[r.verdict] || 0) + 1));
  let html = `<div class="summary-row">${Object.entries(counts).map(([v, n]) => `${badge(v)} <span class="hint">${n}</span>`).join(" ")}</div>`;
  html += `<div class="card"><div class="table-wrap"><table><thead><tr>
    <th>Titolo</th><th>Giudizio</th><th class="num">Prezzo</th><th class="num">Valore intrinseco</th>
    <th class="num">Margine sicurezza</th><th class="num">Rend. atteso</th><th class="num">Prezzo max acquisto</th>
    <th class="num">Qualità</th><th class="num">Solidità</th><th class="num">Totale</th></tr></thead><tbody>
    ${data.results.map((r) => `<tr class="clickable" data-ticker="${esc(r.ticker)}">
      <td><strong>${esc(r.ticker)}</strong><br><span class="hint">${esc(r.name)}</span></td>
      <td>${badge(r.verdict)}</td>
      <td class="num">${fmtMoney(r.price, r.currency)}</td>
      <td class="num">${fmtMoney(r.metrics.intrinsic_value, r.currency)}</td>
      <td class="num ${cls(r.metrics.margin_of_safety)}">${fmtPct(r.metrics.margin_of_safety)}</td>
      <td class="num">${fmtPct(r.metrics.expected_return)}</td>
      <td class="num">${fmtMoney(r.metrics.buy_below_price, r.currency)}</td>
      <td class="num">${fmtNum(r.scores.qualita, 0)}</td>
      <td class="num">${fmtNum(r.scores.solidita, 0)}</td>
      <td class="num"><strong>${fmtNum(r.scores.totale, 0)}</strong></td></tr>`).join("")}
    </tbody></table></div><p class="hint">Clicca su una riga per l'analisi completa.</p></div>`;
  if (data.errors.length) {
    html += `<div class="card"><h2>Titoli non analizzati (${data.errors.length})</h2><ul>
      ${data.errors.map((e) => `<li><strong>${esc(e.ticker)}</strong>: <span class="hint">${esc(e.error)}</span></li>`).join("")}</ul></div>`;
  }
  return html;
}

// ---------------------------------------------------------------- portafoglio
document.getElementById("portfolio-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = document.getElementById("portfolio-result");
  const btn = e.submitter; btn.disabled = true;
  out.innerHTML = `<div class="loading">Analisi dei titoli e costruzione del portafoglio…</div>`;
  try {
    const data = await api("/api/portfolio", {
      universe: document.getElementById("pf-universe").value || null,
      tickers: parseTickers(document.getElementById("pf-tickers").value),
      capital: Number(document.getElementById("pf-capital").value),
      base_currency: document.getElementById("pf-currency").value,
      max_positions: Number(document.getElementById("pf-maxpos").value),
      max_weight: Number(document.getElementById("pf-maxw").value) / 100,
      max_sector: Number(document.getElementById("pf-maxs").value) / 100,
      settings,
    });
    out.innerHTML = renderPortfolio(data);
    out.querySelectorAll("tr[data-ticker]").forEach((tr) => tr.addEventListener("click", () => runAnalyze(tr.dataset.ticker)));
  } catch (err) {
    out.innerHTML = `<div class="error">${esc(err.message)}</div>`;
  } finally { btn.disabled = false; }
});

function renderPortfolio(p) {
  const bc = p.base_currency;
  let html = `<div class="card"><div class="kpis">
    <div class="kpi"><div class="lbl">Investito</div><div class="val">${fmtMoney(p.invested, bc, 0)}</div></div>
    <div class="kpi"><div class="lbl">Liquidità</div><div class="val">${fmtMoney(p.cash, bc, 0)} <span class="hint">(${fmtPct(p.cash_weight, 0)})</span></div></div>
    <div class="kpi"><div class="lbl">Rend. atteso parte investita</div><div class="val">${fmtPct(p.expected_return_invested)}</div></div>
    <div class="kpi"><div class="lbl">Rend. atteso totale</div><div class="val">${fmtPct(p.expected_return_total)}</div></div>
  </div>${p.message ? `<div class="verdict-box">${esc(p.message)}</div>` : ""}</div>`;
  if (p.positions.length) {
    html += `<div class="card"><h2>Titoli da acquistare</h2><div class="table-wrap"><table><thead><tr>
      <th>Titolo</th><th>Settore</th><th class="num">Prezzo</th><th class="num">N° azioni</th><th class="num">Importo (${esc(bc)})</th>
      <th class="num">Peso</th><th class="num">Rend. atteso</th><th class="num">Margine sicurezza</th><th class="num">Comprare sotto</th></tr></thead><tbody>
      ${p.positions.map((x) => `<tr class="clickable" data-ticker="${esc(x.ticker)}">
        <td><strong>${esc(x.ticker)}</strong><br><span class="hint">${esc(x.name)}</span></td><td>${esc(x.sector)}</td>
        <td class="num">${fmtMoney(x.price, x.currency)}</td><td class="num"><strong>${x.shares}</strong></td>
        <td class="num">${fmtNum(x.amount, 0)}</td><td class="num">${fmtPct(x.weight)}</td>
        <td class="num">${fmtPct(x.expected_return)}</td><td class="num">${fmtPct(x.margin_of_safety)}</td>
        <td class="num">${fmtMoney(x.buy_below_price, x.currency)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="hint">Se il prezzo sale sopra "Comprare sotto", meglio rimandare l'acquisto. Un numero di azioni pari a 0 indica capitale insufficiente per quel titolo.</p></div>`;
  }
  if (p.watchlist.length) {
    html += `<div class="card"><h2>Lista d'attesa: ottime aziende, oggi troppo care</h2><div class="table-wrap"><table><thead><tr>
      <th>Titolo</th><th class="num">Prezzo</th><th class="num">Comprare sotto</th><th class="num">Distanza</th><th class="num">Qualità</th></tr></thead><tbody>
      ${p.watchlist.map((w) => {
        const dist = w.buy_below_price ? w.price / w.buy_below_price - 1 : null;
        return `<tr class="clickable" data-ticker="${esc(w.ticker)}"><td><strong>${esc(w.ticker)}</strong><br><span class="hint">${esc(w.name)}</span></td>
          <td class="num">${fmtMoney(w.price, w.currency)}</td><td class="num">${fmtMoney(w.buy_below_price, w.currency)}</td>
          <td class="num neg">${dist == null ? "–" : "+" + fmtPct(dist, 0)}</td><td class="num">${fmtNum(w.quality, 0)}</td></tr>`;
      }).join("")}</tbody></table></div></div>`;
  }
  return html;
}

// ---------------------------------------------------------------- form parametri
const settingsForm = document.getElementById("settings-form");
function fillSettingsForm() {
  for (const [k, v] of Object.entries(settings)) {
    const el = settingsForm.elements[k];
    if (el) el.value = PCT_FIELDS.includes(k) ? +(v * 100).toFixed(2) : v;
  }
}
settingsForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const s = {};
  for (const k of Object.keys(DEFAULTS)) {
    const v = Number(settingsForm.elements[k].value);
    s[k] = PCT_FIELDS.includes(k) ? v / 100 : v;
  }
  if (s.terminal_growth >= s.discount_rate) {
    document.getElementById("settings-saved").textContent = "La crescita perpetua deve essere inferiore al tasso di sconto.";
    return;
  }
  settings = s; saveSettings(s);
  document.getElementById("settings-saved").textContent = "Salvato ✓";
  setTimeout(() => (document.getElementById("settings-saved").textContent = ""), 2000);
});
document.getElementById("settings-reset").addEventListener("click", () => {
  settings = { ...DEFAULTS }; saveSettings(settings); fillSettingsForm();
});

// ---------------------------------------------------------------- init
fillSettingsForm();
loadUniverses();
try { const t = localStorage.getItem("vit-tab"); if (t && document.getElementById("tab-" + t)) showTab(t); } catch { /* ignora */ }
