const $ = (sel) => document.querySelector(sel);

const thread = $("#thread");
const savingsEl = $("#savings");
const moneyEl = $("#savings-money");
const timeEl = $("#savings-time");
const subsEl = $("#subscriptions");
const deadlinesEl = $("#deadlines");
const recordedBadge = $("#recorded-badge");
const skillsDrawer = $("#skills-drawer");
const skillsBody = $("#skills-body");
const backdrop = $("#drawer-backdrop");

function money(cents) {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}$${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

function hours(minutes) {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

function appendMessage(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
}

function actionLabel(action) {
  if (action === "approve") return "Send";
  if (action === "reject") return "Reject";
  if (action === "edit") return "Edit";
  return action;
}

function renderCard(card) {
  const el = document.createElement("article");
  el.className = "card";
  el.dataset.type = card.type || "";
  if (card.claim_id != null) el.dataset.claimId = String(card.claim_id);
  if (card.subscription_id != null) el.dataset.subscriptionId = String(card.subscription_id);
  if (card.merchant) el.dataset.merchant = String(card.merchant);
  if (card.purchase_id != null) el.dataset.purchaseId = String(card.purchase_id);

  const title = document.createElement("h3");
  title.textContent = card.title || card.type || "Action";
  el.appendChild(title);

  if (card.body) {
    const body = document.createElement("p");
    body.className = "body";
    body.textContent = card.body;
    el.appendChild(body);
  }

  if (Array.isArray(card.sources) && card.sources.length) {
    const sources = document.createElement("div");
    sources.className = "sources";
    for (const src of card.sources) {
      const a = document.createElement("a");
      a.href = src.url || "#";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = src.title || src.url || "Source";
      sources.appendChild(a);
    }
    el.appendChild(sources);
  }

  if (Array.isArray(card.steps) && card.steps.length) {
    const ol = document.createElement("ol");
    for (const step of card.steps) {
      const li = document.createElement("li");
      li.textContent = typeof step === "string" ? step : (step.note || step.action || "");
      ol.appendChild(li);
    }
    el.appendChild(ol);
  }

  const actions = document.createElement("div");
  actions.className = "actions";
  for (const action of card.actions || []) {
    const btn = document.createElement("button");
    const label = actionLabel(action);
    btn.textContent = label;
    btn.type = "button";
    if (label === "Send" || action === "Confirm" || action === "Prepare claim") {
      btn.className = "primary";
    } else if (label === "Reject") {
      btn.className = "danger";
    } else {
      btn.className = "secondary";
    }
    btn.addEventListener("click", () => onCardAction(card, action, el));
    actions.appendChild(btn);
  }
  if ((card.actions || []).length) el.appendChild(actions);

  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
}

async function onCardAction(card, action, el) {
  try {
    if (card.type === "claim_draft" && action === "approve") {
      await api("POST", `/api/claims/${card.claim_id}/approve`);
      appendMessage("agent", "Claim sent to the merchant outbox.");
      el.remove();
      await refreshSavings();
      return;
    }
    if (card.type === "claim_draft" && action === "reject") {
      await api("POST", `/api/claims/${card.claim_id}/reject`);
      appendMessage("agent", "Claim rejected.");
      el.remove();
      return;
    }
    if (card.type === "deadline_alert" && action === "Prepare claim" && card.purchase_id) {
      const res = await api("POST", "/api/claims/prepare", { purchase_id: card.purchase_id });
      if (res.card) renderCard(res.card);
      else if (res.error) appendMessage("agent", res.error.message || "Could not prepare claim.");
      else appendMessage("agent", "Claim prepared.");
      await refreshAll();
      return;
    }
    if (card.type === "cancel_plan" && card.subscription_id) {
      if (action === "Confirm" && card.path && card.path !== "pending") {
        await api("POST", `/api/subscriptions/${card.subscription_id}/cancel/confirm`);
        appendMessage("agent", `Cancelled ${card.merchant || "subscription"}.`);
        el.remove();
      } else {
        const started = await api("POST", `/api/subscriptions/${card.subscription_id}/cancel`);
        if (started.card) {
          const next = {
            ...started.card,
            subscription_id: started.card.subscription_id ?? card.subscription_id,
          };
          el.remove();
          renderCard(next);
        }
      }
      await refreshAll();
      return;
    }
    appendMessage("agent", `Action “${action}” is not wired for this card.`);
  } catch (err) {
    appendMessage("agent", err.message || String(err));
  }
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.detail?.error?.message || data?.error?.message || res.statusText;
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

async function refreshSavings() {
  const data = await api("GET", "/api/savings");
  const prev = moneyEl.textContent;
  moneyEl.textContent = money(data.amount_cents || 0);
  timeEl.textContent = hours(data.time_saved_min || 0);
  if (prev && prev !== moneyEl.textContent) {
    savingsEl.classList.remove("bump");
    void savingsEl.offsetWidth;
    savingsEl.classList.add("bump");
  }
}

async function refreshSubscriptions() {
  const data = await api("GET", "/api/subscriptions");
  subsEl.innerHTML = "";
  for (const sub of data.subscriptions || []) {
    const li = document.createElement("li");
    const unused = sub.unused || sub.status === "flagged";
    if (unused) li.classList.add("flagged");
    li.innerHTML = `<strong>${sub.merchant}</strong>
      <span class="meta">${money(sub.amount_monthly_cents)}/mo · ${sub.status}${unused ? " · unused" : ""}</span>`;
    subsEl.appendChild(li);
  }
  if (!subsEl.children.length) {
    subsEl.innerHTML = "<li><span class=\"meta\">None yet</span></li>";
  }
}

async function refreshDeadlines() {
  const data = await api("GET", "/api/deadlines");
  deadlinesEl.innerHTML = "";
  for (const d of data.deadlines || []) {
    const li = document.createElement("li");
    const days = d.days_left;
    li.innerHTML = `<strong>${d.merchant || d.item}</strong>
      <span class="meta">${days == null ? "—" : `${days} day(s) left`} · ${d.item || ""}</span>`;
    deadlinesEl.appendChild(li);
  }
  if (!deadlinesEl.children.length) {
    deadlinesEl.innerHTML = "<li><span class=\"meta\">No open deadlines</span></li>";
  }
}

async function refreshSkills() {
  const data = await api("GET", "/api/skills");
  skillsBody.innerHTML = "";
  for (const skill of data.skills || []) {
    const block = document.createElement("div");
    block.className = "skill-block";
    const steps = (skill.steps || [])
      .map((s) => `<li>${s.note || s.action || s}</li>`)
      .join("");
    block.innerHTML = `<strong>${skill.name}</strong>
      <div class="meta">${skill.merchant} · ${skill.portal_template}</div>
      <ol>${steps}</ol>`;
    skillsBody.appendChild(block);
  }
  if (!skillsBody.children.length) {
    skillsBody.innerHTML = "<p class=\"meta\">No skills learned yet.</p>";
  }
}

async function refreshAll() {
  await Promise.all([
    refreshSavings(),
    refreshSubscriptions(),
    refreshDeadlines(),
    refreshSkills(),
  ]);
}

async function sendChat(message) {
  if (message) appendMessage("user", message);
  const data = await api("POST", "/api/chat", { message: message || "" });
  if (data.reply) appendMessage("agent", data.reply);
  for (const card of data.cards || []) renderCard(card);
}

function openSkills() {
  skillsDrawer.hidden = false;
  backdrop.hidden = false;
}

function closeSkills() {
  skillsDrawer.hidden = true;
  backdrop.hidden = true;
}

function connectEvents() {
  const es = new EventSource("/api/events");
  es.addEventListener("savings.changed", () => refreshSavings());
  es.addEventListener("subscription.changed", () => refreshSubscriptions());
  es.addEventListener("claim.changed", async () => {
    await refreshDeadlines();
    // Re-pull actionable cards without duplicating a user message.
    const data = await api("POST", "/api/chat", { message: "status" });
    // Only append new claim cards not already in the thread.
    const seen = new Set(
      [...thread.querySelectorAll(".card[data-claim-id]")].map((n) => n.dataset.claimId)
    );
    for (const card of data.cards || []) {
      if (card.type === "claim_draft" && !seen.has(String(card.claim_id))) {
        renderCard(card);
      }
    }
  });
  es.addEventListener("notification.new", () => refreshDeadlines());
  es.addEventListener("skill.saved", () => refreshSkills());
  es.onerror = () => {
    // Browser will retry; no UI spam.
  };
}

async function boot() {
  try {
    const health = await api("GET", "/api/health");
    if (health.recorded_mode) recordedBadge.classList.remove("hidden");
  } catch {
    /* ignore */
  }
  await refreshAll();
  await sendChat("");
  connectEvents();
}

$("#chat-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("#chat-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  try {
    await sendChat(message);
  } catch (err) {
    appendMessage("agent", err.message || String(err));
  }
});

$("#skills-toggle").addEventListener("click", openSkills);
$("#skills-close").addEventListener("click", closeSkills);
backdrop.addEventListener("click", closeSkills);

boot();
