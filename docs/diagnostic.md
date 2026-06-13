# Morning Brief Diagnostic — 2026-06-13

## Executive Summary

A full diagnostic and overhaul of the media-monitoring pipeline. The dedup engine
was rebuilt around token-level Jaccard similarity with a 72-hour window, replacing
a word-overlap test gated to a 2-hour window that was fragmenting single stories
(e.g. the JAECOO J5 HEV launch and the Port City "new investments" wire copy) into
multiple cards. Across the cache that change cut un-merged near-duplicate pairs
from **34 to 10 (−71%)** and total displayed cards from 97 to 87 on the same input.
Classification now checks **risk_watch before direct_mentions** and applies
**exclude terms globally**, so negative stories such as *"US adds BYD to list of
firms with alleged Chinese military ties"* are correctly surfaced as **Risk Watch**
instead of buried as neutral Mentions. Keyword matching for short acronyms (BYD,
CSE, HNB, MAS…) is now word-boundary aware, the direct feeds parse through
`feedparser` with a restored network timeout, manual clips bypass the date-window
filter, and adding a client is now a genuine two-step paste with a startup
consistency check. Overall pipeline health: **good** — the core monitoring logic is
materially more accurate and the architecture is ready for new clients.

## Coverage by Client

Live run 2026-06-13: **126 stories fetched** (Google News + 7 direct feeds + 3 manual
clips) → **87 final cluster cards** after dedup.

| Client | Final cards | Notes |
|--------|------------:|-------|
| HNB | 36 | Only client with healthy `industry` coverage (CBSL/rates/competitor banks) |
| Hayleys | 18 | JAECOO J5 launch now largely consolidated |
| MAS | 4 | Hellmann/MAS logistics-hub coverage consolidated from 4 fragments |
| BYD | 6 | 2 Risk Watch (JKCG surcharge clip + US military-ties story) |
| MIFL | 2 | Both manual clips; auto-fetch finds almost nothing (acronym + small cap) |
| Port City Colombo | 21 | "New investments" wire copy consolidated from 4+ fragments |

Category distribution (after): `mention 58 · industry 10 · risk_watch 2 · market_watch 2 · low_relevance 15`.
(Before: `mention 68 · industry 13 · risk_watch 1 · market_watch 1 · low_relevance 14`.)

**Coverage gap that remains:** only HNB produces `industry` stories. The other five
clients' `industry_watch` queries return ~0 usable results — the terms are long and
highly SL-specific, and Google News has little matching inventory. This is a
keyword-tuning task, not a code bug (see Architecture Recommendations).

## Bugs Found and Fixed

1. **2-hour dedup window fragmented stories.** `are_likely_duplicates` only merged
   near-duplicates published within 2 hours; wire copy and press releases run across
   outlets over days. *Fix:* token Jaccard ≥ 0.5 within a 72-hour window, exact
   normalised headline merges at any gap. Files: `utils.py`.
   *Result:* missed near-dup pairs 34 → 10; JAECOO 5 → 4 cards; Port City "new
   investments" and Commercial Bank → Port City fully consolidated.

2. **`choose_primary_story()` was dead code AND buggy.** It was imported but never
   called, so the cluster primary was simply the newest story and `source_rank` was
   ignored. The function itself updated `best_rank`/`best_ts` in its loop but never
   reassigned `best`, so it always returned the original story regardless. *Fix:*
   rewrote it to pick the highest-ranked outlet (lowest `source_rank`, manual clips
   first, newest as tie-break) and wired it into `cluster_stories`. Files: `utils.py`,
   `brief.py`.

3. **Negative stories misclassified as Mentions.** `classify_story` returned on the
   first `direct_mentions` hit before ever testing `risk_watch`, so *"US adds BYD to
   … Chinese military ties"* was a Mention. *Fix:* risk_watch is now checked before
   direct_mentions. *Result:* that story is now Risk Watch; BYD risk count 1 → 2.

4. **Exclude terms applied only to market/risk fetches.** A "HNB cricket sponsorship"
   fetched via direct_mentions sailed through as a Mention. *Fix:* exclude is now a
   global gate at the top of `classify_story`, demoting any story to `low_relevance`.
   Files: `utils.py`. *Result:* low_relevance 14 → 15.

5. **Short acronyms matched as substrings.** `term.lower() in text` made "BYD" hit
   "ABYDOS", "CSE" hit "SELECTED", "MAS" hit "THOMAS". *Fix:* new `term_matches()`
   uses regex word boundaries for terms ≤ 4 chars, applied in `classify_story` and in
   `match_feed_items_to_clients`. Files: `utils.py`, `brief.py`.

6. **`feedparser.parse(url)` had no timeout → infinite hang.** The first live run with
   feedparser hung indefinitely because feedparser does its own fetch with no timeout
   and one direct feed stalled. *Fix:* fetch bytes via `urllib` with a 25s timeout and
   hand them to `feedparser.parse(bytes)`; added `socket.setdefaulttimeout(30)` as a
   global safety net. Files: `brief.py`.

