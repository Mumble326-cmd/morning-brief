# ─────────────────────────────────────────────────────────────────────────────
# config.py — Morning Brief · The only file you need to edit
# ─────────────────────────────────────────────────────────────────────────────

# ── Settings ──────────────────────────────────────────────────────────────────
WINDOW_DAYS  = 30          # Always fetch 30 days; user filters on the page
MAX_STORIES  = 8           # Max stories per client per mode (pre-filter)
OUTPUT_FILE  = 'index.html'

# ── Clients ───────────────────────────────────────────────────────────────────
# RULE: Every query must force "Sri Lanka" locality.
# RULE: Never use short ambiguous acronyms alone (MAS, MIFL, HNB).
#       Always use full names or append "Sri Lanka" directly.

CLIENTS = [
    {
        'key':        'hnb',
        'label':      'HNB',
        'tag':        'Banking',
        # "HNB" alone matches Croatia's Hrvatska Narodna Banka.
        # "HNB PLC" and "HNB Sri Lanka" are unambiguous.
        'mentions_q': '"HNB PLC" OR "HNB Sri Lanka" OR "Hatton National Bank"',
        'industry_q': (
            '("CBSL" OR "Central Bank of Sri Lanka" OR "Sampath Bank" '
            'OR "Commercial Bank of Ceylon" OR "NDB Bank" OR "Seylan Bank" '
            'OR "Bank of Ceylon" OR "banking sector") "Sri Lanka"'
        ),
    },
    {
        'key':        'hayleys',
        'label':      'Hayleys',
        'tag':        'Conglomerate',
        'mentions_q': '"Hayleys" "Sri Lanka" OR "Hayleys PLC"',
        'industry_q': (
            '("Hayleys Fabric" OR "Hayleys Advantis" OR "Dipped Products" '
            'OR "Haycarb" OR "Hayleys Agriculture" OR "Singer Sri Lanka" '
            'OR "Hayleys Leisure" OR "Hayleys Fentons") "Sri Lanka"'
        ),
    },
    {
        'key':        'mas',
        'label':      'MAS',
        'tag':        'Apparel',
        # "MAS" alone matches hundreds of unrelated things globally.
        # Only use full company names.
        'mentions_q': '"MAS Holdings" OR "MAS Holdings Sri Lanka"',
        'industry_q': (
            '("Brandix" OR "Hirdaramani" OR "apparel exports Sri Lanka" '
            'OR "garment sector Sri Lanka" OR "GSP+ Sri Lanka" OR "JAAF Sri Lanka") '
            '"Sri Lanka"'
        ),
    },
    {
        'key':        'byd',
        'label':      'BYD',
        'tag':        'Auto / EV',
        # BYD is a global brand — must always pair with "Sri Lanka"
        'mentions_q': '"BYD" "Sri Lanka"',
        'industry_q': (
            '("electric vehicle Sri Lanka" OR "EV policy Sri Lanka" '
            'OR "Denza Sri Lanka" OR "MG Sri Lanka" OR "EV charging Sri Lanka" '
            'OR "hybrid vehicle Sri Lanka")'
        ),
    },
    {
        'key':        'mifl',
        'label':      'MIFL',
        'tag':        'Finance',
        # "MIFL" alone matches Mediolanum International Funds (Ireland).
        # Only use the full Sri Lankan company name.
        'mentions_q': '"Mahindra Ideal Finance" OR "MIFL Sri Lanka"',
        'industry_q': (
            '("licensed finance company" OR "leasing company" '
            'OR "People\'s Leasing" OR "Central Finance" '
            'OR "LB Finance" OR "Senkadagala Finance") "Sri Lanka"'
        ),
    },
    {
        'key':        'pcc',
        'label':      'Port City Colombo',
        'tag':        'Development',
        'mentions_q': '"Port City Colombo" OR "Colombo Port City"',
        # CHEC alone matches CHEC projects in Libya, Nigeria, Bangladesh.
        # Must pair CHEC with Sri Lanka, or use "CHEC Port City".
        'industry_q': (
            '"CHEC Port City" OR "CHEC Sri Lanka" '
            'OR "special economic zone Sri Lanka" '
            'OR "Colombo real estate" OR "foreign investment Colombo"'
        ),
    },

    # ── Add more clients here ─────────────────────────────────────────────────
    # Template — copy, fill in, save, push, run Action:
    # {
    #     'key':        'cinnamon',
    #     'label':      'Cinnamon Life',
    #     'tag':        'Hospitality',
    #     'mentions_q': '"Cinnamon Life" "Sri Lanka"',
    #     'industry_q': '("hotel Sri Lanka" OR "tourism Sri Lanka" OR "John Keells") "Sri Lanka"',
    # },
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
