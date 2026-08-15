const $ = (sel) => document.querySelector(sel);
const money = (n) => (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const amtClass = (n) => (n >= 0 ? "amt pos" : "amt neg");

let state = null;
let rangeDays = 90;
let activeScenario = null;

document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("on"));
    document.querySelectorAll("main.panel").forEach((p) => p.classList.remove("on"));
    btn.classList.add("on");
    $("#" + btn.dataset.tab).classList.add("on");
  });
});

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function refresh() {
  const qs = new URLSearchParams();
  if (activeScenario) qs.set("scenario", activeScenario);
  qs.set("days", String(rangeDays));
  state = await api("/api/state?" + qs.toString());
  state.history = await api("/api/history");
  render();
}

function render() {
  renderHero();
  renderChart();
  renderUpcoming();
  renderGoals();
  renderPlan();
  renderTemplates();
  renderProposals();
  renderScenarios();
  renderLedgerMeta();
  renderSettings();
  renderAlerts();
}

function renderHero() {
  const el = $("#spendable");
  el.textContent = money(state.spendable);
  el.className = "spend" + (state.health === "danger" ? " bad" : state.health === "warning" ? " warn" : "");
  $("#why").textContent = state.why;
  const bits = [
    `Balance ${money(state.balance)}`,
    state.runway_days == null ? "No floor hit in window" : `Runway ${state.runway_days} days`,
    state.min_date ? `Low ${money(state.min_balance)} on ${state.min_date}` : "",
    `Health ${state.health}`,
    state.scenario ? `Overlay: ${state.scenario.name}` : "",
    state.show_drift ? `Drift vs expected ${money(state.drift)}` : "",
  ].filter(Boolean);
  $("#hero-meta").innerHTML = bits.map((b) => `<span>${b}</span>`).join("");
  $("#stats").innerHTML = [
    `Min ${money(state.stats.min_balance)}`,
    `Max ${money(state.stats.max_balance)}`,
    `Avg ${money(state.stats.avg_balance)}`,
    `Negative days ${state.stats.days_negative}`,
    state.stats.first_negative_date ? `First red ${state.stats.first_negative_date}` : "Never red",
    state.analysis ? `Trend ${state.analysis.trend}` : "",
  ].map((b) => `<span>${b}</span>`).join("");
  const ranges = $("#ranges");
  ranges.innerHTML = "";
  [30, 90, 180, 365].forEach((d) => {
    const b = document.createElement("button");
    b.textContent = d + "d";
    if (d === rangeDays) b.classList.add("on");
    b.onclick = async () => { rangeDays = d; await refresh(); };
    ranges.appendChild(b);
  });
}

function renderChart() {
  const canvas = $("#chart");
  const ctx = canvas.getContext("2d");
  const snaps = state.snapshots || [];
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!snaps.length) return;
  const vals = snaps.map((s) => s.balance);
  const min = Math.min(...vals, 0);
  const max = Math.max(...vals, 0);
  const pad = 16;
  const x = (i) => pad + (i / Math.max(snaps.length - 1, 1)) * (w - pad * 2);
  const y = (v) => {
    const span = max - min || 1;
    return h - pad - ((v - min) / span) * (h - pad * 2);
  };
  ctx.strokeStyle = "#243040";
  ctx.beginPath();
  ctx.moveTo(pad, y(0));
  ctx.lineTo(w - pad, y(0));
  ctx.stroke();
  ctx.strokeStyle = state.health === "danger" ? "#e05a4f" : "#f0c14b";
  ctx.lineWidth = 2;
  ctx.beginPath();
  snaps.forEach((s, i) => {
    const px = x(i), py = y(s.balance);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();
}

function renderUpcoming() {
  const rows = (state.upcoming || []).map((t) => `
    <tr>
      <td>${t.date}</td>
      <td>${escapeHtml(t.name)}</td>
      <td class="${amtClass(t.amount)}">${money(t.amount)}</td>
      <td>
        <button data-skip="${t.template_id}|${t.date}|skipOnce">Skip</button>
        <button data-skip="${t.template_id}|${t.date}|skipForever">Stop</button>
      </td>
    </tr>`).join("");
  $("#upcoming").innerHTML = `<table><thead><tr><th>Date</th><th>Name</th><th>Amt</th><th></th></tr></thead><tbody>${rows || "<tr><td colspan=4>Nothing scheduled.</td></tr>"}</tbody></table>`;
  $("#upcoming").querySelectorAll("button[data-skip]").forEach((b) => {
    b.onclick = async () => {
      const [template_id, date, status] = b.dataset.skip.split("|");
      await api("/api/plan", { method: "POST", body: JSON.stringify({ template_id, date, status }) });
      await refresh();
    };
  });
}

function renderGoals() {
  $("#goals").innerHTML = (state.goals || []).map((g) => `
    <div>
      <strong>${escapeHtml(g.name)}</strong>
      <span class="tiny">${g.on_track ? "on track" : "short " + money(g.shortfall || 0)} · target ${money(g.target_amount)} by ${g.target_date}</span>
      <button data-del-goal="${g.id}">×</button>
    </div>`).join("") || "<p class='hint'>No goals yet.</p>";
  $("#goals").querySelectorAll("[data-del-goal]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/goals/${b.dataset.delGoal}/delete`, { method: "POST", body: "{}" });
      await refresh();
    };
  });
}

