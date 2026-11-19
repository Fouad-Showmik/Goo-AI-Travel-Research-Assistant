const messageList = document.querySelector("#message-list");
const quickReplies = document.querySelector("#quick-replies");
const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const newChatButton = document.querySelector("#new-chat");
const chatView = document.querySelector("#chat-view");
const sourcesView = document.querySelector("#sources-view");
const exportButton = document.querySelector("#export-plan");
const shareButton = document.querySelector("#share-plan");

const DEFAULT_GREETING =
  "Hello! I'm Goo, your AI travel research assistant. Tell me where you'd like to go, where you're travelling from, how many people are travelling, and how long you'd like to stay. I'll help research the destination, weather, and estimated budget.";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function renderInlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_match, label, url) => {
    const safeUrl = url.replace(/&amp;/g, "&");
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>");
  return html;
}

// A small, dependency-free Markdown renderer for assistant replies.
// All text is escaped before formatting; only HTTP(S) Markdown links are clickable.
export function renderMarkdown(markdown) {
  const lines = String(markdown ?? "").replace(/\r\n/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let listType = null;
  let tableRows = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      output.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (!listType) return;
    output.push(`</${listType}>`);
    listType = null;
  };
  const flushTable = () => {
    if (!tableRows.length) return;
    const rows = tableRows.filter((row) => !/^\s*\|?\s*:?-{3,}/.test(row));
    if (rows.length) {
      const renderedRows = rows.map((row, index) => {
        const cells = row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|");
        const tag = index === 0 ? "th" : "td";
        return `<tr>${cells.map((cell) => `<${tag}>${renderInlineMarkdown(cell.trim())}</${tag}>`).join("")}</tr>`;
      }).join("");
      output.push(`<table><tbody>${renderedRows}</tbody></table>`);
    }
    tableRows = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      flushTable();
      continue;
    }
    if (/^\|.*\|$/.test(trimmed)) {
      flushParagraph();
      flushList();
      tableRows.push(trimmed);
      continue;
    }
    flushTable();

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(heading[1].length + 1, 4);
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        flushList();
        output.push(`<${nextType}>`);
        listType = nextType;
      }
      output.push(`<li>${renderInlineMarkdown((unordered || ordered)[1])}</li>`);
      continue;
    }

    flushList();
    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      output.push("<hr>");
    } else {
      paragraph.push(trimmed);
    }
  }
  flushParagraph();
  flushList();
  flushTable();
  return output.join("");
}

function createBotAvatar() {
  const avatar = document.createElement("span");
  avatar.className = "bot-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.innerHTML = '<svg viewBox="0 0 32 32"><path d="M5 14.3 26.5 5.5 18 27l-3.2-8.3L5 14.3Z"/><path d="m14.8 18.7 6.1-6.1"/></svg>';
  return avatar;
}

export function addBubble(type, text = "") {
  const row = document.createElement("li");
  row.classList.add("message-row", `message-row-${type}`);
  if (type !== "user") row.append(createBotAvatar());

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = renderMarkdown(text);
  row.append(bubble);
  messageList.append(row);
  scrollToLatest();
  return bubble;
}

export function showTypingIndicator(bubble) {
  updateBubbleStatus(bubble, "Goo is thinking");
}

export function updateBubbleStatus(bubble, message) {
  bubble.setAttribute("aria-label", message);
  bubble.replaceChildren();

  const indicator = document.createElement("span");
  indicator.className = "typing-indicator";
  indicator.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement("span");
    dot.className = "typing-dot";
    indicator.append(dot);
  }

  const label = document.createElement("span");
  label.className = "stream-status-label";
  label.textContent = message;
  bubble.append(indicator, label);
  scrollToLatest();
}

export function updateDashboardStatus(message, active = true) {
  const banner = document.querySelector("#dashboard-stream-status");
  const label = document.querySelector("#dashboard-stream-status-text");
  if (!banner || !label) return;
  label.textContent = message || "";
  banner.hidden = !active;
  banner.classList.toggle("is-complete", Boolean(message && message.endsWith("complete")));
  banner.classList.toggle("is-error", Boolean(message && message.startsWith("Streaming interrupted")));
}

export function updateBubble(bubble, type, text) {
  bubble.innerHTML = renderMarkdown(text);
  bubble.removeAttribute("aria-label");
  const row = bubble.parentElement;
  row.classList.remove("message-row-bot", "message-row-error");
  row.classList.add(`message-row-${type}`);
  scrollToLatest();
}