7. **Manual clips invisible behind the date filter.** The JS `render()` hid any story
   with `ts < cutoff`, so the MIFL CSE-debenture clip (58 days old) never showed even
   on the 30-day view. *Fix:* `data-manual="true"` on manual cards + `isManual ||
   ts >= cutoff` in `render()`. Files: `brief.py`. *Result:* all 3 manual clips
   always visible.

8. **Dead/blank `CLIENTS` config.** `mentions_q`/`industry_q` in `config.py` were
   never read (queries come from `keywords.json`), and `build_html` read
   `client.get("sector")` while entries only had `tag`, so the section sector-chip
   rendered blank. *Fix:* refactored `CLIENTS` to `{key, label, sector}`. Files:
   `config.py`, `brief.py`.

## Peer Research Applied

- **Token Jaccard ≥ 0.5 for title near-duplicate detection** — USPTO patent 10783200
  (news dedup via resemblance graphs); arxiv.org/abs/2410.01141 (Jaccard vs cosine
  thresholds for news titles); NewsCatcher dedup docs (title + content fingerprinting).
  Implemented in `utils._jaccard` / `are_likely_duplicates`.
- **72-hour clustering window** — NewsCatcher / production aggregator practice; wire
  copy reruns across outlets over days. Implemented as `DEDUP_WINDOW_MS`.
- **Robust RSS/Atom parsing via feedparser** — feedparser.readthedocs.io. Handles
  malformed XML, encodings, RSS 1.0/2.0/Atom, naive dates. Implemented in
  `fetch_outlet_feed`.
- **Google News RSS redirect handling** — codewords.ai/blog/google-news-rss,
  ScrapingBee 2026 Google News API guide. Implemented as `resolve_google_url` (see
  Known Limitations for the production caveat).

## Known Limitations

- **Google News redirect resolution returns 0.** `resolve_google_url` follows the
  redirect once with urllib; modern Google News uses a JS/encoded interstitial rather
  than an HTTP 3xx, so the publisher URL is not recoverable this way and stored links
  remain `news.google.com/rss/...` redirects (84 of 87 cards). The function degrades
  gracefully (keeps the redirect, logs nothing fatal). Properly decoding these
  requires base64-decoding the `CBMi...` path or a headless fetch — a follow-up.
- **Jaccard 0.5 vs time-series headlines.** The CBSL daily USD-rate stories
  ("…rate increases to Rs. 337" vs "…to Rs. 342") score Jaccard ≈ 0.8 and will be
  merged into one card even though they are distinct daily figures. The 0.5 threshold
  is the peer standard; lowering it would worsen this. A future content-aware rule
  (detect differing numerics) could exempt them.
- **JAECOO J5 still shows 4 cards, not 1.** Several headlines are only ~0.47 similar
  ("launches all-new" vs "introduces all-new" vs "Print Edition … introduces"), below
  the 0.5 merge threshold. The window fix did the heavy lifting (the 0.5+ variants
  merged); full collapse would require dropping the threshold to 0.45, which the spec
  sets at 0.5 to avoid false merges.
- **Direct feeds contribute little.** Of 87 cards, 84 are Google News; only 3 come
  from direct feeds/manual. The feeds are general-news and rarely name a client
  directly — expected, not a fault. They remain valuable as a backstop for articles
  Google News doesn't index (e.g. Daily Mirror).
- **No RSS for Daily FT, Daily Mirror, The Morning, Colombo Gazette.** These outlets
  expose no usable feed and arrive only via Google News.
- **`industry` coverage is thin for 5 of 6 clients** (keyword tuning, above).

## Architecture Recommendations

1. **Decode the Google News `CBMi...` redirect** (base64 path) to recover publisher
   URLs and domains — improves source ranking, dedup-by-URL, and link durability.
2. **Numeric-aware dedup exemption** so daily rate/index time-series aren't collapsed.
3. **Tune `industry_watch` per client** — current terms are too long/specific; add
   shorter named competitors and sector phrases that Google News actually carries.
4. **Promote `priority_sources` into ranking** — `outlets.json` already ranks domains;
   feed that into executive-summary ordering and cluster-primary tie-breaks.
5. **Per-client RSS where available** (direct outlet feeds beyond the current 7) to
   reduce dependence on Google News' opaque redirects.
6. **Refresh `docs/manual.md` and `docs/keyword-guide.md`** — they still describe a
   `must_include` / `mentions` / `industry` schema that no longer exists in
   `keywords.json` (now `direct_mentions` / `industry_watch` / `market_watch` /
   `risk_watch` / `exclude`).

## References

- USPTO Patent 10783200: news deduplication via resemblance graphs
- arxiv.org/abs/2410.01141: Jaccard vs cosine thresholds for news title dedup
- NewsCatcher API deduplication docs: title + content fingerprinting approach
- ScrapingBee 2026 Google News API guide: Google RSS production limitations
- codewords.ai/blog/google-news-rss: RSS URL structure, rate limits, redirect handling
- feedparser.readthedocs.io: robust RSS/Atom parsing library
- Reuters Institute Digital News Report 2025: aggregator usage trends
- preferred.jp MinHashLSH blog: scalable dedup for large corpora
