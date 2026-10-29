const $ = (sel) => document.querySelector(sel);

const thread = $("#thread");
const savingsEl = $("#savings");
const moneyEl = $("#savings-money");
const timeEl = $("#savings-time");
const deltaEl = $("#savings-delta");
const subsEl = $("#subscriptions");
const deadlinesEl = $("#deadlines");
const recordedBadge = $("#recorded-badge");
const demoResetBtn = $("#demo-reset");
const skillsDrawer = $("#skills-drawer");
const skillsBody = $("#skills-body");
const backdrop = $("#drawer-backdrop");

/** @type {number | null} */
let lastSavingsCents = null;
/** @type {number | null} */
let lastEventId = null;
/** @type {Array<{id:number, merchant:string, status:string, amount_monthly_cents:number}>} */
let subscriptionsCache = [];
/** @type {Array<{id:number, name:string, merchant:string}>} */
let skillsCache = [];

function money(cents) {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}$${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

function moneyWhole(cents) {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  if (abs % 100 === 0) return `${sign}$${abs / 100}`;
  return money(cents);
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
  if (action === "approve") return "Send claim";
  if (action === "reject") return "Reject";
  if (action === "edit") return "Edit";
  if (action === "Confirm" || action === "cancel") return "Cancel subscription";
  if (action === "Prepare claim") return "Prepare claim";
  return action;
}

function skillLabel(skillId) {
  if (skillId == null) return "saved skill";
  const skill = skillsCache.find((s) => Number(s.id) === Number(skillId));
  return skill?.name || `skill #${skillId}`;
}

function renderCard(card) {
  const el = document.createElement("article");
  el.className = "card";
  el.dataset.type = card.type || "";
  if (card.claim_id != null) el.dataset.claimId = String(card.claim_id);
  if (card.subscription_id != null) el.dataset.subscriptionId = String(card.subscription_id);
  if (card.merchant) el.dataset.merchant = String(card.merchant);
  if (card.purchase_id != null) el.dataset.purchaseId = String(card.purchase_id);
  if (card.path) el.dataset.path = String(card.path);
  if (card.skill_id != null) el.dataset.skillId = String(card.skill_id);

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
  let hasSend = false;
  for (const action of card.actions || []) {
    const btn = document.createElement("button");
    const label = actionLabel(action);
    btn.textContent = label;
    btn.type = "button";
    if (label === "Send claim" || label === "Cancel subscription" || action === "Prepare claim") {
      btn.className = "primary";
    } else if (label === "Reject") {
      btn.className = "danger";
    } else {
      btn.className = "secondary";
    }
    if (label === "Send claim") hasSend = true;
    btn.addEventListener("click", () => onCardAction(card, action, el));
    actions.appendChild(btn);
  }
  if (hasSend) {
    const note = document.createElement("p");
    note.className = "send-note";
    note.textContent =
      "Send claim posts to a test outbox (mock merchant inbox), not a real company.";
    actions.appendChild(note);
  }
  if ((card.actions || []).length) el.appendChild(actions);

  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
}

async function onCardAction(card, action, el) {
  try {
    if (card.type === "claim_draft" && action === "approve") {
      await api("POST", `/api/claims/${card.claim_id}/approve`);
      appendMessage("agent", "Claim sent to the test merchant outbox.");
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
      if (
        (action === "Confirm" || action === "cancel") &&
        card.path &&
        card.path !== "pending"
      ) {
        await api("POST", `/api/subscriptions/${card.subscription_id}/cancel/confirm`);
        appendMessage("agent", `Cancelled ${card.merchant || "subscription"}.`);
        el.remove();
      } else {
        await startCancelFlow(card.subscription_id, {
          replaceEl: el,
          announceSkill: true,
        });
      }
      await refreshAll();
      return;
    }
    appendMessage("agent", `Action “${action}” is not wired for this card.`);
  } catch (err) {
    appendMessage("agent", err.message || String(err));
  }
}

/**
 * Start cancel for a subscription; shows skill reuse line when path is skill.
 * @returns {Promise<object>}
 */
async function startCancelFlow(subscriptionId, { replaceEl = null, announceSkill = true } = {}) {
  const started = await api("POST", `/api/subscriptions/${subscriptionId}/cancel`);
  if (announceSkill && started.path === "skill") {
    appendMessage(
      "agent",
      `I already know how (skill ${skillLabel(started.skill_id)}).`
    );
  }
  if (started.card) {
    const next = {
      ...started.card,
      subscription_id: started.card.subscription_id ?? subscriptionId,
      title: started.card.title || `Cancel ${started.merchant}?`,
      body:
        started.card.body ||
        (started.path === "skill"
          ? "Confirm to replay the saved cancel steps."
          : "Confirm to run the planned cancel steps."),
      actions: started.card.actions || ["Confirm"],
    };
    if (replaceEl) replaceEl.remove();
    renderCard(next);
  }
  return started;
}

async function cancelSubscriptionById(subscriptionId, merchant) {
  const existing = thread.querySelector(
    `.card[data-type='cancel_plan'][data-subscription-id='${subscriptionId}']`
  );
  await startCancelFlow(subscriptionId, {
    replaceEl: existing,
    announceSkill: true,
  });
  if (merchant) {
    appendMessage(
      "agent",
      `Ready to cancel ${merchant}. Press Cancel subscription on the card to confirm.`
    );
  }
  await refreshAll();
}

async function cancelSubscriptionByMerchant(merchantQuery) {
  const needle = merchantQuery.trim().toLowerCase();
  if (!subscriptionsCache.length) await refreshSubscriptions();
  const sub = subscriptionsCache.find(
    (s) =>
      s.status !== "cancelled" &&
      String(s.merchant || "").toLowerCase() === needle
  );
  if (!sub) {
    const active = subscriptionsCache
      .filter((s) => s.status !== "cancelled")
      .map((s) => s.merchant)
      .join(", ");
    appendMessage(
      "agent",
      active
        ? `No active subscription named “${merchantQuery}”. Active: ${active}.`
        : `No active subscription named “${merchantQuery}”.`
    );
    return;
  }
  await cancelSubscriptionById(sub.id, sub.merchant);
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

function showSavingsDelta(event) {
  if (!deltaEl || !event) return;
  const kind =
    event.kind === "cancel"
      ? `${event.merchant} cancellation`
      : event.kind === "refund"
        ? `${event.merchant} refund`
        : event.merchant || "savings";
  deltaEl.textContent = `+${moneyWhole(event.amount_cents)} ${kind}`;
  deltaEl.classList.remove("hidden");
}

async function refreshSavings() {
  const data = await api("GET", "/api/savings");
  const cents = data.amount_cents || 0;
  const events = data.events || [];
  const prevCents = lastSavingsCents;
  const prevEventId = lastEventId;
  const newest = events.length ? events[events.length - 1] : null;

  moneyEl.textContent = money(cents);
  timeEl.textContent = hours(data.time_saved_min || 0);

  if (prevCents != null && cents > prevCents && newest && newest.id !== prevEventId) {
    showSavingsDelta(newest);
    savingsEl.classList.remove("bump");
    void savingsEl.offsetWidth;
    savingsEl.classList.add("bump");
  }

  lastSavingsCents = cents;
  lastEventId = newest ? newest.id : null;
}

async function refreshSubscriptions() {
  const data = await api("GET", "/api/subscriptions");
  subscriptionsCache = data.subscriptions || [];
  subsEl.innerHTML = "";
  for (const sub of subscriptionsCache) {
    const li = document.createElement("li");
    const unused = sub.unused || sub.status === "flagged";
    if (unused) li.classList.add("flagged");
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `${money(sub.amount_monthly_cents)}/mo · ${sub.status}${
      unused ? " · unused" : ""
    }`;

    const strong = document.createElement("strong");
    strong.textContent = sub.merchant;
    li.appendChild(strong);
    li.appendChild(meta);

    if (sub.status !== "cancelled") {
      const row = document.createElement("div");
      row.className = "row-actions";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Cancel subscription";
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          appendMessage("user", `cancel ${sub.merchant}`);
          await cancelSubscriptionById(sub.id, sub.merchant);
        } catch (err) {
          appendMessage("agent", err.message || String(err));
          btn.disabled = false;
        }
      });
      row.appendChild(btn);
      li.appendChild(row);
    }
    subsEl.appendChild(li);
  }
  if (!subsEl.children.length) {
    const li = document.createElement("li");
    li.className = "empty-hint";
    li.textContent =
      "No subscriptions yet. Ingest a bank statement to discover recurring charges.";
    subsEl.appendChild(li);
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
    const li = document.createElement("li");
    li.className = "empty-hint";
    li.textContent =
      "No open deadlines. After a purchase is ingested, run a scan to surface refund windows.";
    deadlinesEl.appendChild(li);
  }
}

