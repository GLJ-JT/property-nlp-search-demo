const DATA_URL = "../data/properties_enriched.json";
const API_URL = window.location.protocol.startsWith("http")
  ? `${window.location.origin}/api/search`
  : "http://127.0.0.1:8787/api/search";

const state = {
  query: "studio near ucl under 2500 not basement",
  items: [],
  mode: "loading",
};

const el = (selector) => document.querySelector(selector);

function normalize(text) {
  return text.toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, " ").trim();
}

function parseQuery(query) {
  const raw = normalize(query);
  const rentMaxMatch = raw.match(/(?:under|max|below)\s*£?\s*(\d{3,5})/);
  const rentMinMatch = raw.match(/(?:over|above|from)\s*£?\s*(\d{3,5})/);
  const bedMatch = raw.match(/(\d)\s*bed/);
  const rentMax = rentMaxMatch ? Number(rentMaxMatch[1]) : null;
  const rentMin = rentMinMatch ? Number(rentMinMatch[1]) : null;
  const bed = raw.includes("studio") ? "studio" : bedMatch ? `${bedMatch[1]} bed` : null;
  const location = ["ucl", "canary wharf", "russell square", "notting hill", "lewisham", "walthamstow", "canada water", "aldgate", "angel", "soho", "lse", "imperial", "kcl"].find((item) => raw.includes(item)) || null;
  const exclusions = ["basement", "noisy", "nightlife", "lift", "pets", "parking", "garden", "house share", "walk up"].filter((item) => new RegExp(`\\b(?:no|not)\\s+${item}\\b|\\bnot\\s+${item}\\b`).test(raw));
  const positives = ["balcony", "gym", "garden", "pet friendly", "bills included", "high floor", "step free"].filter((item) => raw.includes(item));
  return {
    raw,
    rent_max: rentMax,
    rent_min: rentMin,
    rooms: bed,
    location,
    keywords: positives,
    exclude_keywords: exclusions,
    hard_filters: [bed && "room type", location && "location", rentMax && "max rent"].filter(Boolean),
    soft_preferences: positives,
  };
}

function scoreProperty(property, intent) {
  const reasons = [];
  let score = 0;
  const text = `${property.name} ${property.location} ${property.description} ${(property.keywords || []).join(" ")}`.toLowerCase();
  const locationBlob = `${property.location} ${(property.nearby_stations || []).map((item) => item.name).join(" ")} ${(property.nearby_landmarks || []).map((item) => item.name).join(" ")}`.toLowerCase();

  if (intent.rooms) {
    if (text.includes(intent.rooms) || (intent.rooms === "studio" && property.room_type === "studio")) {
      score += 18;
      reasons.push(`room type ${intent.rooms}`);
    }
  }

  if (intent.rent_max && property.monthly_rent_gbp <= intent.rent_max) {
    score += 18;
    reasons.push(`rent within budget at ${property.monthly_rent_gbp}`);
  }

  if (intent.rent_min && property.monthly_rent_gbp >= intent.rent_min) {
    score += 8;
    reasons.push(`rent above ${intent.rent_min}`);
  }

  if (intent.location && (locationBlob.includes(intent.location) || text.includes(intent.location))) {
    score += 24;
    reasons.push(`location match ${intent.location}`);
  }

  for (const item of intent.keywords || []) {
    if (text.includes(item)) {
      score += 6;
      reasons.push(item);
    }
  }

  for (const item of intent.exclude_keywords || []) {
    if (text.includes(item)) {
      score -= 20;
      reasons.push(`excluded by ${item}`);
    }
  }

  score += Math.max(0, 8 - Math.abs(intent.raw.length - text.length) / 40);
  return {
    property,
    score: Number(score.toFixed(2)),
    reasons,
    explanation: {
      hard_filter_pass: score >= 20,
      hard_checks: reasons.slice(0, 3).map((reason) => ({ label: reason, points: 8, passed: true })),
      soft_scores: reasons.slice(3).map((reason) => ({ label: reason, points: 4 })),
      excluded_by_query: reasons.some((reason) => reason.startsWith("excluded by")),
    },
  };
}

function staticSearch(items, query) {
  const parsed = parseQuery(query);
  const ranked = items
    .map((item) => scoreProperty(item, parsed))
    .filter((entry) => entry.score >= 20 && !entry.explanation.excluded_by_query)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);

  return {
    parsed_query: parsed,
    query_repair: { original: query, normalized: parsed.raw, repairs: [], changed: false },
    clarifications: [],
    results: ranked,
    total_matches: ranked.length,
    filtered_out: Math.max(0, items.length - ranked.length),
    excluded_out: 0,
    engine: {
      name: "StaticFallbackSearch",
      source: "assets/search-demo.js",
      data: DATA_URL,
      mode: "static-fallback",
    },
  };
}

function formatMoney(value) {
  return `£${Number(value).toLocaleString("en-GB")}`;
}