function renderPlan() {
  const items = state.plan || [];
  $("#plan").innerHTML = items.length
    ? `<ul>${items.map((p) => `<li>${p.status} · ${p.date} · ${p.template_id.slice(0, 8)} (${p.category})</li>`).join("")}</ul>`
    : "<p class='hint'>No active skips.</p>";
}

function renderTemplates() {
  const rows = (state.templates || []).map((t) => `
    <tr>
      <td>${escapeHtml(t.name)}</td>
      <td>${t.frequency_label}</td>
      <td>${t.category}</td>
      <td class="${amtClass(t.effective_amount)}">${money(t.effective_amount)}</td>
      <td>${t.anchor_date}</td>
      <td>
        <button data-edit="${t.id}">Edit</button>
        <button data-del="${t.id}">Delete</button>
      </td>
    </tr>`).join("");
  $("#templates").innerHTML = `<table><thead><tr><th>Name</th><th>Freq</th><th>Cat</th><th>Amt</th><th>Anchor</th><th></th></tr></thead><tbody>${rows || "<tr><td colspan=6>Empty model. Import a CSV or load the demo.</td></tr>"}</tbody></table>`;
  $("#templates").querySelectorAll("[data-del]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/templates/${b.dataset.del}/delete`, { method: "POST", body: "{}" });
      await refresh();
    };
  });
  $("#templates").querySelectorAll("[data-edit]").forEach((b) => {
    b.onclick = () => {
      const t = state.templates.find((x) => x.id === b.dataset.edit);
      const f = $("#template-form");
      f.id.value = t.id;
      f.name.value = t.name;
      f.amount.value = t.amount;
      f.frequency.value = t.frequency;
      f.anchor_date.value = t.anchor_date;
      f.category.value = t.category;
      f.min_amount.value = t.min_amount ?? "";
      f.max_amount.value = t.max_amount ?? "";
    };
  });
}

function renderProposals() {
  const items = state.proposals || [];
  $("#proposals").innerHTML = items.length ? items.map((p) => `
    <div>
      <strong>${escapeHtml(p.name)}</strong>
      <span class="${amtClass(p.amount)}">${money(p.amount)}</span>
      <div class="tiny">${p.frequency_label} · ${p.reason} · confidence ${(p.confidence * 100).toFixed(0)}%</div>
      <button data-acc="${p.id}">Accept</button>
      <button data-rej="${p.id}">Reject</button>
    </div>`).join("") : "<p class='hint'>No pending proposals.</p>";
  $("#proposals").querySelectorAll("[data-acc]").forEach((b) => {
    b.onclick = async () => { await api(`/api/proposals/${b.dataset.acc}/accept`, { method: "POST", body: "{}" }); await refresh(); };
  });
  $("#proposals").querySelectorAll("[data-rej]").forEach((b) => {
    b.onclick = async () => { await api(`/api/proposals/${b.dataset.rej}/reject`, { method: "POST", body: "{}" }); await refresh(); };
  });
}

function renderScenarios() {
  fetch("/api/scenarios").then((r) => r.json()).then((list) => {
    $("#scenario-list").innerHTML = [
      `<div class="card ${activeScenario ? "" : "on"}" data-sid=""><h3>Baseline</h3><p>No overlay.</p></div>`,
      ...list.map((s) => `<div class="card ${activeScenario === s.id ? "on" : ""}" data-sid="${s.id}"><h3>${escapeHtml(s.name)}</h3><p>${escapeHtml(s.description)}</p></div>`),
    ].join("");
    $("#scenario-list").querySelectorAll(".card").forEach((card) => {
      card.onclick = async () => {
        activeScenario = card.dataset.sid || null;
        await refresh();
      };
    });
  });
}