async function refreshSkills() {
  const data = await api("GET", "/api/skills");
  skillsCache = data.skills || [];
  skillsBody.innerHTML = "";
  for (const skill of skillsCache) {
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
    skillsBody.innerHTML =
      '<p class="empty-hint-block">No skills learned yet. Cancel a subscription once and Clawback will save the steps here.</p>';
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

  const cancelMatch = (message || "").trim().match(/^cancel\s+(.+)$/i);
  if (cancelMatch) {
    await cancelSubscriptionByMerchant(cancelMatch[1]);
    return;
  }

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
  es.addEventListener("demo.reset", async () => {
    await refreshAll();
    appendMessage("agent", "Demo was reset. Refreshing shared state.");
  });
  es.onerror = () => {
    // Browser will retry; no UI spam.
  };
}

function applyHealthBadge(health) {
  if (!recordedBadge) return;
  const label = health?.badge;
  if (label) {
    recordedBadge.textContent = label;
    recordedBadge.title =
      label.includes("budget")
        ? "Live model budget exhausted; using cached responses"
        : "Using cached model and search responses";
    recordedBadge.classList.remove("hidden");
  } else if (health?.recorded_mode || health?.live_budget_exhausted) {
    recordedBadge.textContent = health.live_budget_exhausted
      ? "recorded (live budget used)"
      : "recorded";
    recordedBadge.classList.remove("hidden");
  } else {
    recordedBadge.classList.add("hidden");
  }
}

async function resetDemo() {
  if (!window.confirm("Reset the shared demo for everyone? This cannot be undone.")) {
    return;
  }
  try {
    await api("POST", "/api/demo/reset");
    await refreshAll();
    appendMessage("agent", "Demo reset complete.");
  } catch (err) {
    appendMessage("agent", err.message || String(err));
  }
}

async function boot() {
  try {
    const health = await api("GET", "/api/health");
    applyHealthBadge(health);
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
if (demoResetBtn) demoResetBtn.addEventListener("click", resetDemo);

boot();