function renderCard(entry, rank) {
  const property = entry.property;
  const nearby = property.nearby_stations?.[0];
  const reasonText = entry.reasons.slice(0, 3).join(" · ") || "strong overall match";
  return `
    <article class="result-card">
      <div class="rank">${String(rank).padStart(2, "0")}</div>
      <div class="result-main">
        <div class="result-top">
          <strong>${property.name}</strong>
          <span>${formatMoney(property.monthly_rent_gbp)} pcm</span>
        </div>
        <p class="result-description">${property.description}</p>
        <div class="result-meta">
          <span>${property.room_type}</span>
          <span>${property.location}</span>
          <span>${property.size_sqft} sq ft</span>
        </div>
        <div class="result-extra">
          <span>${nearby ? `${nearby.walk_minutes} min to ${nearby.name}` : property.station || ""}</span>
          <span>${property.new_build ? "New build" : "Older build"}</span>
          <span>${property.floor_label || "floor checked"}</span>
        </div>
        <div class="score-row">
          <strong>${entry.score}</strong>
          <span>Python score</span>
        </div>
        <p class="reason-line">${reasonText}</p>
      </div>
    </article>
  `;
}

function renderChips(parsed) {
  const chips = [];
  (parsed.hard_filters || []).forEach((item) => chips.push(`<span class="chip hard">${item}</span>`));
  if (parsed.rooms) chips.push(`<span class="chip hard">${parsed.rooms}</span>`);
  if (parsed.location) chips.push(`<span class="chip hard">${parsed.location}</span>`);
  if (parsed.landmark) chips.push(`<span class="chip hard">${parsed.landmark}</span>`);
  if (parsed.rent_max) chips.push(`<span class="chip hard">Max ${formatMoney(parsed.rent_max)}</span>`);
  (parsed.keywords || []).forEach((item) => chips.push(`<span class="chip soft">${item}</span>`));
  (parsed.soft_preferences || []).forEach((item) => chips.push(`<span class="chip soft">${item}</span>`));
  (parsed.exclude_keywords || []).forEach((item) => chips.push(`<span class="chip exclude">No ${item}</span>`));
  el("#chips").innerHTML = [...new Set(chips)].join("");
}

function renderChecks(payload) {
  const first = payload.results?.[0];
  const checks = first?.explanation?.hard_checks || [];
  const soft = first?.explanation?.soft_scores || [];
  el("#checks").innerHTML = `
    <div class="check-grid">
      ${checks.slice(0, 5).map((item) => `
        <div class="check ${item.passed ? "pass" : "fail"}">
          <strong>${item.passed ? "pass" : "review"}</strong>
          <span>${item.label}</span>
        </div>
      `).join("") || `<div class="check"><strong>waiting</strong><span>Run a query to see hard filters.</span></div>`}
    </div>
    <div class="soft-list">
      ${soft.slice(0, 4).map((item) => `<span>${item.points > 0 ? "+" : ""}${item.points} · ${item.label}</span>`).join("")}
    </div>
  `;
}

function renderPipeline(payload) {
  const repairs = payload.query_repair?.repairs || [];
  const engine = payload.engine || {};
  el("#engine-mode").textContent = engine.mode === "python-backend" ? "Python backend connected" : "Static fallback";
  el("#engine-source").textContent = `${engine.source || "unknown"} · ${engine.data || "unknown data"}`;
  el("#pipeline").innerHTML = `
    <span>query</span>
    <span>${repairs.length ? "repair" : "normalize"}</span>
    <span>parse</span>
    <span>score</span>
    <span>rank</span>
  `;
}

function renderPayload(payload) {
  renderPipeline(payload);
  renderChips(payload.parsed_query);
  renderChecks(payload);
  el("#results").innerHTML = payload.results.map((entry, index) => renderCard(entry, index + 1)).join("") || `<div class="empty">No results passed the current hard filters. Try relaxing the query.</div>`;
  el("#intent-json").textContent = JSON.stringify(payload.parsed_query, null, 2);
  el("#summary").textContent = `${payload.total_matches} matches · ${payload.filtered_out} filtered · ${payload.excluded_out} excluded`;
}

async function backendSearch(query) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top: 6 }),
  });
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  return response.json();
}

async function ensureStaticData() {
  if (state.items.length) return state.items;
  const response = await fetch(DATA_URL);
  state.items = await response.json();
  return state.items;
}

async function runSearch(query) {
  el("#summary").textContent = "Running parser and ranking listings...";
  try {
    const payload = await backendSearch(query);
    state.mode = "python-backend";
    renderPayload(payload);
  } catch (error) {
    try {
      const items = await ensureStaticData();
      state.mode = "static-fallback";
      renderPayload(staticSearch(items, query));
    } catch (fallbackError) {
      state.mode = "offline";
      el("#engine-mode").textContent = "Start the Python server";
      el("#engine-source").textContent = "Run: python3 engine/server.py";
      el("#summary").textContent = "The page is open as a file and cannot fetch backend or JSON data yet.";
      el("#results").innerHTML = `<div class="empty">Start the backend at <code>http://127.0.0.1:8787</code>, then reload this demo.</div>`;
    }
  }
}

async function boot() {
  const input = el("#query");
  const button = el("#run");

  input.value = state.query;
  button.addEventListener("click", () => runSearch(input.value));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") runSearch(input.value);
  });

  document.querySelectorAll("[data-query]").forEach((buttonEl) => {
    buttonEl.addEventListener("click", () => {
      input.value = buttonEl.dataset.query;
      runSearch(input.value);
    });
  });

  runSearch(input.value);
}

boot();
