import { deleteChat, sendMessageStream } from "./api.js";
import { getSessionId, resetSessionId } from "./session.js";
import {
  addBubble,
  enablePlanActions,
  flashButton,
  focusMessageInput,
  initializeUI,
  renderDashboard,
  renderSources,
  resetChatView,
  setSending,
  showTypingIndicator,
  updateBubble,
  updateBubbleStatus,
  updateDashboardStatus,
} from "./ui.js";

let isSending = false;
let sessionId = getSessionId();
let tripState = {
  trip: {},
  cost: {},
  weather: {},
  days: [],
  sources: [],
  stale: false,
};
let latestPlanMarkdown = "";

function cleanMarkdown(value = "") {
  return String(value)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, "$1")
    .replace(/\*\*|__|`|~~/g, "")
    .replace(/(^|\s)[*_]([^*_]+)[*_](?=\s|$)/g, "$1$2")
    .replace(/^\s*[-*]\s*/, "")
    .replace(/\\([_*()[\]`])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function extractField(text, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const expression = new RegExp(`(?:^|\\n)\\s*(?:[-*]\\s*)?\\*{0,2}${escaped}\\*{0,2}\\s*:\\s*(.+)$`, "im");
  const match = text.match(expression);
  return match ? cleanMarkdown(match[1]) : null;
}

function parseMoney(text) {
  if (!text) return null;
  const match = text.match(/([\d,]+(?:\.\d+)?)\s*([A-Z]{3})\b/i);
  if (!match) return null;
  return { amount: Number(match[1].replace(/,/g, "")), currency: match[2].toUpperCase() };
}

