// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_LOCATION_SCORE    = 5000;
const MAX_STATUS_SCORE      = 5000;
const MAX_TOTAL             = 10000;
const LOCATION_DECAY_KM     = 10000;  // km at which location score reaches ~0
const STATUS_POINTS_PER_STEP = 1000; // lose 1000 per IUCN step off
const STORAGE_KEY           = "rangeguessr_v2_history";

// ─── Date helpers ─────────────────────────────────────────────────────────────
function getTodayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function hashStr(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h;
}

function getDailyAnimal(dateKey) {
  // Use schedule if available for this date
  if (typeof SCHEDULE !== "undefined" && SCHEDULE[dateKey]) {
    const a = ANIMALS.find(a => a.id === SCHEDULE[dateKey]);
    if (a) return a;
  }
  // Fallback: hash-based selection
  return ANIMALS[hashStr(dateKey) % ANIMALS.length];
}

// ─── Geo math ─────────────────────────────────────────────────────────────────
function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
            Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// Point-in-polygon (ray casting)
function pointInPolygon(lat, lng, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].lng, yi = polygon[i].lat;
    const xj = polygon[j].lng, yj = polygon[j].lat;
    if (((yi > lat) !== (yj > lat)) && (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi)) {
      inside = !inside;
    }
  }
  return inside;
}

// Closest distance from a point to a polygon edge (in km)
function distToPolygonEdgeKm(lat, lng, polygon) {
  let minDist = Infinity;
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];
    // Project point onto segment, clamp to [0,1]
    const dx = b.lng - a.lng, dy = b.lat - a.lat;
    const lenSq = dx*dx + dy*dy;
    let t = lenSq > 0 ? ((lng - a.lng)*dx + (lat - a.lat)*dy) / lenSq : 0;
    t = Math.max(0, Math.min(1, t));
    const closestLat = a.lat + t * dy;
    const closestLng = a.lng + t * dx;
    const d = haversineKm(lat, lng, closestLat, closestLng);
    if (d < minDist) minDist = d;
  }
  return minDist;
}

// Returns {insideAny, distKm} — distKm=0 if inside any polygon
function distToRange(lat, lng, rangePolygons) {
  for (const poly of rangePolygons) {
    if (pointInPolygon(lat, lng, poly)) return { insideAny: true, distKm: 0 };
  }
  let minDist = Infinity;
  for (const poly of rangePolygons) {
    const d = distToPolygonEdgeKm(lat, lng, poly);
    if (d < minDist) minDist = d;
  }
  return { insideAny: false, distKm: minDist };
}

// ─── Scoring ──────────────────────────────────────────────────────────────────
function calcLocationScore(lat, lng, rangePolygons) {
  const { insideAny, distKm } = distToRange(lat, lng, rangePolygons);
  if (insideAny) return MAX_LOCATION_SCORE;
  // Linear decay: 0 km off = 5000, LOCATION_DECAY_KM off = 0
  const score = MAX_LOCATION_SCORE * (1 - distKm / LOCATION_DECAY_KM);
  return Math.max(0, Math.round(score));
}

function calcStatusScore(guessedStatus, actualStatus) {
  const guessOrder  = STATUS_ORDER.indexOf(guessedStatus);
  const actualOrder = STATUS_ORDER.indexOf(actualStatus);
  const steps = Math.abs(guessOrder - actualOrder);
  return Math.max(0, MAX_STATUS_SCORE - steps * STATUS_POINTS_PER_STEP);
}

function calcTotal(locationScore, statusScore) {
  return locationScore + statusScore;
}

// Label for how good the location guess was
function locationLabel(distKm, inside) {
  if (inside)         return { text: "Inside the range!", cls: "perfect" };
  if (distKm <  500)  return { text: `${Math.round(distKm)} km from the range`, cls: "hot" };
  if (distKm < 1500)  return { text: `${Math.round(distKm)} km from the range`, cls: "warm" };
  if (distKm < 3000)  return { text: `${Math.round(distKm)} km from the range`, cls: "cold" };
  return               { text: `${Math.round(distKm)} km from the range`, cls: "miss" };
}

// ─── Storage ──────────────────────────────────────────────────────────────────
function loadHistory() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
  catch { return {}; }
}

