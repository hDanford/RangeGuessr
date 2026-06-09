# 🌿 RangeGuessr

A daily wildlife geography game — click the country where an animal lives in the wild. Built with vanilla HTML/CSS/JS, no backend required.

## Live at
👉 `https://[your-username].github.io/rangeguessr` (after GitHub Pages setup below)

---

## Features

- **Daily mode** — one new animal per day, seeded by date (same for all players)
- **Free play** — unlimited random animals with a session score
- **History calendar** — see every day you've played, your score, and which animal it was
- **IUCN conservation status** — every animal shows its real Red List status
- **Share button** — emoji result card for social media
- **Streak tracking** — consecutive daily wins
- **Ad-ready** — Google AdSense slots pre-wired, just uncomment and add your publisher ID

---

## Project structure

```
rangeguessr/
├── index.html          # Main page
├── css/
│   └── style.css       # All styles
├── js/
│   ├── game.js         # Game logic, scoring, storage
│   └── ui.js           # DOM rendering, map, modals
└── data/
    ├── animals.js      # Animal roster with ISO codes & facts
    └── countries.js    # SVG country path data
```

---

## Deploy to GitHub Pages

1. Create a new GitHub repository (e.g. `rangeguessr`)
2. Push this folder's contents to the `main` branch
3. Go to **Settings → Pages**
4. Set source to **Deploy from a branch** → `main` → `/ (root)`
5. Save — your site will be live at `https://[username].github.io/[repo-name]` within ~2 minutes

---

## Set up ads (Google AdSense)

1. Sign up at [Google AdSense](https://www.google.com/adsense)
2. Once approved, get your **Publisher ID** (`ca-pub-XXXXXXXXXXXXXXXX`)
3. In `index.html`, uncomment the AdSense script tag in `<head>` and replace the placeholder ID
4. Uncomment the two `<ins class="adsbygoogle">` blocks (top banner + bottom responsive)
5. Replace both `data-ad-slot` values with your actual ad unit slot IDs

Ad slots are pre-positioned at:
- **Top**: leaderboard (728×90) above the game
- **Bottom**: responsive unit below the game

---

## Add more animals

In `data/animals.js`, add a new object to the `ANIMALS` array:

```js
{
  id: "unique-kebab-id",
  name: "Common Name",
  emoji: "🐾",
  hint: "A memorable clue about this animal",
  status: "EN",  // CR | EN | VU | NT | LC
  iso: ["US","CA","MX"],  // ISO 3166-1 alpha-2 country codes
  fact: "An interesting conservation or biology fact.",
  region: "Display region name"
}
```

The daily rotation cycles through all animals using a date hash — adding more animals automatically expands the rotation.

---

## Add a custom domain

1. Buy a domain (e.g. `rangeguessr.game`)
2. In GitHub Pages settings, set **Custom domain** to your domain
3. Add a `CNAME` file to the repo root containing just your domain name
4. Configure your DNS: add a CNAME record pointing to `[username].github.io`

---

## Local development

Just open `index.html` in a browser — no build step, no server needed.

For live reload, use VS Code's Live Server extension or:
```bash
python3 -m http.server 8080
# then open http://localhost:8080
```

---

## Tech

- Pure HTML/CSS/JavaScript — zero dependencies, zero build tooling
- localStorage for history (no server, no accounts)
- Deterministic daily seed via date-string hash
- SVG world map with click detection