function findSection(text, pattern) {
  const lines = text.split(/\r?\n/);

  const start = lines.findIndex(
    (line) =>
      /^#{1,6}\s/.test(line) &&
      pattern.test(cleanMarkdown(line))
  );

  if (start < 0) return "";

  // Get the heading level of the requested section.
  const startHeading = lines[start].match(/^#+/);
  const startLevel = startHeading
    ? startHeading[0].length
    : 1;

  // Stop only at the next heading of the same or higher level.
  let end = lines.findIndex((line, index) => {
    if (index <= start) return false;

    const heading = line.match(/^(#{1,6})\s/);

    return heading && heading[1].length <= startLevel;
  });

  if (end < 0) end = lines.length;

  return lines.slice(start + 1, end).join("\n");
}

function parseWeather(text, currentTrip) {
  const section = findSection(text, /weather|climate|seasonal/i);
  if (!section) return {};
  const plain = cleanMarkdown(section);
  const high = plain.match(
    /(?:average\s+(?:daily\s+)?(?:high|maximum)|avg\s+high|daily\s+(?:high|maximum)|\bhigh)\s*(?:of|:)?[^\d+-]{0,25}([-+]?\d+(?:\.\d+)?)\s*°?\s*C?/i
  );
  const low = plain.match(
    /(?:average\s+(?:daily\s+)?(?:low|minimum)|avg\s+low|daily\s+(?:low|minimum)|\blow)\s*(?:of|:)?[^\d+-]{0,25}([-+]?\d+(?:\.\d+)?)\s*°?\s*C?/i
  );
  const rain = plain.match(/([\d,.]+)\s*mm\b/i);
  const rainy = plain.match(/([\d,.]+)\s*rainy\s+days?/i);
  const periodMatch = plain.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?/i);
  const noteMatch = plain.match(/(?:not a forecast|historical patterns?|historical observations?)[^.]*\.?/i);
  const details = [];
  if (rain) details.push(`${rain[1]} mm precipitation`);
  if (rainy) details.push(`${rainy[1]} rainy days`);
  return {
    ...(high ? { high: Number(high[1]) } : {}),
    ...(low ? { low: Number(low[1]) } : {}),
    ...(rain ? { precipitation: Number(rain[1].replace(/,/g, "")) } : {}),
    ...(rainy ? { rainyDays: Number(rainy[1].replace(/,/g, "")) } : {}),
    period: periodMatch ? periodMatch[0] : (currentTrip.travelMonth || "Seasonal climate"),
    details: details.join(" · "),
    note: noteMatch ? cleanMarkdown(noteMatch[0]) : "Historical seasonal information; not a forecast.",
  };
}

function parseCost(text, trip) {
  const section = findSection(text, /budget|travel\s+cost|estimated\s+cost/i);
  if (!section) return {};
  const plain = cleanMarkdown(section);
  const dailyMatch = plain.match(/(?:published\s+starting\s+cost|daily\s+cost\s+per\s+person|per\s+person\s+per\s+day)[^\n]{0,90}?(?:US\$|USD\s*)\s*([\d,]+(?:\.\d+)?)/i)
    || plain.match(/(?:US\$|USD\s*)\s*([\d,]+(?:\.\d+)?)\s+per\s+person\s+per\s+day/i);
  const totalUsdMatch = plain.match(/For\s+[\d,]+\s+travelers?\s*[×x]\s*[\d,]+\s+days?\s*:\s*(?:US\$|USD\s*)\s*([\d,]+(?:\.\d+)?)/i)
    || plain.match(/(?:estimated\s+(?:land[- ]trip\s+)?total|land[- ]trip\s+total)[^\n]{0,90}?(?:US\$|USD\s*)\s*([\d,]+(?:\.\d+)?)/i);
  const convertedMatch = plain.match(/converted(?:\s+by\s+the\s+estimator)?\s+to\s+([\d,]+(?:\.\d+)?)\s*([A-Z]{3})/i)
    || plain.match(/(?:converted\s+comparison|converted\s+total|total\s+in)[^\n]{0,80}?([\d,]+(?:\.\d+)?)\s*([A-Z]{3})/i);
  const overviewBudgetMatch = text.match(/(?:^|\n)\s*[-*]\s*\*{0,2}([A-Za-z][\w -]*?)\s+budget\*{0,2}\s*:\s*\*{0,2}\s*([\d,]+(?:\.\d+)?)\s*([A-Z]{3})([^\n]*)/im);
  const comparisonBudgetMatch = plain.match(/budget\s+comparison\s*:[^\n]*?([\d,]+(?:\.\d+)?)\s*([A-Z]{3})\s+budget/i);
  const dailyUsd = dailyMatch ? Number(dailyMatch[1].replace(/,/g, "")) : null;
  const totalUsd = totalUsdMatch ? Number(totalUsdMatch[1].replace(/,/g, "")) : null;
  const totalLocal = convertedMatch ? Number(convertedMatch[1].replace(/,/g, "")) : null;
  const localCurrency = convertedMatch?.[2]?.toUpperCase() || null;
  const overviewBudget = overviewBudgetMatch
    ? { amount: Number(overviewBudgetMatch[2].replace(/,/g, "")), currency: overviewBudgetMatch[3].toUpperCase() }
    : null;
  const comparisonBudget = comparisonBudgetMatch
    ? { amount: Number(comparisonBudgetMatch[1].replace(/,/g, "")), currency: comparisonBudgetMatch[2].toUpperCase() }
    : null;
  const budget = overviewBudget || comparisonBudget || (trip.budget != null && trip.budgetCurrency
    ? { amount: trip.budget, currency: trip.budgetCurrency }
    : null);
  const rateMatch = plain.match(/reference\s+rate\s+of\s+([\d,.]+)\s*([A-Z]{3})\s+per\s+USD/i)
    || plain.match(/1\s*USD\s*=\s*([\d,.]+)\s*([A-Z]{3})/i);
  const excludedMatch = plain.match(/\*?Excluded\*?\s*:\s*([^\n.]+(?:\.)?)/i);
  const startingNoteMatch = plain.match(/The\s+source\s+gives\s+a\s+starting\s+price[^.]*\./i);
  let difference = totalLocal != null && budget ? totalLocal - budget.amount : null;
  const notes = [];
  if (trip.budgetScope) notes.push(`${trip.budgetScope} budget`);
  if (startingNoteMatch) notes.push(startingNoteMatch[0]);
  if (excludedMatch) notes.push(`Excluded: ${excludedMatch[1]}`);

  return {
    ...(dailyUsd != null ? { dailyUsd } : {}),
    ...(totalUsd != null ? { totalUsd } : {}),
    ...(totalLocal != null ? { totalLocal, currency: localCurrency } : {}),
    ...(budget ? { budget: budget.amount, currency: budget.currency } : {}),
    ...(difference != null ? { difference } : {}),
    ...(rateMatch ? { exchangeRate: Number(rateMatch[1].replace(/,/g, "")), currency: rateMatch[2].toUpperCase() } : {}),
    ...(dailyUsd != null && trip.travelers && trip.durationDays ? { equation: `US$${dailyUsd.toLocaleString()} × ${trip.travelers} travelers × ${trip.durationDays} days` } : {}),
    ...(notes.length ? { note: notes.join(" · ").slice(0, 320) } : {}),
  };
}

function parseItinerary(text) {
  const section = findSection(text, /day[- ]by[- ]day\s+itinerary|itinerary/i);
  const source = section || text;

  // Normalize bold standalone day headings into formats handled below.
  // Examples:
  //   **Day 1 — Trafalgar Square and The Mall**
  //   **Days 2–5 — Further research needed**
  const normalizedSource = source
    .replace(
      /^[ \t]*\*\*Day[ \t]+(\d+)[ \t]*[—–:-][ \t]*(.+?)[ \t]*\*\*[ \t]*$/gim,
      "### Day $1 — $2",
    )
    .replace(
      /^[ \t]*\*\*Days[ \t]+(\d+)[ \t]*[–—-][ \t]*(\d+)[ \t]*[—–:-][ \t]*(.+?)[ \t]*\*\*[ \t]*$/gim,
      "- **Days $1–$2:** $3",
    );

  const days = new Map();

  // Support the structured heading format used by earlier Goo responses.
  const headings = [...normalizedSource.matchAll(/^#{2,4}\s*Day\s*(\d+)\s*[—–:-]\s*(.+)$/gim)];
  headings.forEach((heading, index) => {
    const start = heading.index + heading[0].length;
    const nextDayIndex = headings[index + 1]?.index ?? normalizedSource.length;
    const remaining = normalizedSource.slice(start, nextDayIndex);
    const nextSectionMatch = remaining.match(/\n#{1,2}\s+/);
    const end = nextSectionMatch ? start + nextSectionMatch.index : nextDayIndex;
    const content = normalizedSource.slice(start, end).trim();
    const slots = {};
    const marker = /(?:^|\n)\s*(?:[-*]\s*)?\*{0,2}(Morning\s+or\s+afternoon|Other half of (?:the )?day|Late morning|Morning|Afternoon|Evening|Optional)(?:\s*\([^)]*\))?\*{0,2}\s*:\s*\*{0,2}\s*/gi;
    const matches = [...content.matchAll(marker)];
    for (let slotIndex = 0; slotIndex < matches.length; slotIndex += 1) {
      const match = matches[slotIndex];
      const valueStart = match.index + match[0].length;
      const whyIndex = content.search(/\n\s*\*?Why\b/i);
      const valueEnd = matches[slotIndex + 1]?.index ?? (whyIndex >= 0 ? whyIndex : content.length);
      const rawLabel = match[1].toLowerCase().replace(/\s+/g, " ");
      const label = rawLabel === "morning or afternoon" ? "daytime"
        : rawLabel.startsWith("other half") ? "other" : rawLabel;

      const rawValue = content
        .slice(valueStart, valueEnd)
        .replace(/^\s*[-*]\s*/gm, "")
        .replace(/\n+/g, " ");

      const value = cleanMarkdown(
        rawValue.replace(
          /\s+\*?Why(?: these fit| this fits| these places fit| this works)?[^:]*:[\s\S]*$/i,
          ""
        )
      );

      // Preserve multiple activities belonging to the same period.
      slots[label] = slots[label]
        ? `${slots[label]} · ${value}`
        : value;
    }
    const why = content.match(/(?:\*\*)?Why[^:*]*:?(?:\*\*)?\s*([\s\S]*)/i);
    const morningParts = [
      slots.daytime || slots.morning,
      slots["late morning"],
    ].filter(Boolean);

    const afternoonParts = [
      slots.other || slots.afternoon,
      slots.optional ? `Optional: ${slots.optional}` : null,
    ].filter(Boolean);
    days.set(Number(heading[1]), {
      number: Number(heading[1]),
      title: cleanMarkdown(heading[2]),

      morning: morningParts.join(" · ") || "Flexible time",
      morningLabel: slots.daytime ? "Daytime" : "Morning",

      afternoon: afternoonParts.join(" · ") || "Flexible time",
      afternoonLabel: slots.other ? "Other half" : "Afternoon",

      evening: slots.evening || "Free time",

      ...(why ? { note: cleanMarkdown(why[1]) } : {}),
    });
  });

  // Also support the current response format: "- **Day 1:** ..." and day ranges.
  const bulletPattern = /^\s*[-*]\s+\*{0,2}Days?\s+(\d+)(?:\s*[–—-]\s*(\d+))?(?:\s*:\*{0,2}|\*{0,2}\s*:)\s*(.+?)\s*$/gim;
  for (const match of normalizedSource.matchAll(bulletPattern)) {
    const firstDay = Number(match[1]);
    const lastDay = Number(match[2] || match[1]);
    const description = cleanMarkdown(match[3]);
    const flexible = /keep\s+flexible|flexible\s+until|free\s+time/i.test(description);
    let title = flexible
      ? "Flexible day"
      : description
        .replace(/^explore\s+the\s+nearby\s+religious\s+sites\s+/i, "")
        .replace(/^(?:visit|explore|discover|walk(?:\s+through)?|spend\s+time\s+at)\s+/i, "")
        .replace(/\s+and,\s+if[\s\S]*$/i, "")
        .replace(/\s+and\s+other[\s\S]*$/i, "")
        .replace(/[.;]$/, "")
        .trim()
        .slice(0, 58) || "Sightseeing";

    for (let dayNumber = firstDay; dayNumber <= Math.min(lastDay, firstDay + 6); dayNumber += 1) {
      if (days.has(dayNumber)) continue;
      days.set(dayNumber, {
        number: dayNumber,
        title,
        morning: description,
        morningLabel: "Plan",
        afternoon: flexible ? "Keep this day open" : "Flexible time",
        afternoonLabel: "Other time",
        evening: "Free time",
        ...(flexible ? { note: "Additional attraction research is needed before filling this day." } : {}),
      });
    }
  }

  return [...days.values()].sort((a, b) => a.number - b.number);
}

function inferSourceType(name, url) {
  const value = `${name} ${url}`.toLowerCase();
  if (/tieredtravel|cost|budget/.test(value)) return "BUDGET";
  if (/open-meteo|weather|climate/.test(value)) return "WEATHER";
  if (/geoapify|place|attraction/.test(value)) return "PLACES";
  if (/openstreetmap|osm/.test(value)) return "MAP DATA";
  return "RESEARCH";
}

function parseSources(text) {
  const sources = [];
  const seen = new Set();
  const add = (name, url, description = "Referenced in Goo's travel research.", licenseUrl = null) => {
    if (!url) return;
    const normalizedUrl = url.replace(/[.,;*]+$/, "");
    if (!/^https?:\/\//i.test(normalizedUrl) || seen.has(normalizedUrl)) return;
    seen.add(normalizedUrl);
    const cleanName = cleanMarkdown(name || normalizedUrl);
    sources.push({
      name: cleanName,
      type: inferSourceType(cleanName, normalizedUrl),
      description: cleanMarkdown(description) || "Referenced in Goo's travel research.",
      url: normalizedUrl,
      ...(licenseUrl ? { licenseUrl } : {}),
    });
  };

  // Prefer the authored label for Markdown links.
  const markdownLinks = [...text.matchAll(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g)];
  for (const match of markdownLinks) {
    const lineStart = text.lastIndexOf("\n", match.index) + 1;
    const lineEnd = text.indexOf("\n", match.index);
    const line = text.slice(lineStart, lineEnd < 0 ? text.length : lineEnd);
    add(match[1], match[2], line);
  }

  // Capture provider and attribution URLs even when they are plain text.
  const rawUrls = [...text.matchAll(/https?:\/\/[^\s)]+/g)];
  for (const match of rawUrls) {
    const url = match[0].replace(/[.,;*]+$/, "");
    if (seen.has(url)) continue;
    const lineStart = text.lastIndexOf("\n", match.index) + 1;
    const lineEnd = text.indexOf("\n", match.index);
    const line = text.slice(lineStart, lineEnd < 0 ? text.length : lineEnd);
    const context = text.slice(Math.max(0, match.index - 100), match.index);
    const attributed = context.match(/(?:Weather data by|Powered by|©)\s*([^:\n]+):?\s*$/i);
    const host = (() => {
      try { return new URL(url).hostname.replace(/^www\./, ""); }
      catch { return url; }
    })();
    const fallbackName = /open-meteo/i.test(host) ? "Open-Meteo"
      : /geoapify/i.test(host) ? "Geoapify"
      : /openstreetmap/i.test(host) ? "OpenStreetMap contributors"
      : host;
    add(attributed?.[1]?.trim() || fallbackName, url, line, /openstreetmap/i.test(host) ? url : null);
  }

  return sources;
}

function parsePlanReply(reply, existing) {
  const trip = { ...existing.trip };
  const origin = extractField(reply, "Origin");
  const destination = extractField(reply, "Destination");
  const travelers = extractField(reply, "Travelers");
  const duration = extractField(reply, "Duration");
  const style = extractField(reply, "Travel style") || extractField(reply, "Style");
  const budget = extractField(reply, "Budget");
  const month = extractField(reply, "Travel month") || extractField(reply, "Travel dates") || extractField(reply, "Travel period") || extractField(reply, "When");
  const route = reply.match(/(?:^|\n)\s*[-*]\s*\*{0,2}Route\*{0,2}\s*:\s*(.+?)\s*(?:→|->)\s*(.+?)\s*$/im);
  const overviewBudget = reply.match(/(?:^|\n)\s*[-*]\s*\*{0,2}([A-Za-z][\w -]*?)\s+budget\*{0,2}\s*:\s*\*{0,2}\s*([\d,]+(?:\.\d+)?)\s*([A-Z]{3})([^\n]*)/im);

  if (route) {
    trip.origin = cleanMarkdown(route[1]);
    trip.destination = cleanMarkdown(route[2]);
  }
  if (origin) trip.origin = origin;
  if (destination) trip.destination = destination;
  if (travelers) {
    const count = travelers.match(/\d+/);
    if (count) trip.travelers = Number(count[0]);
  }
  if (duration) {
    const count = duration.match(/\d+/);
    if (count) trip.durationDays = Number(count[0]);
  }
  if (style) trip.travelStyle = style.toLowerCase().replace(/[ -]/g, "_");
  if (budget) {
    const money = parseMoney(budget);
    if (money) { trip.budget = money.amount; trip.budgetCurrency = money.currency; }
  }
  if (overviewBudget) {
    trip.budget = Number(overviewBudget[2].replace(/,/g, ""));
    trip.budgetCurrency = overviewBudget[3].toUpperCase();
    trip.budgetScope = overviewBudget[1].replace(/[-_]+/g, " ").trim();
    trip.budgetExclusions = cleanMarkdown(overviewBudget[4]).replace(/^[;,\s]+/, "");
  }
  if (month) trip.travelMonth = month;

  const titleMatch = reply.match(/^#\s+(.+?)\s*:\s*(?:Complete\s+)?\d+[- ]day itinerary/im);
  if (!trip.destination && titleMatch) trip.destination = cleanMarkdown(titleMatch[1]);
  if (!trip.durationDays) {
    const headingDuration = reply.match(/^#.*?\b(\d+)[- ]day itinerary/im);
    if (headingDuration) trip.durationDays = Number(headingDuration[1]);
  }
  if (!trip.travelMonth) {
    const monthMatch = reply.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b/i);
    if (monthMatch) trip.travelMonth = monthMatch[0];
  }

  const days = parseItinerary(reply);
  const parsedSources = parseSources(reply);
  const isFullPlan = days.length > 0;
  const next = {
    ...existing,
    trip,
    cost: { ...existing.cost, ...parseCost(reply, trip) },
    weather: { ...existing.weather, ...parseWeather(reply, trip) },
    days: isFullPlan ? days : existing.days,
    sources: parsedSources.length ? parsedSources : existing.sources,
    stale: isFullPlan ? false : existing.stale,
  };
  return { next, isFullPlan };
}

function applyRequirementAcknowledgement(reply) {
  const duration = reply.match(/(?:trip\s+)?duration\s*(?:is|to|of)?\s*\*{0,2}(\d+)\s*days?/i);
  const destination = reply.match(/\b(?:destination|trip to)\s*(?:is|:)?\s*\*{0,2}([A-Z][\w .'-]+?)(?:\*{0,2},|\s+in\s+|\.|$)/i);
  const previousDuration = tripState.trip.durationDays;
  let changed = false;
  if (duration) {
    const nextDuration = Number(duration[1]);
    if (nextDuration && nextDuration !== previousDuration) {
      tripState.trip.durationDays = nextDuration;
      changed = true;
    }
  }
  if (destination && !tripState.trip.destination) tripState.trip.destination = destination[1].trim();
  if (changed && tripState.days.length) {
    tripState.stale = true;
    tripState.cost = {
      ...tripState.cost,
      totalLocal: null,
      totalUsd: null,
      difference: null,
      note: "The trip duration changed. Regenerate the itinerary to recalculate the total estimate.",
    };
  }
  if (changed || destination) renderDashboard(tripState);
}

let lastStreamingRender = 0;

function renderStreamingProgress(reply, force = false) {
  if (!reply.trim()) return;
  const now = Date.now();
  if (!force && now - lastStreamingRender < 100) return;
  lastStreamingRender = now;

  const { next } = parsePlanReply(reply, tripState);
  tripState = next;
  renderDashboard(tripState);
  if (tripState.sources.length) {
    const note = tripState.cost?.note || "Research sources are provided with the relevant estimates and place information in Goo's response.";
    renderSources(tripState.sources, note);
  }
}

function getToolStatus(name, completed = false) {
  const labels = {
    update_trip_requirements: "Saving your trip requirements",
    search_nearby_places: "Researching attractions and places",
    get_seasonal_climate: "Checking seasonal climate",
    get_weather: "Checking the weather forecast",
    convert_currency: "Checking currency conversion",
    search_destination: "Looking up destination details",
    estimate_travel_cost: "Researching travel costs",
  };
  const label = labels[name] || "Researching your trip";
  return completed ? `${label} · complete` : `${label}...`;
}

function updatePlanFromReply(reply) {
  const { next, isFullPlan } = parsePlanReply(reply, tripState);
  tripState = next;
  if (isFullPlan) {
    latestPlanMarkdown = reply;
    enablePlanActions(true);
  } else {
    applyRequirementAcknowledgement(reply);
  }
  renderDashboard(tripState);
  if (tripState.sources.length) {
    const note = tripState.cost?.note || "Research sources are provided with the relevant estimates and place information in the assistant's response.";
    renderSources(tripState.sources, note);
  }
}

function isTripResearchResponse(text) {
  return /(?:^|\n)#{1,4}\s*(?:[A-F]\.\s*)?(?:Trip Overview|Destination Overview|Weather(?: and Seasonal Considerations)?|Day[- ]by[- ]Day Itinerary|Estimated Travel Budget|Sources and Important Notes)\b/im.test(text)
    || /^#\s+.+?\b\d+[- ]day itinerary/im.test(text);
}

async function handleSend(message) {
  if (!message || isSending) return;
  isSending = true;
  setSending(true);
  addBubble("user", message);
  const replyBubble = addBubble("bot");
  showTypingIndicator(replyBubble);
  updateDashboardStatus("Preparing your trip research...");

  let streamedText = "";
  let streamError = null;
  let streamDone = false;
  let isTripReport = false;
  let lastBubbleUpdate = 0;

  try {
    await sendMessageStream(sessionId, message, (event) => {
      if (streamError) return;

      if (event.type === "status") {
        const status = event.message || "Goo is thinking";
        updateBubbleStatus(replyBubble, status);
        updateDashboardStatus(status);
        return;
      }

      if (event.type === "tool_start") {
        const status = getToolStatus(event.name);
        updateBubbleStatus(replyBubble, status);
        updateDashboardStatus(status);
        return;
      }

      if (event.type === "tool_complete") {
        const status = getToolStatus(event.name, true);
        updateBubbleStatus(replyBubble, status);
        updateDashboardStatus(status);
        return;
      }

      if (event.type === "text_delta") {
        if (typeof event.delta !== "string" || !event.delta) return;
        streamedText += event.delta;
        isTripReport = isTripReport || isTripResearchResponse(streamedText);
        const now = Date.now();
        if (isTripReport) {
          // Keep the conversation bubble as a concise progress indicator.
          updateBubbleStatus(replyBubble, "Building your trip workspace");
        } else if (!streamedText.trimStart().startsWith("#") && now - lastBubbleUpdate >= 45) {
          // Clarifications and ordinary conversational replies stay in chat bubbles.
          lastBubbleUpdate = now;
          updateBubble(replyBubble, "bot", streamedText);
        }
        renderStreamingProgress(streamedText);
        updateDashboardStatus(isTripReport ? "Streaming trip workspace sections..." : "Streaming Goo's response...");
        return;
      }

      if (event.type === "done") {
        streamDone = true;
        return;
      }

      if (event.type === "error") {
        streamError = new Error(event.message || "Something went wrong. Please try again.");
      }
    });

    if (streamError) throw streamError;
    if (!streamDone) {
      throw new Error("The connection closed before Goo finished responding. Please try again.");
    }
    if (!streamedText.trim()) {
      throw new Error("Goo did not return a response. Please try again.");
    }

    updateBubble(
      replyBubble,
      "bot",
      isTripReport
        ? "Your trip research is ready in the workspace. You can review the budget, seasonal weather, itinerary, and sources on the right."
        : streamedText,
    );
    renderStreamingProgress(streamedText, true);
    updatePlanFromReply(streamedText);
    const hasResearchData = Boolean(
      tripState.days.length ||
      tripState.cost?.totalLocal != null ||
      tripState.weather?.high != null
    );
    updateDashboardStatus(hasResearchData ? "Research complete" : "Response complete");
    window.setTimeout(() => updateDashboardStatus("", false), 2400);
  } catch (error) {
    const messageText = error instanceof Error
      ? error.message
      : "Something went wrong. Please try again.";

    if (streamedText.trim()) {
      updateBubble(
        replyBubble,
        isTripReport ? "error" : "bot",
        isTripReport
          ? "The trip research stream was interrupted. Some workspace sections may be incomplete."
          : `${streamedText}\n\n*The connection was interrupted. This response may be incomplete.*`,
      );
      renderStreamingProgress(streamedText, true);
    } else {
      updateBubble(replyBubble, "error", messageText);
    }
    updateDashboardStatus("Streaming interrupted", true);
  } finally {
    isSending = false;
    setSending(false);
    focusMessageInput();
  }
}

async function handleNewChat() {
  await deleteChat(sessionId);
  sessionId = resetSessionId();
  tripState = { trip: {}, cost: {}, weather: {}, days: [], sources: [], stale: false };
  latestPlanMarkdown = "";
  lastStreamingRender = 0;
  updateDashboardStatus("", false);
  enablePlanActions(false);
  resetChatView();
}

function handleExport() {
  if (!latestPlanMarkdown) return;
  const blob = new Blob([latestPlanMarkdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const safeDestination = (tripState.trip.destination || "travel-plan").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  anchor.href = url;
  anchor.download = `${safeDestination || "goo-travel-plan"}-itinerary.md`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  flashButton(document.querySelector("#export-plan"), "Exported");
}

async function handleShare() {
  if (!latestPlanMarkdown) return;
  const shareData = { title: `${tripState.trip.destination || "Goo"} travel itinerary`, text: latestPlanMarkdown };
  try {
    if (navigator.share) {
      await navigator.share(shareData);
      return;
    }
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(latestPlanMarkdown);
      flashButton(document.querySelector("#share-plan"), "Copied");
      return;
    }
    throw new Error("Clipboard sharing is unavailable in this browser.");
  } catch (error) {
    if (error?.name !== "AbortError") {
      flashButton(document.querySelector("#share-plan"), "Unable to share");
    }
  }
}

initializeUI({
  onSend: handleSend,
  onNewChat: handleNewChat,
  onExport: handleExport,
  onShare: handleShare,
});
resetChatView();
enablePlanActions(false);