function saveResult(dateKey, result) {
  const h = loadHistory();
  h[dateKey] = result;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(h));
}

// result shape: { animalId, guessLat, guessLng, guessStatus, locationScore, statusScore, total, date }

// ─── Streak ───────────────────────────────────────────────────────────────────
function calcStreak() {
  const history = loadHistory();
  let streak = 0;
  const check = new Date(); check.setHours(0,0,0,0);
  for (let i = 0; i < 365; i++) {
    const key = check.toISOString().slice(0,10);
    if (history[key]) { streak++; check.setDate(check.getDate()-1); }
    else break;
  }
  return streak;
}

// ─── Game State ───────────────────────────────────────────────────────────────
const GameState = {
  mode: "daily",
  animal: null,
  dateKey: null,
  pendingLat: null,
  pendingLng: null,
  pendingStatus: null,
  submitted: false,
  freeplayScore: 0,
  freeplayRound: 0,
  freeplayUsedIds: [],
};

function startDaily() {
  const dateKey = getTodayKey();
  GameState.mode      = "daily";
  GameState.dateKey   = dateKey;
  GameState.animal    = getDailyAnimal(dateKey);
  GameState.pendingLat= null;
  GameState.pendingLng= null;
  GameState.pendingStatus = null;
  GameState.submitted = false;

  const history = loadHistory();
  if (history[dateKey]) {
    GameState.submitted = true;
    return { alreadyPlayed: true, result: history[dateKey] };
  }
  return { alreadyPlayed: false };
}

function startFreeplay() {
  GameState.mode  = "freeplay";
  GameState.freeplayScore = 0;
  GameState.freeplayRound = 0;
  GameState.freeplayUsedIds = [];
  nextFreeplayAnimal();
}

function nextFreeplayAnimal() {
  let pool = ANIMALS.filter(a => !GameState.freeplayUsedIds.includes(a.id));
  if (!pool.length) { GameState.freeplayUsedIds = []; pool = ANIMALS; }
  const pick = pool[Math.floor(Math.random() * pool.length)];
  GameState.animal = pick;
  GameState.freeplayUsedIds.push(pick.id);
  GameState.pendingLat = null;
  GameState.pendingLng = null;
  GameState.pendingStatus = null;
  GameState.submitted = false;
  GameState.freeplayRound++;
}

function submitGuess() {
  if (GameState.submitted) return null;
  if (GameState.pendingLat === null || GameState.pendingStatus === null) return null;

  const a = GameState.animal;
  const locScore = calcLocationScore(GameState.pendingLat, GameState.pendingLng, a.rangePolygons);
  const statScore = calcStatusScore(GameState.pendingStatus, a.status);
  const total = calcTotal(locScore, statScore);
  const { insideAny, distKm } = distToRange(GameState.pendingLat, GameState.pendingLng, a.rangePolygons);

  GameState.submitted = true;

  const result = {
    animalId: a.id,
    guessLat: GameState.pendingLat,
    guessLng: GameState.pendingLng,
    guessStatus: GameState.pendingStatus,
    locationScore: locScore,
    statusScore: statScore,
    total,
    insideRange: insideAny,
    distKm: insideAny ? 0 : distKm,
    date: GameState.dateKey || getTodayKey(),
  };

  if (GameState.mode === "daily") {
    saveResult(GameState.dateKey, result);
  } else {
    GameState.freeplayScore += total;
  }

  return result;
}

// ─── Share ────────────────────────────────────────────────────────────────────
function buildShareText(result) {
  const a = ANIMALS.find(x => x.id === result.animalId);
  const locBar  = scoreBar(result.locationScore, MAX_LOCATION_SCORE);
  const statBar = scoreBar(result.statusScore, MAX_STATUS_SCORE);
  const mode = GameState.mode === "daily" ? `RangeGuessr ${result.date}` : "RangeGuessr — Free Play";
  return `${mode}\n${a.emoji} ${a.name}\n📍 Location: ${locBar} ${result.locationScore}\n🏷 Status:   ${statBar} ${result.statusScore}\n🌿 Total: ${result.total}/10000\nhttps://rangeguessr.game`;
}

function scoreBar(score, max) {
  const filled = Math.round((score / max) * 5);
  return "🟩".repeat(filled) + "⬛".repeat(5 - filled);
}
