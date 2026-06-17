# Morning Brief — Operations Manual

A practical guide for running the daily media-monitoring brief. Written for PR
professionals, not developers. No coding knowledge needed for day-to-day use.

---

## What this tool is

The Morning Brief is an automated daily media-monitoring report for Adfactors PR
Lanka. Every weekday at 6:30 AM Sri Lanka time it searches the news for our six
clients — **HNB, Hayleys, MAS, BYD, MIFL, and Port City Colombo** — groups the
coverage by client, removes duplicates, classifies each story, and publishes a
clean web page you can open on any device.

It runs entirely on free infrastructure (GitHub Actions + GitHub Pages) and uses
**no Claude tokens** in normal operation — it is pure Python reading public news
feeds. It lives at **github.com/Mumble326-cmd/morning-brief** and publishes to
**https://mumble326-cmd.github.io/morning-brief/**.

---

## The brief — how to read it

**Controls bar** (top of the page):

- **Window** — `1d` / `7d` / `14d` / `30d`. How far back to show stories. The
  tool always *fetches* 30 days; this just filters what you see (default `7d`).
- **Client** — show all clients or just one.
- **Category** — `Mention` (the client is in the news) / `Industry` (sector or
  competitor news) / `Market Watch` (stock-market news) / `Risk Watch` (negative
  or reputational stories).
- **Search** — type to filter stories by any word in the headline, snippet, or
  outlet.
- **Show low relevance** — a toggle. Off by default; turn it on to see stories
  the tool judged weak matches.
- **↻ Refresh** — reloads the page to pull the latest published brief.
- **✎ Keyword Studio** — opens the in-browser editor (see *Updating keywords*).

**Story cards** show: the headline (links to the article), the publication, the
date, and a colour-coded **category tag**. Two extra badges may appear:

- **★ New** — the story wasn't in yesterday's brief.
- **✂ Manual Clip** — a story added by hand (see *Adding a manual clip*).

If the same story ran in several outlets, the duplicates are merged into one card
with an **"Also in"** row linking the other outlets.

**Executive Summary** strip at the very top lists the top stories across all
clients for the day. Each client section also shows a small **SOV sparkline** —
a per-day trend line plus that client's share of voice across all clients today.

---

## Daily workflow

Nothing to do. Wake up, open **https://mumble326-cmd.github.io/morning-brief/**,
and it's already updated for the day. The page rebuilds itself every weekday
morning automatically.

---

## Updating keywords

Keywords decide what each client's search pulls in. There are two ways to edit
them. (For *how* to choose good keywords, see `docs/keyword-guide.md`.)

**Option A — Keyword Studio (no technical knowledge):**

1. Open the brief and click **✎ Keyword Studio** (top right).
2. Click a client to expand it, then edit the tags under each category. Press
   **Enter** to add a tag, click **×** to remove one.
3. Click **↓ Download keywords.json**.
4. Go to **github.com/Mumble326-cmd/morning-brief** → **Add file → Upload files**
   → drag in the downloaded `keywords.json` → **Commit changes**.
5. To refresh immediately: **Actions → Daily Morning Brief → Run workflow**.

**Option B — Direct edit in VS Code:**

1. Open `keywords.json`, make your edits, **Ctrl+S**.
2. **Source Control** panel → write a message → **Commit** → **Sync Changes**.

**The five keyword categories** (per client):

- **direct_mentions** — the client's own names, subsidiaries, products. A hit
  here = **Mention**.
- **industry_watch** — competitors, regulators, sector terms. A hit here =
  **Industry**.
- **market_watch** — stock-exchange / index / trading terms. A hit = **Market
  Watch**.
- **risk_watch** — negative signals (fraud, recall, investigation, ban). A hit =
  **Risk Watch**. Checked *before* mentions so bad news is never buried.
- **exclude** — false-positive killers (sports, cricket, school). A hit here
  pushes the story to *low relevance*.

