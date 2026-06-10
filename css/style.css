// ─── Map projection helpers ───────────────────────────────────────────────────
// Equirectangular: viewBox 0 0 900 460
const MAP_W = 900, MAP_H = 460;

function latLngToXY(lat, lng) {
  const x = (lng + 180) / 360 * MAP_W;
  const y = (90 - lat) / 180 * MAP_H;
  return { x, y };
}

function xyToLatLng(x, y) {
  const lng = (x / MAP_W) * 360 - 180;
  const lat = 90 - (y / MAP_H) * 180;
  return { lat, lng };
}

// ─── UI ───────────────────────────────────────────────────────────────────────
const UI = {
  svgEl: null,
  markerEl: null,
  rangeGroupEl: null,
  resultMarkerEl: null,

  init() {
    this.svgEl = document.getElementById("world-svg");
    this.buildMapBase();
    this.bindNav();
    this.bindStatusPicker();
    this.bindSubmit();
    this.renderStreak();
  },

  // ── Map construction ──────────────────────────────────────────────────────
  buildMapBase() {
    // Ocean bg
    const ocean = document.createElementNS("http://www.w3.org/2000/svg","rect");
    ocean.setAttribute("width","900"); ocean.setAttribute("height","460");
    ocean.setAttribute("fill","#a8d8ea");
    this.svgEl.appendChild(ocean);

    // Country fills from countries.js (Natural Earth data)
    Object.entries(COUNTRY_PATHS).forEach(([iso, entry]) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg","path");
      path.setAttribute("d", entry.d);
      path.setAttribute("class","country");
      path.dataset.iso  = iso;
      path.dataset.name = entry.name;
      // Tooltip on hover
      const title = document.createElementNS("http://www.w3.org/2000/svg","title");
      title.textContent = entry.name;
      path.appendChild(title);
      this.svgEl.appendChild(path);
    });

    // Range highlight group (drawn above countries, below marker)
    this.rangeGroupEl = document.createElementNS("http://www.w3.org/2000/svg","g");
    this.rangeGroupEl.setAttribute("id","range-group");
    this.svgEl.appendChild(this.rangeGroupEl);

    // Guess marker
    this.markerEl = document.createElementNS("http://www.w3.org/2000/svg","g");
    this.markerEl.setAttribute("id","guess-marker");
    this.markerEl.style.display = "none";
    this.markerEl.innerHTML = `
      <circle r="10" fill="none" stroke="#ff6b35" stroke-width="2.5" opacity="0.9"/>
      <circle r="3"  fill="#ff6b35"/>
    `;
    this.svgEl.appendChild(this.markerEl);

    // Click handler
    this.svgEl.addEventListener("click", e => this.handleMapClick(e));
  },

  handleMapClick(e) {
    if (GameState.submitted) return;
    const rect = this.svgEl.getBoundingClientRect();
    const scaleX = MAP_W / rect.width;
    const scaleY = MAP_H / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top)  * scaleY;
    const { lat, lng } = xyToLatLng(x, y);

    GameState.pendingLat = lat;
    GameState.pendingLng = lng;

    // Move marker
    this.markerEl.style.display = "";
    this.markerEl.setAttribute("transform", `translate(${x},${y})`);

    // Show country name if clicked on one
    const target = e.target.closest(".country");
    const countryName = target ? target.dataset.name : null;
    const locText = countryName
      ? `📍 ${countryName} (${lat.toFixed(1)}°, ${lng.toFixed(1)}°)`
      : `📍 ${lat.toFixed(1)}°, ${lng.toFixed(1)}°`;

    this.updateSubmitBtn();
    document.getElementById("map-instruction").textContent = locText;
  },

  // ── Status picker ─────────────────────────────────────────────────────────
  bindStatusPicker() {
    document.querySelectorAll(".status-option").forEach(btn => {
      btn.addEventListener("click", () => {
        if (GameState.submitted) return;
        document.querySelectorAll(".status-option").forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        GameState.pendingStatus = btn.dataset.status;
        this.updateSubmitBtn();
      });
    });
  },

  // ── Submit ────────────────────────────────────────────────────────────────
  bindSubmit() {
    document.getElementById("submit-btn").addEventListener("click", () => {
      if (GameState.pendingLat === null) {
        this.flashInstruction("Click the map first to place your guess!"); return;
      }
      if (!GameState.pendingStatus) {
        this.flashInstruction("Pick a conservation status first!"); return;
      }
      const result = submitGuess();
      if (result) this.showResult(result);
    });
  },

  updateSubmitBtn() {
    const ready = GameState.pendingLat !== null && GameState.pendingStatus !== null;
    const btn = document.getElementById("submit-btn");
    btn.disabled = !ready || GameState.submitted;
    btn.classList.toggle("ready", ready && !GameState.submitted);
  },

  flashInstruction(msg) {
    const el = document.getElementById("map-instruction");
    el.textContent = msg;
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1200);
  },

  // ── Nav ───────────────────────────────────────────────────────────────────
  bindNav() {
    document.getElementById("btn-daily").addEventListener("click",    () => this.showDaily());
    document.getElementById("btn-freeplay").addEventListener("click", () => this.showFreeplay());
    document.getElementById("btn-history").addEventListener("click",  () => this.openModal("history"));
    document.getElementById("btn-how").addEventListener("click",      () => this.openModal("how"));
    document.getElementById("btn-donate").addEventListener("click",   () => this.openModal("donate"));
    document.getElementById("modal-close").addEventListener("click",  () => this.closeModal());
    document.getElementById("modal-overlay").addEventListener("click", e => {
      if (e.target.id === "modal-overlay") this.closeModal();
    });
    document.getElementById("freeplay-next").addEventListener("click", () => {
      nextFreeplayAnimal();
      this.renderGame();
    });
    document.getElementById("share-btn").addEventListener("click", () => this.share());
  },

  setActiveNav(id) {
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.getElementById(id).classList.add("active");
  },

  // ── Screens ───────────────────────────────────────────────────────────────
  showDaily() {
    this.setActiveNav("btn-daily");
    document.getElementById("freeplay-controls").style.display = "none";
    const init = startDaily();
    this.renderGame();
    if (init.alreadyPlayed) this.showResult(init.result, true);
  },

  showFreeplay() {
    this.setActiveNav("btn-freeplay");
    startFreeplay();
    document.getElementById("freeplay-controls").style.display = "flex";
    this.renderGame();
  },

  // ── Game render ───────────────────────────────────────────────────────────
  renderGame() {
    const a = GameState.animal;
    const meta = STATUS_META[a.status] || STATUS_META["LC"];

    document.getElementById("animal-name").textContent   = a.name;
    document.getElementById("animal-sci").textContent    = a.scientificName || "";
    document.getElementById("animal-hint").textContent   = a.hint;

    // Thumbnail — show image if available, else show a link to view it
    const imgEl      = document.getElementById("animal-img");
    const fallbackEl = document.getElementById("animal-img-fallback");
    const creditEl   = document.getElementById("animal-img-credit");
    imgEl.style.display      = "none";
    fallbackEl.style.display = "none";
    creditEl.style.display   = "none";
    if (a.image) {
      imgEl.src = a.image;
      imgEl.alt = a.name;
      imgEl.onload = () => {
        imgEl.style.display    = "block";
        fallbackEl.style.display = "none";
        if (a.imageCredit || a.imageLicense) {
          creditEl.textContent = [a.imageCredit, a.imageLicense].filter(Boolean).join(" · ");
          creditEl.style.display = "block";
        }
      };
      imgEl.onerror = () => {
        imgEl.style.display      = "none";
        fallbackEl.href          = a.image;
        fallbackEl.textContent   = `View ${a.name} photo →`;
        fallbackEl.style.display = "block";
      };
    } else {
      fallbackEl.style.display = "none";
    }

    const badge = document.getElementById("status-badge");
    badge.textContent      = meta.label;
    badge.style.background = meta.bg;
    badge.style.color      = meta.color;
    badge.style.display    = "none"; // revealed after guessing

    if (GameState.mode === "daily") {
      document.getElementById("mode-label").textContent = `Daily — ${getTodayKey()}`;
    } else {
      document.getElementById("mode-label").textContent =
        `Free Play · Round ${GameState.freeplayRound} · Session: ${GameState.freeplayScore} pts`;
    }

    // Reset map
    this.clearRange();
    this.markerEl.style.display = "none";
    GameState.pendingLat = GameState.pendingLng = GameState.pendingStatus = null;

    // Reset status picker
    document.querySelectorAll(".status-option").forEach(b => b.classList.remove("selected"));

    // Reset submit + result
    this.updateSubmitBtn();
    document.getElementById("map-instruction").textContent = "Click the map to place your guess";
    document.getElementById("result-panel").style.display  = "none";
    document.getElementById("share-btn").style.display     = "none";
    document.getElementById("freeplay-next").style.display = "none";

    this.renderStreak();
  },

  // ── Range polygon overlay ─────────────────────────────────────────────────
  drawRange(rangePolygons) {
    this.clearRange();
    rangePolygons.forEach(poly => {
      const pts = poly.map(p => {
        const {x,y} = latLngToXY(p.lat, p.lng);
        return `${x},${y}`;
      }).join(" ");
      const polygon = document.createElementNS("http://www.w3.org/2000/svg","polygon");
      polygon.setAttribute("points", pts);
      polygon.setAttribute("fill","rgba(255,215,0,0.22)");
      polygon.setAttribute("stroke","#FFD700");
      polygon.setAttribute("stroke-width","1.8");
      this.rangeGroupEl.appendChild(polygon);
    });
  },

  clearRange() {
    while (this.rangeGroupEl && this.rangeGroupEl.firstChild) {
      this.rangeGroupEl.removeChild(this.rangeGroupEl.firstChild);
    }
  },

  // Draw a line from guess point to nearest range edge (if outside)
  drawDistanceLine(guessLat, guessLng, rangePolygons, insideAny) {
    if (insideAny) return;
    // Find closest point on any polygon edge
    let minDist = Infinity, closestLat = 0, closestLng = 0;
    for (const poly of rangePolygons) {
      for (let i = 0; i < poly.length; i++) {
        const a = poly[i], b = poly[(i+1)%poly.length];
        const dx = b.lng-a.lng, dy = b.lat-a.lat;
        const lenSq = dx*dx+dy*dy;
        let t = lenSq > 0 ? ((guessLng-a.lng)*dx+(guessLat-a.lat)*dy)/lenSq : 0;
        t = Math.max(0,Math.min(1,t));
        const cLat = a.lat+t*dy, cLng = a.lng+t*dx;
        const d = haversineKm(guessLat,guessLng,cLat,cLng);
        if (d < minDist) { minDist=d; closestLat=cLat; closestLng=cLng; }
      }
    }
    const g1 = latLngToXY(guessLat, guessLng);
    const g2 = latLngToXY(closestLat, closestLng);
    const line = document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",g1.x); line.setAttribute("y1",g1.y);
    line.setAttribute("x2",g2.x); line.setAttribute("y2",g2.y);
    line.setAttribute("stroke","#FFD700");
    line.setAttribute("stroke-width","1.5");
    line.setAttribute("stroke-dasharray","4 3");
    line.setAttribute("opacity","0.9");
    this.rangeGroupEl.appendChild(line);
  },

  // ── Result ────────────────────────────────────────────────────────────────
  showResult(result, alreadyPlayed = false) {
    const a = ANIMALS.find(x => x.id === result.animalId) || GameState.animal;
    const locLabel = locationLabel(result.distKm, result.insideRange);
    const correctMeta = STATUS_META[a.status];
    const guessMeta   = STATUS_META[result.guessStatus] || {};
    const stepsOff    = Math.abs(STATUS_ORDER.indexOf(result.guessStatus) - STATUS_ORDER.indexOf(a.status));

    // Draw range + distance line
    this.drawRange(a.rangePolygons);
    if (!result.insideRange) {
      this.drawDistanceLine(result.guessLat, result.guessLng, a.rangePolygons, false);
    }

    // Move marker to guess location
    const {x,y} = latLngToXY(result.guessLat, result.guessLng);
    this.markerEl.setAttribute("transform", `translate(${x},${y})`);
    this.markerEl.style.display = "";

    // Highlight guessed status in picker
    document.querySelectorAll(".status-option").forEach(b => {
      b.classList.remove("selected");
      if (b.dataset.status === result.guessStatus) b.classList.add("selected");
    });

    // Populate result panel
    document.getElementById("res-location-score").textContent = result.locationScore;
    document.getElementById("res-status-score").textContent   = result.statusScore;
    document.getElementById("res-total").textContent          = result.total;
    document.getElementById("res-loc-label").textContent      = result.insideRange
      ? "Inside the range! 🎯"
      : `${Math.round(result.distKm).toLocaleString()} km from the range`;
    document.getElementById("res-loc-label").className = "res-detail " + locLabel.cls;

    const statusLine = document.getElementById("res-status-label");
    if (stepsOff === 0) {
      statusLine.textContent = "Exact conservation status! 🎯";
      statusLine.className = "res-detail perfect";
    } else {
      statusLine.textContent = `${stepsOff} step${stepsOff>1?"s":""} off — correct: ${correctMeta.label}`;
      statusLine.className = "res-detail " + (stepsOff === 1 ? "hot" : stepsOff === 2 ? "warm" : "cold");
    }

    document.getElementById("res-fact").textContent   = `🔬 ${a.fact}`;
    document.getElementById("res-region").textContent = `Native range: ${a.region}`;

    // Reveal large photo after guessing
    const imgWrap  = document.getElementById("res-image-wrap");
    const resImg   = document.getElementById("res-image");
    const resCredit= document.getElementById("res-image-credit");
    if (a.image) {
      resImg.src = a.image;
      resImg.alt = a.name;
      const licenseShort = a.imageLicense
        ? a.imageLicense.replace("https://creativecommons.org/licenses/","CC ").replace("https://creativecommons.org/publicdomain/","CC ").replace(/\/[\d.]+\/$/,"").toUpperCase()
        : "";
      resCredit.textContent = [a.imageCredit, licenseShort].filter(Boolean).join(" · ");
      imgWrap.style.display = "block";
      resImg.onerror = () => { imgWrap.style.display = "none"; };
    } else {
      imgWrap.style.display = "none";
    }

    // Score ring color
    const pct = result.total / MAX_TOTAL;
    const ringColor = pct >= 0.8 ? "#4a9e4a" : pct >= 0.5 ? "#e8a020" : "#c0392b";
    document.getElementById("res-ring").style.stroke = ringColor;
    const circumference = 2 * Math.PI * 28;
    document.getElementById("res-ring").style.strokeDashoffset =
      circumference * (1 - pct);

    document.getElementById("result-panel").style.display  = "block";
    // Reveal the correct status badge now that the guess is in
    const badge = document.getElementById("status-badge");
    const correctMeta2 = STATUS_META[a.status] || STATUS_META["LC"];
    badge.textContent      = correctMeta2.label;
    badge.style.background = correctMeta2.bg;
    badge.style.color      = correctMeta2.color;
    badge.style.display    = "inline-block";
    document.getElementById("share-btn").style.display     = "inline-flex";
    if (GameState.mode === "freeplay") {
      document.getElementById("freeplay-next").style.display = "inline-flex";
      document.getElementById("freeplay-score-display").textContent =
        `Session total: ${GameState.freeplayScore} pts`;
    }

    GameState.submitted = true;
    document.getElementById("submit-btn").disabled = true;
    document.getElementById("map-instruction").textContent =
      alreadyPlayed ? "You already played today — range shown above" : "Range revealed above";

    this.renderStreak();
  },

  // ── History ───────────────────────────────────────────────────────────────
  renderHistoryCalendar() {
    const history = loadHistory();
    const container = document.getElementById("history-content");
    const dates = Object.keys(history).sort().reverse();

    if (!dates.length) {
      container.innerHTML = `<p class="empty-history">No games yet — try today's daily!</p>`;
      return;
    }

    const byMonth = {};
    dates.forEach(d => {
      const key = d.slice(0,7);
      (byMonth[key] = byMonth[key]||[]).push(d);
    });

    let html = "";
    Object.entries(byMonth).sort((a,b)=>b[0].localeCompare(a[0])).forEach(([mk, days]) => {
      const [y,m] = mk.split("-");
      const name = new Date(y,m-1,1).toLocaleString("default",{month:"long",year:"numeric"});
      html += `<div class="cal-month"><h3 class="cal-month-name">${name}</h3><div class="cal-grid">`;
      days.sort().forEach(dk => {
        const r = history[dk];
        const animal = ANIMALS.find(a=>a.id===r.animalId);
        const emoji  = animal ? animal.emoji : "🐾";
        const day    = parseInt(dk.split("-")[2]);
        const pct    = r.total / MAX_TOTAL;
        const cls    = pct >= 0.8 ? "great" : pct >= 0.5 ? "ok" : "low";
        html += `<div class="cal-day ${cls}" title="${dk} — ${animal?.name||''}">
          <span class="cal-emoji">${emoji}</span>
          <span class="cal-day-num">${day}</span>
          <span class="cal-score">${r.total}</span>
        </div>`;
      });
      html += `</div></div>`;
    });
    container.innerHTML = html;
  },

  // ── Streak ────────────────────────────────────────────────────────────────
  renderStreak() {
    const s = calcStreak();
    document.getElementById("streak-display").textContent = s > 0 ? `🔥 ${s}` : "";
  },

  // ── Share ─────────────────────────────────────────────────────────────────
  async share() {
    const history = loadHistory();
    const result  = history[GameState.dateKey] ||
                    { animalId: GameState.animal.id, locationScore: 0, statusScore: 0, total: 0,
                      guessLat: GameState.pendingLat||0, guessLng: GameState.pendingLng||0,
                      guessStatus: GameState.pendingStatus||"LC", insideRange: false, distKm: 9999 };
    const text = buildShareText(result);
    if (navigator.share) { try { await navigator.share({ text }); return; } catch {} }
    await navigator.clipboard.writeText(text).catch(()=>{});
    const btn = document.getElementById("share-btn");
    const orig = btn.textContent;
    btn.textContent = "Copied! ✓";
    setTimeout(() => btn.textContent = orig, 2000);
  },

  // ── Modal ─────────────────────────────────────────────────────────────────
  openModal(type) {
    document.getElementById("modal-overlay").style.display = "flex";
    document.getElementById("modal-history").style.display = type==="history" ? "block" : "none";
    document.getElementById("modal-how").style.display     = type==="how"     ? "block" : "none";
    document.getElementById("modal-donate").style.display  = type==="donate"  ? "block" : "none";
    if (type === "history") this.renderHistoryCalendar();
  },

  closeModal() {
    document.getElementById("modal-overlay").style.display = "none";
  },
};