function renderLedgerMeta() {
  $("#anchor-line").textContent = state.anchor
    ? `Anchor ${money(state.anchor.amount)} on ${state.anchor.date}. Derived balance ${money(state.balance)}.`
    : "No anchor yet. Update balance or import a bank CSV.";
  const rows = (state.history || []).slice(0, 40).map((e) => `
    <tr>
      <td>${e.date}</td>
      <td>${escapeHtml(e.template_name || e.note || e.entry_type)}</td>
      <td>${e.entry_type}</td>
      <td class="${amtClass(e.amount)}">${money(e.amount)}</td>
    </tr>`).join("");
  $("#ledger").innerHTML = `<table><thead><tr><th>Date</th><th>Name</th><th>Type</th><th>Amt</th></tr></thead><tbody>${rows || "<tr><td colspan=4>Empty ledger.</td></tr>"}</tbody></table>`;
}

function renderSettings() {
  const f = $("#settings-form");
  const s = state.settings;
  f.timezone.value = s.timezone;
  f.transaction_ordering.value = s.transaction_ordering;
  f.rounding_mode.value = s.rounding_mode;
  f.projection_days.value = s.projection_days;
  f.safety_floor.value = s.safety_floor;
  f.warning_threshold.value = s.warning_threshold;
}

function renderAlerts() {
  const box = $("#alerts");
  const items = state.alerts || [];
  if (!items.length) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  box.innerHTML = items.map((a) => `<div>${escapeHtml(a.message)} <button data-ack="${a.id}">ack</button></div>`).join("");
  box.querySelectorAll("[data-ack]").forEach((b) => {
    b.onclick = async () => { await api(`/api/alerts/${b.dataset.ack}/ack`, { method: "POST", body: "{}" }); await refresh(); };
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

$("#template-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  const payload = {
    id: f.id.value || undefined,
    name: f.name.value,
    amount: Number(f.amount.value),
    frequency: f.frequency.value,
    anchor_date: f.anchor_date.value,
    category: f.category.value,
    min_amount: f.min_amount.value === "" ? null : Number(f.min_amount.value),
    max_amount: f.max_amount.value === "" ? null : Number(f.max_amount.value),
  };
  await api("/api/templates", { method: "POST", body: JSON.stringify(payload) });
  f.reset();
  await refresh();
};

$("#goal-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  await api("/api/goals", { method: "POST", body: JSON.stringify({
    name: f.name.value, target_amount: Number(f.target_amount.value), target_date: f.target_date.value
  })});
  f.reset();
  await refresh();
};

$("#ledger-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  await api("/api/ledger", { method: "POST", body: JSON.stringify({
    date: f.date.value, amount: Number(f.amount.value), entry_type: "adjustment", note: f.note.value
  })});
  f.reset();
  await refresh();
};

$("#balance-form").onsubmit = async (e) => {
  e.preventDefault();
  await api("/api/balance", { method: "POST", body: JSON.stringify({ amount: Number(e.target.amount.value) }) });
  e.target.reset();
  await refresh();
};

$("#settings-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  await api("/api/settings", { method: "POST", body: JSON.stringify({
    timezone: f.timezone.value,
    transaction_ordering: f.transaction_ordering.value,
    rounding_mode: f.rounding_mode.value,
    projection_days: Number(f.projection_days.value),
    safety_floor: Number(f.safety_floor.value),
    warning_threshold: Number(f.warning_threshold.value),
  })});
  await refresh();
};

$("#clear-plan").onclick = async () => { await api("/api/plan/clear", { method: "POST", body: "{}" }); await refresh(); };
$("#reset-plan").onclick = async () => { await api("/api/plan/reset", { method: "POST", body: "{}" }); await refresh(); };
$("#demo-btn").onclick = async () => { await api("/api/demo", { method: "POST", body: "{}" }); await refresh(); };
$("#nightly-btn").onclick = async () => {
  const report = await api("/api/nightly", { method: "POST", body: "{}" });
  $("#nightly-out").textContent = JSON.stringify(report, null, 2);
  await refresh();
};
$("#import-btn").onclick = async () => {
  const text = $("#csv-text").value;
  const result = await api("/api/import", { method: "POST", body: JSON.stringify({ csv: text }) });
  $("#import-result").textContent = `Imported ${result.imported} ${result.kind} rows, ${result.proposals} proposals.`;
  await refresh();
};
$("#csv-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("#csv-text").value = await file.text();
};

refresh().catch((err) => {
  $("#why").textContent = "Could not load engine: " + err.message;
});
