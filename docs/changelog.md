# Morning Brief - Changelog

## 2026-06-11

### Major Updates

#### Keywords Structure Overhaul
- Migrated from basic `mentions`/`industry` to comprehensive keyword governance model
- Each client now has: `sector`, `must_include`, `direct_mentions`, `industry_watch`, `exclude`, `priority_sources`
- This enables stricter filtering and cleaner reporting

#### HNB Expansion
- Added subsidiaries: HNB General Insurance, HNB Investment Bank, HNB Securities, HNB Stockbrokers
- Added financial products: HNB SOLO, HNB MOMO, HNB leasing, HNB pawning, HNB SME, HNB digital banking
- Added regulatory terms: AWPLR, SLFR, SDFR, CRIB, NPL, credit growth
- Added competitor banks for industry context: People's Bank, DFCC Bank
- Reason: Google News missed subsidiary coverage; now properly tracks banking sector context

#### Hayleys Expansion
- Added all major subsidiaries: Hayleys Fentons, Aventura, Consumer, Free Zone, Lifecode, Agriculture, Electronics
- Added related entities: Kelani Valley Plantations, Dipped Products, Logiwiz, Unisyst
- Expanded industry watch with sector-specific terms: tea estates, rubber exports, activated carbon, logistics
- Reason: Better coverage of conglomerate ecosystem; reduce noise from unrelated "Hayley" stories

#### MAS Expansion
- Overhauled mentions with all brands: MAS Kreeda, Bodyline, Silueta, Fabric Park, Twinery, Linea Aqua, etc.
- Added specific exclusions: "Brandix cricket", "school apparel" to eliminate sports/school noise
- Expanded industry with GSP+ tariff tracking, US tariff implications
- Reason: Sports/school coverage was polluting results; now targets manufacturing/export focus

#### BYD Expansion
- Added vehicle models: Atto 3, Dolphin, Seal
- Added service touchpoints: aftersales, service centre, showroom, charging
- Added Denza brand for premium EV track
- Added Motor Traffic policy terms
- Reason: More precise vehicle launch/service/policy coverage

#### MIFL Tightening
- Restricted to only Mahindra Ideal Finance mentions (avoid sports league pollution)
- Added strict exclusions: "MIFL football", "MIFL league", "MIFL sports", "Michigan", "India league"
- Expanded finance company landscape
- Reason: MIFL acronym is high-risk for false matches

#### Port City Colombo Enhancement
- Added SEZ governance terms: Port City Economic Commission, CCEC
- Added banking partnership focus: Sampath Bank Port City, Commercial Bank Port City
- Added financial centre positioning
- Reason: Track investment inflows and banking partnerships separately from general real estate

### Governance Updates
- Created `outlets.json` to govern media sources and domain whitelist
- Created `docs/` folder structure for documentation
- Created `data/` folder with `archive/` for historical tracking
- Created `.github/workflows/` for CI/CD organization

### Next Steps
1. Update `brief.py` to read from new keyword structure
2. Add archive output: `data/latest.json` and `data/archive/YYYY-MM-DD.json`
3. Add duplicate story grouping logic
4. Build client report view with date range and story filtering
5. Add PDF export capability

### Breaking Changes
- Keyword file structure changed: `mentions` → `direct_mentions`, `industry` → `industry_watch`
- **Required:** Update `brief.py` to parse new structure

## 2026-07-03

### Bugs Found and Fixed

1. **Executive Summary showed stale news as "top stories today."** `pick_executive_stories`
   scored candidates by category weight × source quality × freshness, but "freshness" only
   checked `is_new` (new since yesterday's archive) — it never checked actual story age. A
   manual clip from 15 Apr 2026 (MIFL's CSE debenture debut, `also_covered_by` from a
   priority outlet, `manual` bonus ×1.3) outscored every real story on the 2 Jul brief and
   sat at #1 in the Executive Summary for weeks. *Fix:* candidates are now restricted to
   stories published within 3 days of generation time (`EXEC_RECENCY_MS`). Files: `brief.py`.

2. **Duplicate outlet chips on stories fetched twice for one client.** The same article
   could enter `all_stories` twice — once per split `direct_mentions` query group (10+ term
   clients) or once via Google News and again via a direct outlet feed — and `cluster_stories`
   never deduped members before building `also_covered_by`, so a single outlet (e.g.
   "Newswire") could appear twice as a coverage chip on the same card. *Fix:* global
   `(client, url)` de-dupe of `all_stories` before classification, plus a defensive URL
   de-dupe when building `also_covered_by`. Files: `brief.py`, `utils.py`.

3. **`cluster_id` churned when a better outlet picked up an existing story.** It was hashed
   from the current *primary* story's headline, but the primary is re-chosen every run by
   source rank — so when a higher-ranked outlet (e.g. Daily FT) later covered a story a
   lower-ranked outlet (e.g. Newswire) broke first, the cluster got a brand-new `cluster_id`
   on the day the primary flipped. This falsely re-flagged old stories as "New" and broke
   day-over-day trend/SOV continuity for that story. *Fix:* `cluster_id` is now anchored to
   the earliest-published member's headline, which doesn't change as later outlets pick up
   the story. Files: `utils.py`.

4. **No retry on transient fetch failures.** A single dropped Google News or outlet-feed
   request silently returned zero stories for that client/query, with no way to distinguish
   a real no-news day from a flaky connection (e.g. 2026-06-26, where HNB, MAS, and Port
   City had zero stories archived that day — almost certainly a network blip, not an actual
   news vacuum for three unrelated clients on the same day). *Fix:* one retry with a 2s
   backoff on both `fetch_news` and `fetch_outlet_feed`. Files: `brief.py`.

### Known, Not Code Bugs (keyword/editorial tuning — see `docs/keyword-guide.md`)

- MAS, BYD, MIFL, and Port City still produce far fewer `industry_watch` hits than HNB —
  HNB's keyword set is the most mature (fed from real tracker data early on); the others
  need the same treatment via Keyword Studio or a follow-up tuning pass.
- Near-duplicate headlines from different outlets that are reworded past the 0.38 Jaccard
  threshold still surface as separate cards instead of one card with multiple outlet chips
  (documented in `docs/diagnostic.md` as the JAECOO J5 case). Lowering the threshold risks
  false merges of unrelated stories; needs a content-aware rule (shared entities/numbers),
  not attempted here for lack of live data to validate against.
