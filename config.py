# ─────────────────────────────────────────────────────────────────────────────
# config.py — Morning Brief · The only file you need to edit
# ─────────────────────────────────────────────────────────────────────────────

# ── Settings ──────────────────────────────────────────────────────────────────
WINDOW_DAYS  = 30          # Always fetch 30 days; user filters on the page
MAX_STORIES  = 20          # Max stories per client per mode (pre-filter)
OUTPUT_FILE  = 'index.html'

# Per-client per-day card caps for filler-prone categories. The best-scored
# stories survive; the overflow stays in data/latest.json (is_capped: true)
# but never reaches the rendered brief. Mentions and risk are never capped —
# a client's own coverage and negative news must always surface in full.
CATEGORY_CAPS = {
    'industry':     5,
    'market_watch': 3,
}

# ── Global exclude layer ──────────────────────────────────────────────────────
# Terms that mark a story as junk for EVERY client, on top of each client's
# own exclude list in keywords.json. Sports coverage keeps leaking in via
# corporate-named teams ("Bowlers star in LOLC Holdings' five wicket win"),
# so the sports vocabulary lives here once instead of six times.
GLOBAL_EXCLUDE = [
    'cricket',
    'rugby',
    'football',
    'futsal',
    'netball',
    'volleyball',
    'badminton',
    'wicket',
    'bowlers',
    'batsman',
    'batter',
    'innings',
    'run chase',
    'T10',
    'T20',
    'horse racing',
    'horoscope',
    'obituar',           # obituary / obituaries
    'matrimonial',
]

# ── Recurring time-series posts ───────────────────────────────────────────────
# Some outlets publish the same data point as a fresh "story" every day
# (CBSL daily exchange rate, T-bill auction yields, market close). Each entry
# is (series_key, regex tested against the lowercased headline). Stories in
# the same (client, series_key) group are rolled up: the newest becomes a
# one-line "recurring update" in the brief, the rest are suppressed from the
# rendered page (kept in data/latest.json with is_series_repeat: true).
SERIES_PATTERNS = [
    ('cbsl-fx-rate',  r'\b(?:cbsl|central bank)\b.*\b(?:selling|buying)\s+rate\b'),
    ('fx-rate',       r'\b(?:usd|us ?dollar|dollar)\b.*\brs\.?\s*\d'),
    ('tbill-auction', r'\btreasury (?:bill|bond)\b.*\b(?:auction|yields?)\b'),
    ('market-close',  r'\b(?:bourse|asp?i|indices|stock market|cse)\b.*\b(?:closes?|ends?|gains?|dips?|slips?|edges?|in (?:green|red))\b'),
    ('market-close',  r'\bweek ends in (?:green|red)\b'),
    ('fuel-price',    r'\bfuel price (?:revision|update|formula)\b'),
    ('gold-price',    r'\bgold price\b'),
]

# ── Clients ───────────────────────────────────────────────────────────────────
# A client entry needs only three keys: 'key', 'label', 'sector'.
#   key    — short id; MUST match the top-level key in keywords.json
#   label  — display name in the brief
#   sector — shown as the section chip; also the client's industry grouping
#
# All keyword queries (direct_mentions / industry_watch / market_watch /
# risk_watch / exclude) live in keywords.json, NOT here. Adding a client is two
# steps: (1) paste a keywords.json block, (2) add a {key,label,sector} entry
# below. Use new_client.py to scaffold both — `py -3 new_client.py "Name" "Sector"`.
#
# RULE: keep brand queries unambiguous in keywords.json — short acronyms (MAS,
#       MIFL, HNB, BYD) need a "Sri Lanka" query_context or full company names.

CLIENTS = [
    {'key': 'hnb',     'label': 'HNB',               'sector': 'Banking'},
    {'key': 'hayleys', 'label': 'Hayleys',           'sector': 'Conglomerate'},
    {'key': 'mas',     'label': 'MAS',               'sector': 'Apparel'},
    {'key': 'byd',     'label': 'BYD',               'sector': 'Auto / EV'},
    {'key': 'mifl',    'label': 'MIFL',              'sector': 'Finance'},
    {'key': 'pcc',     'label': 'Port City Colombo', 'sector': 'Development'},

    # ── Add more clients here ─────────────────────────────────────────────────
    # {'key': 'cinnamon', 'label': 'Cinnamon Life', 'sector': 'Hospitality'},
]

# ── Direct outlet RSS feeds ───────────────────────────────────────────────────
# Fetched in addition to Google News, which caps results at 100 and misses
# articles some outlets block from indexing. These are all Sri Lankan outlets,
# so items skip the SL-signal gate; an item is kept only when it matches a
# client's direct_mentions or risk_watch keywords.
# Probed 2026-06-12: ft.lk (timeout), dailymirror.lk (no XML feed),
# themorning.lk (404) and colombogazette.com (origin errors) have no usable
# feed — those outlets still arrive via Google News.
DIRECT_FEEDS = [
    {'source': 'EconomyNext',         'url': 'https://economynext.com/feed/'},
    {'source': 'The Island',          'url': 'https://island.lk/feed/'},
    {'source': 'Ada Derana',          'url': 'https://www.adaderana.lk/rss.php'},
    {'source': 'Newswire',            'url': 'https://www.newswire.lk/feed/'},
    {'source': 'Lanka Business News', 'url': 'https://www.lankabusinessnews.com/feed/'},
    {'source': 'Daily News',          'url': 'https://www.dailynews.lk/feed/'},
    {'source': 'LBO',                 'url': 'https://www.lankabusinessonline.com/feed/'},
]

# ── SL relevance signals ──────────────────────────────────────────────────────
# Post-fetch validation: a story is kept only if its headline+snippet
# contains at least one of these. Keep these SPECIFIC to Sri Lanka.
# Do NOT add generic terms like "central bank" or "tamil" — too broad globally.
SL_SIGNALS = {
    'sri lanka',
    'lanka',
    'colombo',
    'lkr',
    'rupee sri',
    'ceylon',
    'cbsl',
    'kandy',
    'galle',
    'jaffna',
    'trincomalee',
    'hatton',
    'negombo',
    '.lk',           # domain suffix in URLs/snippets, e.g. ft.lk, derana.lk
}