export function resetChatView() {
  messageList.replaceChildren();
  addBubble("bot", DEFAULT_GREETING);
  quickReplies.hidden = false;
  messageInput.value = "";
  resizeComposer();
  setActiveView("chat");
  resetDashboard();
  focusMessageInput();
}

export function setSending(isSending) {
  messageInput.disabled = isSending;
  sendButton.disabled = isSending;
  newChatButton.disabled = isSending;
  messageInput.setAttribute("aria-busy", String(isSending));
  sendButton.setAttribute("aria-label", isSending ? "Goo is responding" : "Send message");
  sendButton.innerHTML = isSending
    ? '<span class="button-spinner" aria-hidden="true"></span>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 4 17 8-17 8 3-8-3-8Z"/><path d="M7 12h14"/></svg>';
  quickReplies.querySelectorAll("button").forEach((button) => { button.disabled = isSending; });
}

function resizeComposer() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 150)}px`;
}

export function focusMessageInput() {
  messageInput.focus({ preventScroll: true });
}

function setActiveView(view) {
  const showChat = view !== "sources";
  chatView.hidden = !showChat;
  sourcesView.hidden = showChat;
  document.querySelectorAll("[data-view]").forEach((element) => {
    if (element.classList.contains("nav-item")) {
      const active = element.dataset.view === view;
      element.classList.toggle("is-active", active);
      if (active) element.setAttribute("aria-current", "page");
      else element.removeAttribute("aria-current");
    }
  });
}

export function initializeUI({ onSend, onNewChat, onExport, onShare }) {
  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = messageInput.value.trim();
    if (!message || sendButton.disabled) return;
    messageInput.value = "";
    resizeComposer();
    quickReplies.hidden = true;
    setActiveView("chat");
    onSend(message);
  });

  messageInput.addEventListener("input", resizeComposer);
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });

  quickReplies.addEventListener("click", (event) => {
    const button = event.target.closest(".quick-reply");
    if (!button || sendButton.disabled) return;
    quickReplies.hidden = true;
    onSend(button.textContent.trim());
  });

  document.querySelectorAll("[data-view]").forEach((element) => {
    element.addEventListener("click", () => setActiveView(element.dataset.view));
  });
  newChatButton.addEventListener("click", onNewChat);
  exportButton.addEventListener("click", onExport);
  shareButton.addEventListener("click", onShare);
}

export function updateTripHeader(trip = {}) {
  const title = document.querySelector("#trip-title");
  const subtitle = document.querySelector("#trip-subtitle");
  const currentTrip = document.querySelector("#current-trip");
  const sideTitle = document.querySelector("#sidebar-trip-title");
  const sideMeta = document.querySelector("#sidebar-trip-meta");

  if (!trip.destination) {
    title.textContent = "Where would you like to go?";
    subtitle.textContent = "Tell Goo where you're going, and let's plan the details together.";
    currentTrip.hidden = true;
    return;
  }

  const destinationName = trip.destination.split(",")[0].trim();
  title.textContent = trip.travelMonth ? `${destinationName}, ${trip.travelMonth}` : trip.destination;
  const details = [];
  if (trip.origin) details.push(`From ${trip.origin}`);
  if (trip.travelers) details.push(`${trip.travelers} ${trip.travelers === 1 ? "traveler" : "travelers"}`);
  if (trip.travelStyle) details.push(formatStyle(trip.travelStyle));
  if (trip.durationDays) details.push(`${trip.durationDays} days`);
  subtitle.textContent = details.join(" · ") || "Your travel research workspace";
  sideTitle.textContent = trip.destination;
  sideMeta.textContent = [trip.durationDays ? `${trip.durationDays} days` : null, trip.travelMonth].filter(Boolean).join(" · ") || "Requirements in progress";
  currentTrip.hidden = false;
}

function formatStyle(style) {
  return String(style).replace(/_/g, "-").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value, maximumFractionDigits = 0) {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

function setText(selector, value, fallback = "—") {
  const element = document.querySelector(selector);
  element.textContent = value == null || value === "" ? fallback : value;
}

export function renderDashboard(data = {}) {
  const hasData = Boolean(data.trip?.destination || data.cost?.totalLocal != null || data.weather?.high != null || data.days?.length);
  document.querySelector("#dashboard-empty").hidden = hasData;
  document.querySelector("#dashboard-content").hidden = !hasData;
  updateTripHeader(data.trip || {});

  const cost = data.cost || {};
  setText("#budget-total", cost.totalLocal != null ? `${formatNumber(cost.totalLocal)} ${cost.currency || ""}`.trim() : (cost.totalUsd != null ? `US$${formatNumber(cost.totalUsd, 2)}` : "Awaiting estimate"));
  setText("#budget-equation", cost.equation || (cost.dailyUsd != null && data.trip?.travelers && data.trip?.durationDays ? `US$${formatNumber(cost.dailyUsd, 2)} × ${data.trip.travelers} travelers × ${data.trip.durationDays} days` : "Based on available cost research"), "");
  setText("#exchange-rate", cost.exchangeRate ? `1 USD = ${formatNumber(cost.exchangeRate, 2)} ${cost.currency || "BDT"}` : "");
  const budgetScope = data.trip?.budgetScope
    ? `${formatStyle(data.trip.budgetScope)}: `
    : "Budget ";

  const budgetCurrency =
    cost.budgetCurrency ||
    data.trip?.budgetCurrency ||
    cost.currency ||
    "";

  setText(
    "#budget-limit",
    cost.budget != null
      ? `${budgetScope}${formatNumber(cost.budget)} ${budgetCurrency}`.trim()
      : (
          data.trip?.budget != null
            ? `${budgetScope}${formatNumber(data.trip.budget)} ${data.trip.budgetCurrency || ""}`.trim()
            : "Budget not provided"
        )
  );
  const difference = cost.difference;
  const differenceElement = document.querySelector("#budget-difference");
  differenceElement.classList.toggle("is-over", Number.isFinite(difference) && difference > 0);
  differenceElement.textContent = Number.isFinite(difference)
    ? `${difference > 0 ? "+" : ""}${formatNumber(Math.abs(difference))} ${cost.differenceCurrency || cost.currency || ""} ${difference > 0 ? "over" : "under"}`.trim()
    : "";
  const track = document.querySelector("#budget-track");
  const trackFill = track.querySelector("span");
  const budget = cost.budget ?? data.trip?.budget;
  const total = cost.totalLocal;
  if (Number.isFinite(budget) && budget > 0 && Number.isFinite(total)) {
    const isOver = total > budget;
    const fillRatio = isOver ? 1 : total / budget;
    const budgetBoundary = isOver ? (budget / total) * 100 : fillRatio * 100;
    trackFill.style.width = `${fillRatio * 100}%`;
    track.style.setProperty("--budget-ratio", `${budgetBoundary}%`);
    track.classList.toggle("is-over", isOver);
    track.hidden = false;
  } else {
    trackFill.style.width = "0%";
    track.classList.remove("is-over");
    track.hidden = true;
  }
  setText("#budget-note", cost.note || "", "");

  const weather = data.weather || {};
  setText("#weather-high", weather.high != null ? `${formatNumber(weather.high, 1)}°C` : "—");
  setText("#weather-low", weather.low != null ? `${formatNumber(weather.low, 1)}°C` : "—");
  setText("#weather-period", weather.period || data.trip?.travelMonth || "");
  const weatherDetails = [];
  if (weather.precipitation != null) weatherDetails.push(`${formatNumber(weather.precipitation, 1)} mm rain`);
  if (weather.rainyDays != null) weatherDetails.push(`${formatNumber(weather.rainyDays, 1)} rainy days`);
  setText("#weather-details", weather.details || weatherDetails.join(" · "), "Weather information not available yet.");
  setText("#weather-note", weather.note || "", "");

  renderItinerary(data.days || [], Boolean(data.stale));
  renderSourceSummary(data.sources || []);
}

function renderItinerary(days, stale) {
  const list = document.querySelector("#itinerary-list");
  const staleNote = document.querySelector("#stale-plan-note");
  const expandedDays = new Set(
    [...list.querySelectorAll("details.itinerary-day[open]")]
      .map((item) => Number(item.dataset.dayNumber)),
  );
  list.replaceChildren();
  staleNote.hidden = !stale;
  if (!days.length || stale) {
    const placeholder = document.createElement("p");
    placeholder.className = "itinerary-placeholder";
    placeholder.textContent = stale ? "The previous itinerary is hidden until Goo regenerates it for your updated requirements." : "Your researched daily plan will appear here.";
    list.append(placeholder);
    return;
  }

  for (const day of days) {
    const details = document.createElement("details");
    details.className = "itinerary-day";
    details.dataset.dayNumber = String(day.number);
    details.open = expandedDays.has(Number(day.number));
    const summary = document.createElement("summary");

    const number = document.createElement("span");
    number.className = "day-number";
    number.textContent = String(day.number);
    summary.append(number);

    const heading = document.createElement("span");
    heading.className = "day-heading";
    const dayLabel = document.createElement("small");
    dayLabel.textContent = `Day ${day.number}`;
    const dayTitle = document.createElement("strong");
    dayTitle.textContent = day.title || "Flexible day";
    heading.append(dayLabel, dayTitle);
    summary.append(heading);

    const expanded = document.createElement("div");
    expanded.className = "day-expanded";
    for (const period of ["morning", "afternoon", "evening"]) {
      const value = day[period] || "Free time";
      const labelText = day[`${period}Label`] || period;
      const slot = document.createElement("div");
      const label = document.createElement("span");
      label.className = "day-activity-label";
      label.textContent = labelText;
      const text = document.createElement("p");
      text.textContent = value;
      slot.append(label, text);
      expanded.append(slot);

      const preview = document.createElement("span");
      preview.className = "day-activity";
      preview.dataset.period = period;
      const previewLabel = document.createElement("span");
      previewLabel.className = "day-activity-label";
      previewLabel.textContent = labelText;
      const previewText = document.createElement("p");
      previewText.textContent = value;
      preview.append(previewLabel, previewText);
      summary.append(preview);
    }

    if (day.note) {
      const note = document.createElement("p");
      note.className = "day-note";
      note.textContent = day.note;
      expanded.append(note);
    }
    details.append(summary, expanded);
    list.append(details);
  }
}

function renderSourceSummary(sources) {
  const container = document.querySelector("#source-summary");
  const items = document.querySelector("#source-summary-items");
  if (!sources.length) {
    container.hidden = true;
    return;
  }
  items.textContent = sources.slice(0, 4).map((source) => source.name).join(" · ");
  container.hidden = false;
}

export function renderSources(sources = [], notes = "") {
  const grid = document.querySelector("#sources-grid");
  const note = document.querySelector("#sources-note");
  grid.replaceChildren();
  if (!sources.length) {
    const empty = document.createElement("div");
    empty.className = "sources-empty";
    const heading = document.createElement("h2");
    heading.textContent = "No research sources yet";
    const description = document.createElement("p");
    description.textContent = "Ask Goo to research a destination. Sources used in its response will appear here.";
    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "button";
    button.dataset.view = "chat";
    button.textContent = "Start planning";
    button.addEventListener("click", () => setActiveView("chat"));
    empty.append(heading, description, button);
    grid.append(empty);
  } else {
    for (const source of sources) {
      const card = document.createElement("article");
      card.className = "source-card";
      const type = document.createElement("span");
      type.className = "source-type";
      type.textContent = source.type || "RESEARCH";
      const heading = document.createElement("h2");
      heading.textContent = source.name;
      const description = document.createElement("p");
      description.textContent = source.description || "Source referenced in Goo's travel research.";
      const actions = document.createElement("div");
      actions.className = "source-card-actions";
      if (source.url) {
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Open source ↗";
        actions.append(link);
      }
      if (source.licenseUrl) {
        const license = document.createElement("a");
        license.href = source.licenseUrl;
        license.target = "_blank";
        license.rel = "noopener noreferrer";
        license.textContent = source.licenseLabel || "License";
        actions.append(license);
      }
      card.append(type, heading, description, actions);
      grid.append(card);
    }
  }
  note.textContent = notes;
  note.hidden = !notes;
}

export function resetDashboard() {
  renderDashboard({});
  renderSources([], "");
  exportButton.disabled = true;
  shareButton.disabled = true;
}

export function enablePlanActions(enabled) {
  exportButton.disabled = !enabled;
  shareButton.disabled = !enabled;
}

export function flashButton(button, label) {
  const original = button.textContent;
  button.textContent = label;
  window.setTimeout(() => { button.textContent = original; }, 1600);
}

function scrollToLatest() {
  messageList.scrollTop = messageList.scrollHeight;
}
