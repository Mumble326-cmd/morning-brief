# Morning Brief - Changelog

## 2026-07-07

### Relevance Overhaul — make the default view an actual morning brief

Second overhaul. The first (2026-06, see `docs/diagnostic.md`) fixed dedup and
classification bugs; this one fixes the product failure that remained: the
page read as a 30-day archive (75 cards, only ~8 new, a third of them 14–30
days old), flooded with flat-scored CBSL administrivia and sports junk.

#### Morning-brief-first layout
- Default view now answers "what happened since yesterday?": an executive
  summary strip (top stories across all clients, new-first, ranked), then
  per-client sections showing only NEW-since-last-run cards
- A client with nothing new shows an explicit "No new coverage since the
  previous brief (date)" line instead of stale padding
- Everything older collapses into a per-client "Previously reported" block;
  manual clips pin to its top. Filters/search/coverage-PDF unchanged
- Reason: the reader was re-scrolling the same stale cards every morning; the
  brief must be readable in under 30 seconds

#### Noise suppression
- Recurring time-series posts (daily CBSL USD selling rate, T-bill auctions,
  market close) are detected via `config.SERIES_PATTERNS` plus a
  digits-stripped-signature fallback and rolled up to a single "Recurring
  updates" line; repeats are suppressed (`is_series_repeat` in JSON)
- Per-client per-day caps on filler categories (`config.CATEGORY_CAPS`:
  5 industry / 3 market watch), best compound score survives, overflow kept
  in JSON as `is_capped`
- `config.GLOBAL_EXCLUDE`: sports/junk vocabulary applied to every client
  (kills "Bowlers star in LOLC Holdings' five wicket win" under MAS)
- low_relevance stories no longer render at all (previously they shipped in
  the DOM behind a toggle); they remain in `data/latest.json` for audit
- Outlet boilerplate stripped from headlines and snippets ("Sri Lanka Latest
  Breaking News and Headlines - Print Edition …", "… | Daily Mirror - Sri
  Lanka - newspaper"); snippets that merely restate the headline are dropped

#### Compound relevance scoring
- `compound_score()` = category weight × match strength (brand-in-headline >
  snippet-only > fetch-floor) × source-rank weight (outlets.json) ×
  freshness decay (36h half-life), scaled 0–100
- Drives ordering everywhere: sections, "Previously reported", executive
  summary, cap survival. Replaces the flat 1.0/0.7/0.0 relevance for ranking
  (the old field is kept for compatibility)

#### Keyword governance (keywords.json)
- HNB: naked "CBSL" / "Central Bank of Sri Lanka" industry terms replaced
  with policy-scoped variants (monetary policy / policy rate / rate decision /
  banking supervision); excludes added for pyramid-scheme lists and
  finance-company administrator/wind-up administrivia
- Hayleys: + HayWind (Mannar wind farm coverage was scoring low_relevance)
- MAS: + MAS Legato; industry recall variants (Sri Lanka apparel, apparel
  industry Sri Lanka, textile exports Sri Lanka)
- BYD: + BYD Sri Lanka / BYD Lanka; MIFL: + Mahindra Ideal Finance Limited /
  Ideal Finance PLC; Port City: + "Port City" (container-terminal noise is
  already excluded)

#### Offline replay harness + assertion suite
- `python brief.py --replay [DATE]` rebuilds the raw pool from that date's
  archive and re-runs the identical `run_pipeline()` the live GitHub Action
  uses — classification, scoring, dedup, rollup, render — with no network.
  Replay never overwrites dated archives
- `python replay_checks.py [DATE]` replays and asserts: no low_relevance or
  capped cards rendered, caps respected, cricket junk absent, rate posts
  rolled up, exec summary populated, every client section present with new
  cards XOR an explicit no-news line, boilerplate gone. Non-zero exit on
  failure. Verified on 2026-06-11, 2026-06-26, 2026-07-06, 2026-07-07

#### Polish round (critic review)
- First-run semantics: with no previous archive every story is now marked
  NEW (previously all six sections claimed "no new coverage since the
  previous brief" about a brief that never existed, with the entire run
  collapsed into "Previously reported"). The no-coverage wording adapts,
  and risk alerts stay suppressed on a first run — a blanket issue listing
  every risk story is noise, not an alert
- Search now auto-opens the collapsed "Previously reported" block while a
  query is active (matches inside it were invisible before) and re-collapses
  it when cleared, without touching a block the user opened manually
- Digit-signature series grouping is restricted to industry/market_watch:
  on 2026-06-11 it had demoted the "HNB Finance records exceptional FY
  2025/26 growth, PAT doubled" Mention — that day's top HNB story — to a
  one-line recurring update. Explicit SERIES_PATTERNS still apply everywhere
- `--replay` now writes to the untracked `replay_output/` directory by
  default (pass `--write` to regenerate index.html / data/latest.json /
  data/alerts.json in place), so a replayed old morning can't be committed
  by accident; replay_checks.py asserts the committed artifacts stay
  untouched by a replay
- Google News queries are now built via `build_queries()`, which splits any
  keyword list whose URL-encoded query would exceed a 1000-char budget into
  multiple fetches (overlong queries silently return 0 results — the tuned
  HNB industry list had crossed that line). replay_checks.py unit-checks
  every client/mode query offline for budget compliance and term preservation

#### Known transition artifacts / watch items (documented, no code change)
- One-time NEW-badge blip: 7 stories archived by the old code carry
  boilerplated headlines and/or unresolved Google News URLs. Their
  cluster_ids change under the new headline cleaning, so on the first live
  run after this deploy they may re-badge as NEW once. Self-heals the next
  morning; none of the affected stories is risk_watch
- The new HNB excludes (pyramid / administrator / wind up) run BEFORE
  risk_watch classification, like all excludes. Archive grep confirms they
  currently only suppress CBSL administrivia about third-party finance
  companies, but a hypothetical genuine "HNB administrator / wind-up" story
  would be excluded too — keep in mind when editing HNB keywords

#### Replayed 2026-07-07 result (vs the live run that morning)
- Same 74 stories in JSON, but the rendered page now leads with 7 new
  stories; HNB's 17 flat-0.7 CBSL cards became 5 ranked industry cards +
  1 recurring-rate line (1 repeat suppressed, 5 capped, 5 excluded as
  administrivia); MAS shows an honest "No new coverage" line instead of
  cricket junk

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