**query_context** — only **BYD** and **MIFL** have this, set to `"Sri Lanka"`.
Their names are globally ambiguous, so this forces `"Sri Lanka"` into every
search and stops the feed filling with global noise. Leave it as is.

---

## Adding a manual clip

Use this when an important story didn't get picked up automatically (e.g. an
outlet that blocks Google News indexing).

1. Open **Keyword Studio → Manual Clippings**.
2. Paste the article **URL** and click **Auto-fill ↗**.
3. Fill any fields it couldn't auto-fill (headline, source, date, snippet).
4. Select the **client** and the **category**.
5. Write a **reason** — why this matters. This becomes institutional memory for
   future briefs and Claude sessions, so be specific.
6. Click **+ Add to Clippings**, then **↓ Download manual_articles.json**.
7. Upload it to GitHub the same way as keywords (Add file → Upload files →
   commit).

**Note — sites that block auto-fill:** Daily Mirror and Sunday Times block the
auto-fill (CORS). For those, paste the article text into Claude chat and ask it
to add the clip directly to `manual_articles.json`.

**Note — manual clips ignore the date window.** They always show regardless of
age (e.g. the MIFL debenture clip is over 30 days old but still appears). This is
intentional — curated context shouldn't expire.

---

## Adding a new client

A two-step paste, no code changes. From the repo folder run:

```
py -3 new_client.py "Client Name" "Sector"
```

It prints two blocks:

1. **Step 1** — paste the printed JSON block into `keywords.json`, inside the
   top-level object.
2. **Step 2** — paste the printed entry into the `CLIENTS` list in `config.py`.

That's all. On the next run, a startup check warns you if the two files have
drifted apart (e.g. a client added to one but not the other).

For short or ambiguous brand names, add the context flag so the search stays
Sri Lanka-only:

```
py -3 new_client.py "Client Name" "Sector" --context "Sri Lanka"
```

---

## Triggering a manual run

To refresh the brief without waiting for tomorrow morning:

**github.com/Mumble326-cmd/morning-brief → Actions → Daily Morning Brief →
Run workflow.**

It finishes in about 90 seconds, then the live URL updates.

---

## Machines and setup

**Home laptop (ASUS TUF, Windows):**

- Python: **`py -3`** (not `python` or `python3`)
- pip: `py -3 -m pip install <package> --break-system-packages`
- Claude Code: run `claude` from the repo directory
- Repo: `C:\Users\ASUS TUF\morning-brief`

**Work laptop (Windows):**

- No Python installed — **edit and commit only**, via VS Code + Claude extension
- Repo: `C:\Users\Abdullah Firdousi\morning-brief`

**Git routine (always pull before changes):**

```
git pull --rebase origin main
git add .
git commit -m "message"
git push
```

The `--rebase` matters: the daily run commits the generated brief back to the
repo, so your local copy is usually behind. Always pull first.

---

## What auto-runs and when

GitHub Actions runs on cron `0 1 * * 1-5` — that's **1:00 AM UTC = 6:30 AM Sri
Lanka time, Monday to Friday**. The result is committed and published
automatically. You can also trigger a run any time via **Actions → Run
workflow**.

---

## Media contacts

Journalist names and contact details are **never** stored in this public repo.
They live in a private local file (`media-contacts.md`) that is not committed.
The brief shows outlet names only.

---

## Known limitations

- **Some outlets have no RSS feed.** Daily FT, Daily Mirror, The Morning, and
  Colombo Gazette expose no usable feed, so they arrive via Google News only —
  and some of their articles never get indexed there. Manual clips are the fix.
- **Google News results are volatile.** The same search returns different
  results run to run, because Google's date filter is loose. Daily story counts
  fluctuate — that's the data source, not a bug.
- **Google News links are redirect URLs** (`news.google.com/rss/…`). They work
  but are opaque. The tool tries to resolve them to the real publisher URL, but
  Google now uses a JavaScript interstitial, so most links stay as redirects.

---

**Repository:** https://github.com/Mumble326-cmd/morning-brief
**Live brief:** https://mumble326-cmd.github.io/morning-brief/
