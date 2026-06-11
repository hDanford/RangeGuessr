// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_LOCATION_SCORE    = 5000;
const MAX_STATUS_SCORE      = 5000;
const MAX_TOTAL             = 10000;
const LOCATION_DECAY_KM     = 10000;  // km at which location score reaches ~0
const STATUS_POINTS_PER_STEP = 1000; // lose 1000 per IUCN step off
const STORAGE_KEY           = "rangeguessr_v2_history";
const FREEPLAY_STATS_KEY    = "rangeguessr_v2_freeplay";
const ANIMALDEX_KEY         = "rangeguessr_v2_animaldex";

// ─── Date helpers ─────────────────────────────────────────────────────────────
function getTodayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

// Daily #1 = first scheduled day
const PUZZLE_EPOCH = "2026-06-09";
function puzzleNumber(dateKey) {
  const [y,m,d]    = dateKey.split("-").map(Number);
  const [ey,em,ed] = PUZZLE_EPOCH.split("-").map(Number);
  return Math.round((Date.UTC(y,m-1,d) - Date.UTC(ey,em-1,ed)) / 86400000) + 1;
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
  // DD is outside the threat spectrum — special flat scoring
  if (actualStatus === 'DD') {
    return guessedStatus === 'DD' ? 5000 : 4000;
  }
  // Guessing DD for an assessed species is an "I don't know" hedge — flat score
  // (tunable; without this, DD would score 4000 vs LC due to its STATUS_ORDER position)
  if (guessedStatus === 'DD') return 2500;
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

// ─── Free Play stats ──────────────────────────────────────────────────────────
function loadFreeplayStats() {
  try { return JSON.parse(localStorage.getItem(FREEPLAY_STATS_KEY)) || { gamesPlayed: 0, highScore: 0, bestSession: 0 }; }
  catch { return { gamesPlayed: 0, highScore: 0, bestSession: 0 }; }
}

function saveFreeplayStats(s) {
  localStorage.setItem(FREEPLAY_STATS_KEY, JSON.stringify(s));
}

// Called once per freeplay round submitted. `roundTotal` is that round's score;
// `sessionTotal` is the running session total after this round.
function recordFreeplayRound(roundTotal, sessionTotal) {
  const s = loadFreeplayStats();
  s.gamesPlayed += 1;
  if (roundTotal  > s.highScore)   s.highScore   = roundTotal;   // best single round
  if (sessionTotal > s.bestSession) s.bestSession = sessionTotal; // best session run
  saveFreeplayStats(s);
}

// ─── Animal Dex (best score per animal, across both modes) ─────────────────────
function loadAnimalDex() {
  try { return JSON.parse(localStorage.getItem(ANIMALDEX_KEY)) || {}; }
  catch { return {}; }
}

// dex shape: { [animalId]: { bestTotal, bestLocation, bestStatus, plays, lastMode, lastPlayed } }
function recordAnimalPlay(result, mode) {
  const dex = loadAnimalDex();
  const id  = result.animalId;
  const prev = dex[id] || { bestTotal: 0, bestLocation: 0, bestStatus: 0, plays: 0 };
  dex[id] = {
    bestTotal:    Math.max(prev.bestTotal,    result.total),
    bestLocation: Math.max(prev.bestLocation, result.locationScore),
    bestStatus:   Math.max(prev.bestStatus,   result.statusScore),
    plays:        prev.plays + 1,
    lastMode:     mode,
    lastPlayed:   result.date || getTodayKey(),
  };
  localStorage.setItem(ANIMALDEX_KEY, JSON.stringify(dex));
}

// result shape: { animalId, guessLat, guessLng, guessStatus, locationScore, statusScore, total, date }

// ─── Streak ───────────────────────────────────────────────────────────────────
function calcStreak() {
  const history = loadHistory();
  const fmt = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  let streak = 0;
  const check = new Date(); check.setHours(0,0,0,0);
  // If today hasn't been played yet, the streak isn't broken until tomorrow —
  // start counting from yesterday.
  if (!history[fmt(check)]) check.setDate(check.getDate()-1);
  for (let i = 0; i < 365; i++) {
    if (history[fmt(check)]) { streak++; check.setDate(check.getDate()-1); }
    else break;
  }
  return streak;
}

// ─── Stats ────────────────────────────────────────────────────────────────────
function calcStats() {
  const history = loadHistory();
  const results = Object.values(history);
  const n = results.length;
  if (!n) return null;

  let sumLoc = 0, sumStat = 0, sumTotal = 0, best = 0, inRange = 0, exactStatus = 0;
  for (const r of results) {
    sumLoc   += r.locationScore;
    sumStat  += r.statusScore;
    sumTotal += r.total;
    if (r.total > best)        best = r.total;
    if (r.insideRange)         inRange++;
    if (r.statusScore === MAX_STATUS_SCORE) exactStatus++; // only exact matches hit 5000
  }

  // Max streak: longest run of consecutive day keys (UTC math avoids DST issues)
  const keys = Object.keys(history).sort();
  let maxStreak = 0, cur = 0, prev = null;
  for (const k of keys) {
    const [y,m,d] = k.split("-").map(Number);
    const t = Date.UTC(y, m-1, d);
    cur = (prev !== null && t - prev === 86400000) ? cur + 1 : 1;
    if (cur > maxStreak) maxStreak = cur;
    prev = t;
  }

  return {
    gamesPlayed:   n,
    avgLocation:   Math.round(sumLoc / n),
    avgStatus:     Math.round(sumStat / n),
    avgTotal:      Math.round(sumTotal / n),
    bestScore:     best,
    pctInRange:    Math.round(inRange / n * 100),
    pctExactStatus:Math.round(exactStatus / n * 100),
    currentStreak: calcStreak(),
    maxStreak,
  };
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
  lastResult: null,
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
    GameState.lastResult = history[dateKey];
    return { alreadyPlayed: true, result: history[dateKey] };
  }
  GameState.lastResult = null;
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
  GameState.lastResult = null;
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
    recordFreeplayRound(total, GameState.freeplayScore);
  }

  // Per-animal best, across both modes
  recordAnimalPlay(result, GameState.mode);

  GameState.lastResult = result;
  return result;
}

// ─── Share ────────────────────────────────────────────────────────────────────
function buildShareText(result) {
  const a = ANIMALS.find(x => x.id === result.animalId);
  const locBar  = scoreBar(result.locationScore, MAX_LOCATION_SCORE);
  const statBar = scoreBar(result.statusScore, MAX_STATUS_SCORE);
  const mode = GameState.mode === "daily" ? `RangeGuessr #${puzzleNumber(result.date)}` : "RangeGuessr — Free Play";
  return `${mode}\n${a.emoji} ${a.name}\n📍 Location: ${locBar} ${result.locationScore}\n🏷 Status:   ${statBar} ${result.statusScore}\n🌿 Total: ${result.total}/10000\nhttps://rangeguessr.com`;
}

function scoreBar(score, max) {
  const filled = Math.round((score / max) * 5);
  return "🟩".repeat(filled) + "⬛".repeat(5 - filled);
}
