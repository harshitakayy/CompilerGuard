(function () {
"use strict";
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const state = { target: "cglang", presets: [], rules: [], examples: [], lastCompile: null, tab: "verdict", health: null };
const CUSTOM_DEFAULT = "# Write your own production rules.\n# Rule syntax:  name -> alternative | alternative\nexpr   -> term (('+' | '-') term)*\nterm   -> factor (('*' | '/') factor)*\nfactor -> NUMBER | ID | '(' expr ')'\n";
const ARMS = { blind: ["Mutation, blind", "var(--silver)"], feedback: ["Mutation + compiler feedback", "var(--gold)"], ai: ["AI-guided", "var(--teal)"] };
const METRICS = [["unique_error_patterns", "Unique error patterns", 1], ["bug_signals", "Potential bug signals", 0],
  ["production_coverage_pct", "Grammar production coverage (%)", 1], ["ast_unique_shapes", "AST shapes (unique)", 1],
  ["ast_unique_edges", "Production edges (unique)", 1], ["path_coverage_pct", "Compiler path coverage (%)", 1],
  ["new_patterns_per_test", "New patterns per test", 3], ["novel_tests", "Tests uncovering a new pattern", 1]];

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  let d; try { d = await r.json(); } catch (e) { d = { error: "The server returned an invalid response" }; }
  if (!r.ok) { const e = new Error(d.error || r.statusText); e.data = d; throw e; }
  return d;
}
const payload = () => state.target === "custom" ? { target: "custom", grammar: $("grammarEdit").value } : { target: state.target };
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const tag = (cls, txt) => `<span class="tg ${cls}">${esc(txt)}</span>`;

// ---------- grammar display ----------
function hlGrammar(text) {
  return text.split("\n").map(line => {
    let q = null, cut = -1;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (q) { if (ch === q && line[i - 1] !== "\\") q = null; }
      else if (ch === "'" || ch === '"') q = ch;
      else if (ch === "#" || line.startsWith("//", i)) { cut = i; break; }
    }
    const code = cut < 0 ? line : line.slice(0, cut), cm = cut < 0 ? "" : line.slice(cut);
    let h = code.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    h = h.replace(/^(\s*)([A-Za-z_]\w*)(\s*(?:-&gt;|::=|:=|→))/, '$1<span class="rn">$2</span><span class="ar">$3</span>');
    h = h.replace(/'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"/g, m => `<span class="lit">${m}</span>`);
    h = h.replace(/\b(ID|NUMBER|STRING|CHAR)\b(?![^<]*<\/span>)/g, '<span class="cls">$1</span>');
    return h + (cm ? `<span class="cm">${esc(cm)}</span>` : "");
  }).join("\n");
}
function renderRules(el, used) {
  used = used || {};
  if (!state.rules.length) { el.innerHTML = '<p class="muted small">Production rules appear here once the grammar is valid.</p>'; return; }
  el.innerHTML = state.rules.map(r => {
    const n = used[r.name];
    return `<div class="rule ${n ? "used" : ""}"><span style="white-space:pre-wrap">${esc(r.text)}</span><b>${n ? "×" + n : ""}</b></div>`;
  }).join("");
}
function renderAnalysis(res) {
  const el = $("analysis");
  if (!res.ok) {
    state.rules = []; renderRules($("rulesCompile")); renderRules($("rulesExp"));
    el.innerHTML = `<div class="note err"><b>Grammar error${res.error.line ? " on line " + res.error.line : ""}:</b> ${esc(res.error.message)}</div>`;
    $("gStats").textContent = ""; return;
  }
  const g = res.grammar;
  state.rules = g.rules;
  $("gStats").textContent = `start: ${g.start}`;
  let h = `<div class="stat3"><div>${g.stats.rules}<small>Rules</small></div><div>${g.stats.productions}<small>Productions</small></div><div>${g.stats.terminals}<small>Terminals</small></div></div>`;
  h += `<div class="lab">Terminals and token classes</div><div class="chips">${g.terminals.slice(0, 70).map(t => `<span class="tchip">${esc(t)}</span>`).join("")}${g.classes.map(t => `<span class="tchip" style="color:#d9a0e0">${t}</span>`).join("")}</div>`;
  h += g.warnings.length ? `<div class="lab">Warnings</div>` + g.warnings.map(w => `<div class="note"><b>${w.line ? "Line " + w.line + ": " : ""}</b>${esc(w.message)}</div>`).join("") : '<div class="note ok"><b>No structural problems found.</b> Every rule is reachable and productive.</div>';
  h += `<p class="muted small" style="margin-top:14px">“Productions” counts every alternative after expanding <code>( )</code>, <code>*</code>, <code>+</code> and <code>?</code>; coverage is measured against these.</p>`;
  el.innerHTML = h;
  renderRules($("rulesCompile")); renderRules($("rulesExp"));
}
async function refreshGrammar() {
  const text = state.target === "custom" ? $("grammarEdit").value : (state.presets.find(p => p.id === state.target) || {}).grammar || "";
  try {
    const res = await api("/api/grammar/analyze", { grammar: text });
    renderAnalysis(res);
    if (res.ok && state.target === "custom" && res.samples.length) state.examples = res.samples;
    return res.ok;
  } catch (e) { $("analysis").innerHTML = `<div class="note err">${esc(e.message)}</div>`; return false; }
}
async function loadExamples(forceInput) {
  const forTarget = state.target;
  try {
    const d = await api("/api/generate", { ...payload(), kind: "valid", count: 8, seed: Math.floor(Math.random() * 9999) });
    state.examples = d.rows.map(r => r.code);
  } catch (e) { state.examples = []; }
  if (forTarget !== state.target) return;
  if (forceInput && state.examples.length) { $("src").value = state.examples[0]; doCompile(); }
}

// ---------- language cards ----------
function renderCards() {
  const all = state.presets.concat([{ id: "custom", name: "Your own grammar", description: "Write production rules in EBNF. CompilerGuard builds a parser, an oracle, a generator and the whole experiment from them." }]);
  $("langCards").innerHTML = all.map(p => `<button class="card ${p.id === state.target ? "sel" : ""}" data-id="${p.id}"><span class="tag">${p.id === "custom" ? "Bring your own" : p.id === "cglang" ? "Hand-written compiler" : p.id === "cpp" ? "Flagship" : "Generated parser"}</span><h3>${esc(p.name)}</h3><p>${esc(p.description)}</p></button>`).join("");
  $("langCards").querySelectorAll(".card").forEach(b => b.onclick = () => selectTarget(b.dataset.id));
}
async function selectTarget(id) {
  state.target = id; renderCards();
  const custom = id === "custom";
  $("grammarView").hidden = custom; $("grammarEdit").hidden = !custom; $("grammarFoot").hidden = !custom;
  if (custom && !$("grammarEdit").value) $("grammarEdit").value = CUSTOM_DEFAULT;
  if (!custom) { const p = state.presets.find(x => x.id === id); $("grammarView").innerHTML = hlGrammar(p.grammar); }
  $("grammarSub").textContent = custom ? "Write the production rules below. The analysis, parser, oracle and tests are rebuilt from them as you type." : "The production rules that define the language. Everything below is generated from them.";
  const ok = await refreshGrammar();
  if (ok) await loadExamples(true);
  else $("cOut").innerHTML = '<p class="empty">Fix the grammar to compile programs.</p>';
}

// ---------- compile ----------
let compileSeq = 0;
async function doCompile() {
  const src = $("src").value, seq = ++compileSeq;
  try {
    const d = await api("/api/compile", { ...payload(), source: src });
    if (seq !== compileSeq) return; // a newer request superseded this one
    state.lastCompile = d; renderCompile(); renderRules($("rulesCompile"), d.rules_used); renderRules($("rulesExp"));
    $("compileHint").textContent = d.signal ? "The oracle disagrees with the compiler: a bug signal." : "Results update as you type.";
  } catch (e) { if (seq === compileSeq) $("cOut").innerHTML = `<div class="note err">${esc(e.message)}</div>`; }
}
function renderCompile() {
  const d = state.lastCompile, el = $("cOut"); if (!d) return;
  const r = d.response, o = d.oracle, t = state.tab;
  if (t === "verdict") {
    let h = r.status === "PASS" ? '<span class="badge pass">Accepted</span>' : `<span class="badge fail">Rejected · ${esc(r.type)}</span>`;
    if (d.signal) h += ' <span class="badge sig">Bug signal</span>';
    if (r.status === "FAIL") {
      const ln = ($("src").value.split("\n")[(r.line || 1) - 1]) || "";
      h += `<div class="kv"><b>Line</b><span class="mono">${esc(r.line)}</span><b>Column</b><span class="mono">${esc(r.column)}</span><b>Message</b><span>${esc(r.message)}</span></div><pre class="src">${esc(ln)}\n<span class="caret">${" ".repeat(Math.max(0, (r.column || 1) - 1))}^</span></pre>`;
    } else h += '<p class="muted" style="margin-top:18px">The program is a sentence of the language: lexing, parsing and any semantic checks all passed.</p>';
    h += `<div class="lab">Independent oracle</div><p>${o.status === "PASS" ? "Accepts" : "Rejects (" + esc(o.type) + ")"} the program${d.signal ? ` — <strong>disagreement:</strong> ${esc(d.reasons.join(", "))}` : ", in agreement with the compiler"}.</p>`;
    if (d.expected && d.expected.length) h += `<div class="lab">Tokens the grammar expected</div><div class="chips">${d.expected.map(x => `<span class="tchip">${esc(x)}</span>`).join("")}</div>`;
    el.innerHTML = h;
  } else if (t === "tokens") {
    el.innerHTML = d.tokens.length ? d.tokens.map(k => `<span class="tok">${esc(k.text || "EOF")}<s>${esc(k.kind)} ${k.line}:${k.col}</s></span>`).join("") : '<p class="empty">No tokens (lexical error).</p>';
  } else if (t === "tree") {
    const node = n => n.t !== undefined ? `<li><span class="t">${esc(n.t)}</span></li>` : `<li><span class="n">${esc(n.n)}</span>${n.c.length ? "<ul>" + n.c.map(node).join("") + "</ul>" : ""}</li>`;
    el.innerHTML = d.tree ? `<ul class="tree">${node(d.tree)}</ul>` : '<p class="empty">No parse tree: the program was rejected.</p>';
  } else {
    el.innerHTML = d.productions_used.length ? d.productions_used.map(p => `<div class="rule"><span>${esc(p.label)}</span><b>×${p.count}</b></div>`).join("") : '<p class="empty">Productions used appear once the program is accepted.</p>';
  }
}
const breakIt = () => {
  const s = $("src"), v = s.value, i = Math.floor(Math.random() * Math.max(1, v.length)), pick = Math.floor(Math.random() * 4);
  s.value = pick === 0 ? v.slice(0, i) + v.slice(i + 1) : pick === 1 ? v.slice(0, i) + " @ " + v.slice(i) : pick === 2 ? v.slice(0, i) + v.slice(i).replace(/[)\];}]/, "") : v.slice(0, Math.max(1, v.length - 1 - Math.floor(Math.random() * 3)));
  doCompile();
};

