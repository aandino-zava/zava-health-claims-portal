/* All claim values are escaped before entering HTML. MSAL uses sessionStorage. */
"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number(v));
const statuses = [
  "Submitted",
  "Under Review",
  "Pending Info",
  "Approved",
  "Denied",
  "In Appeal",
];
const services = [
  "Medical",
  "Surgical",
  "Mental Health",
  "Emergency",
  "Preventive",
  "Dental",
  "Vision",
  "Physical Therapy",
  "Lab/Diagnostics",
];
let config,
  auth,
  roles = [],
  view = "dashboard",
  page = 0,
  query = "",
  filterStatus = "",
  filterService = "";
let draft = {},
  step = 0,
  requestKey = crypto.randomUUID(),
  selectedClaim,
  transitions;
const option = (values, selected = "") =>
  values
    .map(
      (v) =>
        `<option value="${esc(v)}" ${v === selected ? "selected" : ""}>${esc(v)}</option>`,
    )
    .join("");
const badge = (status) =>
  `<span class="status s-${esc(status.replaceAll(" ", "-"))}">${esc(status)}</span>`;
function notice(text = "", error = false) {
  $("#notice").textContent = text;
  $("#notice").className = error ? "error" : "";
}
async function token() {
  if (config.auth_mode === "development") return null;
  const account = auth.getAllAccounts()[0];
  if (!account) throw Error("Sign in with your work account to continue.");
  try {
    return (await auth.acquireTokenSilent({ account, scopes: [config.scope] }))
      .accessToken;
  } catch (e) {
    if (e instanceof msal.InteractionRequiredAuthError) {
      await auth.acquireTokenRedirect({ account, scopes: [config.scope] });
    }
    throw e;
  }
}
async function api(path, options = {}) {
  const access = await token();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (access) headers.Authorization = `Bearer ${access}`;
  const response = await fetch("/api/v1" + path, { ...options, headers });
  const data = await response.json();
  if (!response.ok) {
    const message = Array.isArray(data.detail)
      ? data.detail
          .map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
          .join("; ")
      : data.detail;
    throw Error(message || "Request failed");
  }
  return data;
}
const can = (role) => roles.includes("Claims." + role);
function stats(cards) {
  return `<div class="stats">${cards.map(([label, value, symbol]) => `<div class="stat"><div><small>${esc(label)}</small><strong>${esc(value)}</strong></div><span class="stat-symbol" aria-hidden="true">${symbol}</span></div>`).join("")}</div>`;
}
function table(items) {
  return items.length
    ? `<div class="table-responsive"><table class="table"><thead><tr><th>CLAIM ID</th><th>MEMBER</th><th>TYPE</th><th>SERVICE DATE</th><th>CHARGES</th><th>STATUS</th></tr></thead><tbody>${items.map((c) => `<tr><td><button data-claim="${esc(c.id)}">${esc(c.id)}</button></td><td>${esc(c.patient_name)}<br><small class="text-secondary">${esc(c.patient_id)}</small></td><td>${esc(c.service_type)}</td><td>${esc(c.service_date)}</td><td>${money(c.amount)}</td><td>${badge(c.status)}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="empty">No claims found. Try different filters or file a new synthetic claim.</p>';
}
async function dashboard() {
  const [a, c] = await Promise.all([api("/analytics"), api("/claims?limit=5")]);
  $("#content").innerHTML =
    `<section class="hero"><h1>Health Insurance Claims Portal</h1><p>Submit, track, and manage health insurance claims efficiently.</p><button class="btn btn-light" data-view="new" ${can("Writer") ? "" : "disabled"}>＋ File New Claim</button><button class="btn btn-outline-light" data-view="tracker">View All Claims</button></section>
  ${stats([
    ["Total Claims", a.total, "▤"],
    ["Approved", a.by_status.Approved, "✓"],
    [
      "Pending Review",
      a.by_status.Submitted +
        a.by_status["Under Review"] +
        a.by_status["Pending Info"],
      "◷",
    ],
    ["Denied / Appeal", a.by_status.Denied + a.by_status["In Appeal"], "!"],
  ])}
  <div class="grid-two"><section class="panel"><h3>Quick Actions</h3><button class="action" data-view="new" ${can("Writer") ? "" : "disabled"}><span>✚</span><div><strong>File Medical Claim</strong><small>Submit a new synthetic service claim</small></div></button><button class="action" data-view="tracker"><span>⌕</span><div><strong>Check Claim Status</strong><small>Look up an existing claim</small></div></button><button class="action" data-view="analytics"><span>▥</span><div><strong>View Analytics</strong><small>Claims trends and insights</small></div></button></section>
  <section class="panel"><h3>Claims Summary</h3>${[
    ["Total Charges Filed", money(a.total_amount)],
    ["Approved / All Claims", a.approval_rate + "%"],
    ["Average Claim Amount", money(a.average_amount)],
    ["Services This Month", a.this_month],
  ]
    .map(
      ([l, v]) =>
        `<div class="summary-line"><span>${l}</span><strong>${v}</strong></div>`,
    )
    .join("")}</section></div>
  <section class="panel"><div class="panel-head"><h3>Recent Claims</h3><button class="btn btn-sm btn-outline-primary" data-view="tracker">View All →</button></div>${table(c.items)}</section>`;
}
async function tracker() {
  const p = new URLSearchParams({ q: query, offset: page * 10, limit: 10 });
  if (filterStatus) p.set("status", filterStatus);
  if (filterService) p.set("service_type", filterService);
  const c = await api("/claims?" + p);
  $("#content").innerHTML =
    `<h2>Claims Tracker</h2><p class="subtitle">Search and filter claims. Select a claim ID to view details and its history.</p><form id="filters" class="filters"><input aria-label="Search claims by ID, member name, or patient ID" name="q" class="form-control" placeholder="Search by claim ID, member, or patient ID…" value="${esc(query)}"><select aria-label="Filter by status" name="status" class="form-select"><option value="">All Statuses</option>${option(statuses, filterStatus)}</select><select aria-label="Filter by service type" name="service" class="form-select"><option value="">All Types</option>${option(services, filterService)}</select><button class="btn btn-primary">Search</button></form><section class="panel"><p class="text-secondary">${c.total} claims found</p>${table(c.items)}<div class="pagination-row"><button class="btn btn-sm btn-outline-secondary" id="prev-page" ${page === 0 ? "disabled" : ""}>← Previous</button><span>Page ${page + 1} of ${Math.max(1, Math.ceil(c.total / 10))}</span><button class="btn btn-sm btn-outline-secondary" id="next-page" ${(page + 1) * 10 >= c.total ? "disabled" : ""}>Next →</button></div></section>`;
}
function chart(title, data, currency = false) {
  const max = Math.max(1, ...Object.values(data));
  return `<section class="panel"><h3>${title}</h3><div class="bars">${
    Object.entries(data)
      .map(
        ([k, v]) =>
          `<div><div class="bar-label"><span>${esc(k)}</span><strong>${currency ? money(v) : v}</strong></div><div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${Math.max(0, (v / max) * 100)}%"></div></div></div>`,
      )
      .join("") || '<p class="empty">No data yet</p>'
  }</div><p class="chart-note">Calculated from stored synthetic claims</p></section>`;
}
async function analytics() {
  const a = await api("/analytics");
  $("#content").innerHTML =
    `<h2>Claims Analytics</h2><p class="subtitle">Live summaries of submissions, status, and financial trends.</p>${stats(
      [
        ["Total Charges Filed", money(a.total_amount), "$"],
        ["Approved Amount", money(a.approved_amount), "✓"],
        ["Denied Amount", money(a.denied_amount), "!"],
        ["Approved / All Claims", a.approval_rate + "%", "%"],
      ],
    )}<div class="grid-two">${chart("Claims by Status", a.by_status)}${chart("Claims by Service Type", a.by_service)}${chart("Monthly Service Volume", a.by_month)}${chart("Total Charges by Provider", a.by_provider, true)}</div>`;
}
const steps = [
  "Member Info",
  "Provider Details",
  "Service Information",
  "Additional Info",
  "Review & Submit",
];
const fields = [
  [
    ["patient_id", "Patient / Member ID", "text", true],
    ["group_number", "Group Number"],
    ["first_name", "First Name", "text", true],
    ["last_name", "Last Name", "text", true],
    ["date_of_birth", "Date of Birth", "date"],
    ["phone", "Phone", "tel"],
    ["email", "Email", "email"],
  ],
  [
    ["provider_name", "Provider Name", "text", true],
    ["provider_id", "Provider ID", "text", true],
    ["npi", "NPI (10 digits)"],
    ["provider_address", "Provider Address"],
    [
      "claim_type",
      "Claim Type",
      ["Professional", "Institutional", "Dental", "Pharmacy"],
      true,
    ],
  ],
  [
    ["service_type", "Service Type", services, true],
    ["service_date", "Date of Service", "date", true],
    ["diagnosis_code", "ICD-10 Diagnosis Code", "text", true],
    ["procedure_code", "CPT / HCPCS Procedure Code", "text", true],
    ["diagnosis_description", "Diagnosis Description"],
    ["amount", "Total Charges ($)", "number", true],
    [
      "place_of_service",
      "Place of Service",
      [
        "Office",
        "Outpatient Hospital",
        "Inpatient Hospital",
        "Emergency Room",
        "Telehealth",
        "Other",
      ],
    ],
    ["admission_date", "Admission Date", "date"],
    ["discharge_date", "Discharge Date", "date"],
  ],
  [
    ["prior_authorization", "Prior Authorization Number"],
    ["other_insurance", "Other Insurance Coverage", ["No", "Yes"]],
    ["other_insurer", "Other Insurer"],
    [
      "injury_type",
      "Accident / Injury",
      ["None", "Auto", "Work-related", "Other"],
    ],
    ["notes", "Additional Notes", "textarea"],
  ],
];
function inputField([name, label, type = "text", required = false]) {
  let value = draft[name] ?? "";
  const id = "f-" + name;
  const common = `id="${id}" name="${name}" ${required ? "required" : ""}`;
  let control;
  if (Array.isArray(type))
    control = `<select class="form-select" ${common}>${option(type, value || type[0])}</select>`;
  else if (type === "textarea")
    control = `<textarea class="form-control" ${common} rows="3" maxlength="2000">${esc(value)}</textarea>`;
  else
    control = `<input class="form-control" ${common} type="${type}" value="${esc(value)}" ${type === "number" ? 'min="0.01" max="10000000" step="0.01"' : ""} ${name === "npi" ? 'pattern="[0-9]{10}" maxlength="10"' : type === "text" ? 'maxlength="160"' : ""}>`;
  return `<div class="${type === "textarea" ? "full" : ""}"><label class="form-label" for="${id}">${label}${required ? ' <span class="required">*</span>' : ""}</label>${control}</div>`;
}
function newClaim() {
  if (!can("Writer"))
    throw Error("Your account does not have claim submission permission.");
  let body;
  if (step < 4)
    body = `<div class="form-grid">${fields[step].map(inputField).join("")}</div>`;
  else
    body = `<p>Review the information below. Submission stores a synthetic claim and its initial timeline event.</p><div class="review-grid">${fields
      .flat()
      .map(
        ([key, label]) =>
          `<div><small>${label}</small>${esc(draft[key] || "—")}</div>`,
      )
      .join(
        "",
      )}</div><div class="form-check mt-4"><input class="form-check-input" id="confirm" type="checkbox" required><label class="form-check-label" for="confirm">I confirm this is fictitious demonstration data, with no real patient information.</label></div>`;
  $("#content").innerHTML =
    `<h2>File New Health Claim</h2><p class="subtitle">Complete the required fields to submit a synthetic health insurance claim.</p><ol class="steps">${steps.map((s, i) => `<li class="${i === step ? "active" : i < step ? "done" : ""}" ${i === step ? 'aria-current="step"' : ""}>${i + 1}. ${s}</li>`).join("")}</ol><form id="claim-form" class="panel"><h3 class="mb-4">${steps[step]}</h3>${body}<div class="form-actions"><button type="button" class="btn btn-outline-secondary" id="previous" ${step === 0 ? "disabled" : ""}>← Previous</button><button class="btn btn-primary" id="next">${step === 4 ? "Submit Claim" : "Next Step →"}</button></div></form>`;
}
function saveStep() {
  if (step < 4) {
    for (const [key, value] of new FormData($("#claim-form")).entries())
      draft[key] = value;
  }
}
async function submitStep(event) {
  event.preventDefault();
  saveStep();
  notice();
  if (step < 4) {
    step++;
    newClaim();
    return;
  }
  const button = $("#next");
  button.disabled = true;
  const data = {
    ...draft,
    other_insurance: draft.other_insurance === "Yes",
    synthetic_data_confirmed: true,
  };
  for (const key of ["date_of_birth", "admission_date", "discharge_date"])
    if (!data[key]) data[key] = null;
  try {
    const c = await api("/claims", {
      method: "POST",
      headers: { "Idempotency-Key": requestKey },
      body: JSON.stringify(data),
    });
    draft = {};
    step = 0;
    requestKey = crypto.randomUUID();
    await navigate("tracker");
    notice(`Claim ${c.id} submitted successfully.`);
  } catch (e) {
    notice(e.message, true);
    button.disabled = false;
  }
}
async function showClaim(id) {
  const c = await api("/claims/" + encodeURIComponent(id));
  selectedClaim = c;
  transitions = transitions || (await api("/transitions"));
  $("#detail-body").innerHTML =
    `<div class="panel-head"><h3 id="detail-title">${esc(c.id)}</h3><button class="btn btn-sm btn-outline-secondary" id="close-detail" aria-label="Close claim details">✕</button></div>${badge(c.status)}<div class="review-grid">${[
      ["Member", c.patient_name],
      ["Patient / Member ID", c.patient_id],
      ["Provider", c.data.provider_name],
      ["Provider ID", c.data.provider_id],
      ["NPI", c.data.npi],
      ["Service Date", c.data.service_date],
      ["ICD-10", c.data.diagnosis_code],
      ["CPT / HCPCS", c.data.procedure_code],
      ["Charges", money(c.amount)],
      ["Claim Type", c.data.claim_type],
      ["Prior Authorization", c.data.prior_authorization],
      ["Notes", c.data.notes],
    ]
      .map(([k, v]) => `<div><small>${esc(k)}</small>${esc(v || "—")}</div>`)
      .join(
        "",
      )}</div><h3 class="mt-4">Claim Timeline</h3><div class="timeline">${c.history.map((h) => `<article><strong>${esc(h.status)}</strong><small>${esc(new Date(h.at).toLocaleString())}</small><p>${esc(h.note)}</p></article>`).join("")}</div>
  ${can("Reviewer") && transitions[c.status].length ? `<form id="status-form"><h3>Review this synthetic claim</h3><label class="form-label" for="new-status">Next status</label><select id="new-status" class="form-select">${option(transitions[c.status])}</select><label class="form-label mt-3" for="status-note">Reason / review note</label><textarea id="status-note" class="form-control" required minlength="3" maxlength="500"></textarea><button class="btn btn-primary mt-3">Record status change</button><p id="status-error" class="text-danger mt-2" role="alert"></p></form>` : ""}`;
  if (!$("#detail-dialog").open) $("#detail-dialog").showModal();
}
async function navigate(next) {
  view = next;
  notice();
  document.querySelectorAll("nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    b.setAttribute("aria-current", b.dataset.view === view ? "page" : "false");
  });
  $("#content").innerHTML = '<p class="loading">Loading…</p>';
  try {
    await (
      { dashboard, tracker, analytics, new: newClaim }[view] || dashboard
    )();
  } catch (e) {
    $("#content").innerHTML =
      '<section class="panel"><h2>Unable to load this view</h2><p>Check your connection and account permissions, then select the view again.</p></section>';
    notice(e.message, true);
  }
}
document.addEventListener("click", async (event) => {
  const b = event.target.closest("button");
  if (!b) return;
  try {
    if (b.dataset.view) {
      if (view === "new" && step < 4 && $("#claim-form")) saveStep();
      await navigate(b.dataset.view);
    }
    if (b.dataset.claim) await showClaim(b.dataset.claim);
    if (b.id === "previous") {
      saveStep();
      step--;
      newClaim();
    }
    if (b.id === "prev-page") {
      page--;
      await tracker();
    }
    if (b.id === "next-page") {
      page++;
      await tracker();
    }
    if (b.id === "close-detail") $("#detail-dialog").close();
    if (b.id === "collapse") {
      document.body.classList.toggle("collapsed");
      b.setAttribute(
        "aria-expanded",
        !document.body.classList.contains("collapsed"),
      );
    }
    if (b.id === "login") await auth.loginRedirect({ scopes: [config.scope] });
    if (b.id === "logout")
      await auth.logoutRedirect({
        postLogoutRedirectUri: location.origin + "/",
      });
  } catch (e) {
    notice(e.message, true);
  }
});
document.addEventListener("submit", async (event) => {
  if (event.target.id === "claim-form") {
    await submitStep(event);
    return;
  }
  event.preventDefault();
  if (event.target.id === "filters") {
    const f = new FormData(event.target);
    query = f.get("q");
    filterStatus = f.get("status");
    filterService = f.get("service");
    page = 0;
    try {
      await tracker();
    } catch (e) {
      notice(e.message, true);
    }
  }
  if (event.target.id === "status-form") {
    const b = event.target.querySelector("button");
    b.disabled = true;
    try {
      await api("/claims/" + encodeURIComponent(selectedClaim.id) + "/status", {
        method: "PATCH",
        body: JSON.stringify({
          status: $("#new-status").value,
          note: $("#status-note").value,
          expected_version: selectedClaim.version,
        }),
      });
      $("#detail-dialog").close();
      await navigate(view);
      notice("Status change recorded.");
    } catch (e) {
      $("#status-error").textContent = e.message;
      b.disabled = false;
    }
  }
});
async function init() {
  try {
    config = await (await fetch("/api/config")).json();
    if (config.auth_mode === "entra") {
      auth = new msal.PublicClientApplication({
        auth: {
          clientId: config.spa_client_id,
          authority: config.authority,
          redirectUri: location.origin + "/",
        },
        cache: { cacheLocation: "sessionStorage" },
      });
      await auth.initialize();
      await auth.handleRedirectPromise();
      if (!auth.getAllAccounts().length) {
        $("#login").hidden = false;
        $("#content").innerHTML =
          '<section class="hero"><h1>Welcome to HealthClaim</h1><p>Sign in with your authorized work account to access the claims workspace.</p></section>';
        return;
      }
      $("#logout").hidden = false;
    } else {
      $("#identity").textContent = "Local development identity";
    }
    const user = await api("/me");
    roles = user.roles;
    if (config.auth_mode === "entra")
      $("#identity").textContent = "Work account";
    await navigate("dashboard");
  } catch (e) {
    $("#content").innerHTML =
      '<section class="panel"><h2>Workspace unavailable</h2><p>Check the application configuration or contact your administrator.</p></section>';
    notice(e.message, true);
  }
}
init();
