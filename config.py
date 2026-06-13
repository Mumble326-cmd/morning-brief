# ─────────────────────────────────────────────────────────────────────────────
# config.py — Morning Brief · The only file you need to edit
# ─────────────────────────────────────────────────────────────────────────────

# ── Settings ──────────────────────────────────────────────────────────────────
WINDOW_DAYS  = 30          # Always fetch 30 days; user filters on the page
MAX_STORIES  = 20          # Max stories per client per mode (pre-filter)
OUTPUT_FILE  = 'index.html'

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
    'lk',            # domain suffix, e.g. ft.lk, derana.lk
}

# ── Media contacts ────────────────────────────────────────────────────────────
# Key = lowercase substring to match against the outlet name.
# Value = (journalist name, email)
CONTACTS = {
    # Print
    'daily mirror':             ('Shabiya Ahlam',           'shabiya.ahlam@gmail.com'),
    'daily ft':                 ('Nisthar Cassim',           'nisthar@ft.lk'),
    'ft.lk':                    ('Nisthar Cassim',           'nisthar@ft.lk'),
    'daily news':               ('Dharma Sri',               'dharmassri05@gmail.com'),
    'sunday observer':          ('Lalin Fernandopulle',      'lalinfernandopulle08@gmail.com'),
    'the island':               ('Lynn Ockersz',             'lynnockersz976@gmail.com'),
    'island.lk':                ('Lynn Ockersz',             'lynnockersz976@gmail.com'),
    'the morning':              ('Madhusha Thevapalkumara',  'madhusha.news@gmail.com'),
    'sunday morning':           ('Madhusha Thevapalkumara',  'madhusha.news@gmail.com'),
    'sunday times':             ('Feizal Samath',            'bt@sundaytimes.wnl.lk'),
    'ceylon today':             ('Ishara',                   'isharaorg@gmail.com'),
    # Online
    'ada derana':               ('Sisira Kannangara',        'sisira.derana@gmail.com'),
    'economy next':             ('Asantha Sirimanne',        'asanthamail@gmail.com'),
    'economynext':              ('Asantha Sirimanne',        'asanthamail@gmail.com'),
    'lbo':                      ('Ashanthi Ratnasingham',    'ashanthir2@gmail.com'),
    'lanka business online':    ('Ashanthi Ratnasingham',    'ashanthir2@gmail.com'),
    'colombo gazette':          ('Easwaran Rutnam',           'easwaran@live.com'),
    'business cafe':            ('Asanka',                   'asanka@businesscafe.lk'),
    'ceylon business reporter': ('Isuru',                    'cbrwebeditor@gmail.com'),
    'lankapuvath':              ('Chanaka Inoj',              'chanakainoj@yahoo.com'),
    'lanka business news':      ('Milantha',                  'editor@lankabusinessnews.com'),
    'mawrata':                  ('Rishar Saleem',             'rahsirlas@gmail.com'),
    'newslanka':                ('Claude Gunasekera',         'claudegunasekera@gmail.com'),
    'topic.lk':                 ('Indrajith',                 'indrajithneth@gmail.com'),
    'e&b sri lanka':            ('Nimna',                     'enbsrilanka@gmail.com'),
    'sunday reader':            ('Roy Silva',                  'roymarcussilva@gmail.com'),
    'eyeview':                  ('Editor',                    'editor.eyeviewsl@gmail.com'),
    # Monthly
    'lmd':                      ('Tania Tanthri',             'tania@lmd.lk'),
    'business today':           ('Kishendra',                 'kishendra@btoptions.com'),
}