// ---------- generator ----------
async function generate() {
  const b = $("genBtn"); b.disabled = true; b.textContent = "Generating…";
  try {
    const d = await api("/api/generate", { ...payload(), kind: $("gKind").value, count: +$("gCount").value, seed: +$("gSeed").value });
    $("genTable").querySelector("tbody").innerHTML = d.rows.map((r, i) => `<tr data-i="${i}"><td class="muted">${i + 1}</td><td class="op">${esc(r.operator || "grammar derivation")}${r.intent ? `<br><span class="muted small">intent: ${esc(r.intent)}</span>` : ""}</td><td class="c">${esc(r.code)}</td><td>${tag(r.expected === "PASS" ? "pass" : "fail", r.expected === "PASS" ? "valid" : "invalid")}</td><td>${r.actual === "PASS" ? tag("pass", "accepted") : tag("fail", r.response.type.replace("_ERROR", ""))}</td><td>${r.signal ? tag("sig", "signal") : ""}</td></tr>`).join("");
    $("genEmpty").hidden = true;
    $("genTable").querySelectorAll("tbody tr").forEach(tr => tr.onclick = () => { $("src").value = d.rows[+tr.dataset.i].code; doCompile(); $("s-compile").scrollIntoView({ behavior: "smooth" }); });
  } catch (e) { $("genEmpty").hidden = false; $("genEmpty").textContent = e.message; }
  b.disabled = false; b.textContent = "Generate";
}

// ---------- experiment ----------
const fmt = (s, d) => s == null || s.mean == null ? "—" : s.mean.toFixed(d) + (s.stdev != null ? ` ± ${s.stdev.toFixed(d)}` : "");
function lineChart(series, n, prefix, pct) {
  const W = 520, H = 210, L = 38, R = 10, T = 10, B = 24;
  const max = pct ? 100 : Math.max(1, ...series.map(s => Math.max(...s.values)));
  const x = i => L + (W - L - R) * i / Math.max(1, n - 1), y = v => T + (H - T - B) * (1 - v / max);
  let g = "";
  for (let k = 0; k <= 4; k++) { const v = max * k / 4; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${pct ? Math.round(v) : Math.round(v * 10) / 10}</text>`; }
  g += `<text x="${L}" y="${H - 6}">1</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${n}</text><text x="${(L + W) / 2}" y="${H - 6}" text-anchor="middle">tests executed</text>`;
  if (prefix) g += `<line x1="${x(prefix - 1)}" x2="${x(prefix - 1)}" y1="${T}" y2="${H - B}" stroke="var(--line2)" stroke-dasharray="3 4"/><text x="${x(prefix - 1) + 4}" y="${T + 9}">shared start</text>`;
  series.forEach(s => { g += `<polyline fill="none" stroke="${s.color}" stroke-width="2" points="${s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}"/>`; });
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">${g}</svg><div class="legend">${series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>`;
}
function renderResults(res) {
  const R = $("results"); R.hidden = false;
  const t0 = res.trials[0], keys = ["blind", "feedback", "ai"], total = res.grammar.productions;
  const cfg = res.config;
  let h = `<div class="rh"><h3>${esc(res.target_name)} — results</h3><span class="muted">budget ${cfg.budget} per approach · ${cfg.seed_tests} shared start tests · ${cfg.trials} trial(s) · saved to <code>${esc(res.report_dir || "reports/runs")}</code></span></div>`;
  const ai = t0.arms.ai;
  if (ai && ai.status !== "COMPLETE") h += `<div class="note"><b>AI-guided approach ${ai.status === "NOT_RUN" ? "not run" : "incomplete"}.</b> ${esc(ai.reason || "")} The two mutation approaches below are real measurements; no AI numbers are shown or estimated. To include it, tick “Include the AI-guided approach” and provide an API key.</div>`;
  h += '<div class="arms">';
  keys.forEach(k => {
    const a = res.aggregate[k], m = a && a.metrics, c = ARMS[k][1];
    if (!m) { h += `<div class="arm off" style="--c:${c}"><h4>${ARMS[k][0]}</h4><div class="sub">Not run</div><p class="muted small">${esc((t0.arms[k] || {}).reason || "No completed trials.")}</p></div>`; return; }
    h += `<div class="arm" style="--c:${c}"><h4>${ARMS[k][0]}</h4><div class="sub">${cfg.budget} tests × ${a.trials_complete} trial(s)${m.path_coverage_pct.mean === 0 ? " · path instrumentation unavailable" : ""}</div><div class="kpis">`;
    [["unique_error_patterns", "Unique error patterns", 1], ["bug_signals", "Bug signals", 0], ["production_coverage_pct", "Production coverage %", 1], ["ast_unique_shapes", "AST shapes", 1], ["path_coverage_pct", "Path coverage %", 1], ["new_patterns_per_test", "New patterns / test", 2]].forEach(([id, label, d]) => { h += `<div class="kpi"><b>${m[id].mean == null ? "—" : m[id].mean.toFixed(d)}</b><small>${label}</small>${m[id].stdev != null ? `<em>± ${m[id].stdev.toFixed(d)}</em>` : ""}</div>`; });
    h += "</div></div>";
  });
  h += "</div>";
  const have = keys.filter(k => res.aggregate[k] && res.aggregate[k].metrics);
  h += `<div class="panel" style="margin-bottom:22px"><div class="ph"><span>Comparison at equal budget</span><span class="muted">mean ± sample standard deviation over completed trials</span></div><div class="body flush"><div class="tablewrap"><table class="cmp"><thead><tr><th>Metric</th>${have.map(k => `<th>${ARMS[k][0]}</th>`).join("")}</tr></thead><tbody>`;
  METRICS.forEach(([id, label, d]) => {
    h += `<tr><td>${label}</td>` + have.map(k => {
      const a = res.aggregate[k], delta = a.delta_vs_blind && a.delta_vs_blind[id];
      return `<td>${fmt(a.metrics[id], d)}${delta ? ` <span class="${delta > 0 ? "up" : "dn"}">${delta > 0 ? "+" : ""}${delta}</span>` : ""}</td>`;
    }).join("") + "</tr>";
  });
  h += `</tbody></table></div></div></div>`;
  h += `<p class="muted small">Green/red figures are differences from the blind-mutation approach. “Value of feedback” = <em>feedback</em> minus <em>blind</em> at the same test budget; it varies by grammar and seed, so read it with the spread, not as a ranking.</p>`;
  const curve = (key, f) => keys.filter(k => t0.arms[k] && t0.arms[k].summary).map(k => ({ name: ARMS[k][0], color: ARMS[k][1].replace("var(--silver)", getComputedStyle(document.documentElement).getPropertyValue("--silver") || "#a8adc0").replace("var(--gold)", getComputedStyle(document.documentElement).getPropertyValue("--gold") || "#c9a96a").replace("var(--teal)", getComputedStyle(document.documentElement).getPropertyValue("--teal") || "#7fd1c7"), values: f(t0.arms[k].summary) }));
  const n = cfg.budget;
  h += `<div class="charts"><div class="panel chart"><h5>Cumulative unique error patterns</h5>${lineChart(curve("p", s => s.curves.patterns), n, cfg.seed_tests, false)}</div>
  <div class="panel chart"><h5>Grammar production coverage (%)</h5>${lineChart(curve("c", s => s.curves.productions.map(v => 100 * v / total)), n, cfg.seed_tests, true)}</div>
  <div class="panel chart"><h5>Cumulative AST shapes discovered</h5>${lineChart(curve("s", s => s.curves.shapes), n, cfg.seed_tests, false)}</div></div>`;
  h += `<div class="panel" style="margin-bottom:22px"><div class="ph"><span>What each test uncovered</span><span class="muted">trial 1 · one cell per test · gold = new error pattern, amber = new productions or AST shape, teal = new compiler lines</span></div><div class="body">`;
  keys.forEach(k => { const s = t0.arms[k] && t0.arms[k].summary; if (!s) return; h += `<div class="lab">${ARMS[k][0]} — ${s.novel_tests} tests found a new pattern</div><div class="strip">${s.novelty.map((v, i) => `<i class="${v[0] ? "l3" : v[1] || v[2] ? "l2" : v[3] ? "l1" : ""}" title="test ${i + 1}: new patterns ${v[0]}, new productions ${v[1]}, new AST shape ${v[2]}, new lines ${v[3]}"></i>`).join("")}</div>`; });
  h += "</div></div>";
  keys.forEach(k => {
    const s = t0.arms[k] && t0.arms[k].summary; if (!s) return;
    const pc = s.production_coverage;
    h += `<details><summary>${ARMS[k][0]} — production coverage by rule (${pc.covered}/${pc.total}) and uncovered productions</summary>` + Object.entries(pc.by_rule).map(([r, v]) => `<div class="cov"><span>${esc(r)}</span><span class="t"><i style="width:${100 * v.covered / v.total}%"></i></span><span>${v.covered}/${v.total}</span></div>`).join("") + (pc.uncovered.length ? `<div class="lab">Not yet exercised${pc.uncovered.length >= 40 ? " (first 40)" : ""}</div><div class="chips">${pc.uncovered.map(u => `<span class="tchip" style="color:var(--muted)">${esc(u)}</span>`).join("")}</div>` : '<div class="note ok">Every production was exercised.</div>') + "</details>";
  });
  const fb = t0.arms.feedback;
  if (fb && fb.operator_weights) h += `<details><summary>What the feedback approach learned: operator weights</summary>${Object.entries(fb.operator_weights).slice(0, 10).map(([o, w]) => `<div class="cov"><span>${esc(o)}</span><span class="t"><i style="width:${Math.min(100, w * 8)}%"></i></span><span>${w}</span></div>`).join("")}<p class="muted small">Operators that produced new error patterns, productions or AST shapes gain weight; the rest decay (30% of choices stay uniform to keep exploring).</p></details>`;
  const sig = [];
  keys.forEach(k => ((t0.arms[k] && t0.arms[k].tests) || []).forEach(x => { if (x.signal && !sig.some(y => y.code === x.code)) sig.push({ ...x, arm: k }); }));
  h += `<div class="panel" style="margin-top:14px"><div class="ph"><span>Potential compiler bug signals</span><span class="muted">${sig.length} distinct (trial 1) · candidates for investigation, not confirmed bugs</span></div><div class="body flush">${sig.length ? `<div class="tablewrap"><table><thead><tr><th>Approach</th><th>Program</th><th>Compiler</th><th>Oracle</th><th>Disagreement</th></tr></thead><tbody>${sig.slice(0, 30).map(x => `<tr><td>${ARMS[x.arm][0]}</td><td class="c">${esc(x.code)}</td><td>${esc(x.response.status)} ${esc(x.response.type || "")}</td><td>${esc(x.oracle.status)} ${esc(x.oracle.type || "")}</td><td>${tag("sig", x.reasons.join(", "))}</td></tr>`).join("")}</tbody></table></div>` : '<p class="empty">No disagreements between the compiler and the oracle.</p>'}</div></div>`;
  if (ai && ai.ai) h += `<div class="panel" style="margin-top:14px"><div class="ph"><span>AI rounds</span><span class="muted">status ${esc(ai.ai.status)}</span></div><div class="body flush"><div class="tablewrap"><table><thead><tr><th>Round</th><th>Requested</th><th>Executed</th><th>New patterns</th><th>Duplicates dropped</th><th>Status</th></tr></thead><tbody>${ai.ai.rounds.map(r => `<tr><td>${r.round}</td><td>${r.requested}</td><td>${r.executed}</td><td>${r.new_patterns.length}</td><td>${r.duplicates_discarded}</td><td>${esc(r.status)}${r.reason ? " — " + esc(r.reason) : ""}</td></tr>`).join("")}</tbody></table></div></div></div>`;
  const D = res.design;
  h += `<details style="margin-top:14px"><summary>How these numbers are defined</summary><p class="muted small"><b>Bug signal:</b> ${esc(D.bug_signal)}.<br><b>Production coverage:</b> ${esc(D.production_coverage)}.<br><b>AST diversity:</b> ${esc(D.ast_diversity)}.<br><b>Path coverage:</b> ${esc(D.path_coverage)}.<br><b>Unique error pattern:</b> the compiler’s error type and message with names and characters abstracted.</p></details>`;
  R.innerHTML = h; R.scrollIntoView({ behavior: "smooth" });
}
async function runExperiment() {
  const btn = $("runBtn"); btn.disabled = true; $("runState").textContent = "Running"; $("barFill").style.width = "2%"; $("runLog").textContent = "Starting…\n";
  try {
    const body = { ...payload(), budget: +$("eBudget").value, seed_tests: +$("eSeedTests").value, batch: +$("eBatch").value, trials: +$("eTrials").value, seed: +$("eSeed").value, ai: { enabled: $("aiOn").checked, api_key: $("aiKey").value } };
    const { job_id } = await api("/api/experiment", body);
    for (;;) {
      await new Promise(r => setTimeout(r, 700));
      const j = await api("/api/jobs/" + job_id);
      $("barFill").style.width = Math.max(3, j.progress) + "%"; $("runLog").textContent = j.log.join("\n"); $("runLog").scrollTop = 1e6;
      if (j.status === "done") { $("runState").textContent = "Complete"; renderResults(j.result); break; }
      if (j.status === "error") { $("runState").textContent = "Failed"; $("runLog").textContent += "\nError: " + j.error; break; }
    }
  } catch (e) { $("runState").textContent = "Failed"; $("runLog").textContent = e.message; }
  $("aiKey").value = ""; btn.disabled = false;
}

// ---------- boot ----------
async function boot() {
  document.querySelectorAll(".reveal").forEach(el => { new IntersectionObserver((es, ob) => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); ob.disconnect(); } }), { threshold: .06 }).observe(el); });
  $("theme").onclick = () => { const r = document.documentElement; r.dataset.theme = r.dataset.theme === "dark" ? "light" : "dark"; };
  $("heroStats").innerHTML = '<div>22<small>Mutation operators</small></div><div>3<small>Approaches, equal budget</small></div><div>6<small>Grammars</small></div>';
  $("eBudget").oninput = e => { $("vBudget").textContent = e.target.value; const s = $("eSeedTests"); s.max = Math.min(50, e.target.value - 10); if (+s.value > +s.max) s.value = s.max; $("vSeed").textContent = s.value; };
  $("eSeedTests").oninput = e => $("vSeed").textContent = e.target.value;
  $("src").addEventListener("input", debounce(doCompile, 380));
  $("compileBtn").onclick = doCompile; $("breakBtn").onclick = breakIt; $("genBtn").onclick = generate; $("runBtn").onclick = runExperiment;
  $("exampleBtn").onclick = () => { if (!state.examples.length) return loadExamples(true); $("src").value = state.examples[Math.floor(Math.random() * state.examples.length)]; doCompile(); };
  $("analyzeBtn").onclick = async () => { if (await refreshGrammar()) { await loadExamples(true); } };
  $("grammarEdit").addEventListener("input", debounce(async () => { if (await refreshGrammar()) loadExamples(false); }, 700));
  $("cTabs").querySelectorAll("button").forEach(b => b.onclick = () => { state.tab = b.dataset.t; $("cTabs").querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); renderCompile(); });
  try {
    const [h, p] = await Promise.all([api("/api/health"), api("/api/presets")]);
    state.health = h; state.presets = p.presets;
    if (h.ai.available) $("aiOn").checked = true;
    renderCards(); await selectTarget("cglang");
  } catch (e) {
    $("langCards").innerHTML = '<div class="note err"><b>Unable to load the language options.</b> Check the connection and refresh the page.</div>';
  }
}
boot();
})();
