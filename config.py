# ─────────────────────────────────────────────────────────────────
# config.py — Morning Brief configuration
# This is the only file you need to edit.
# ─────────────────────────────────────────────────────────────────

# ── How far back to search (days) ────────────────────────────────
WINDOW_DAYS = 7          # change to 14 or 30 for a wider window
MAX_STORIES  = 5         # max stories per client per mode
OUTPUT_FILE  = 'index.html'

# ── Schedule (for reference — set in .github/workflows/daily-brief.yml)
# Current: Mon–Fri, 1:00 AM UTC = 6:30 AM Sri Lanka time

# ── Clients ──────────────────────────────────────────────────────
# Each client has:
#   key         — unique ID (no spaces)
#   label       — display name
#   tag         — sector badge
#   mentions_q  — search query for direct coverage
#   industry_q  — search query for sector/competitor news

CLIENTS = [
    {
        'key':        'hnb',
        'label':      'HNB',
        'tag':        'Banking',
        'mentions_q': '"HNB" OR "Hatton National Bank"',
        'industry_q': (
            '"CBSL" OR "Central Bank of Sri Lanka" OR "Sampath Bank" OR '
            '"Commercial Bank of Ceylon" OR "NDB Bank" OR "Seylan Bank" OR '
            '"Bank of Ceylon" OR "banking sector Sri Lanka" OR '
            '"bank interest rates" OR "monetary policy Sri Lanka"'
        ),
    },
    {
        'key':        'hayleys',
        'label':      'Hayleys',
        'tag':        'Conglomerate',
        'mentions_q': '"Hayleys" OR "Hayleys PLC"',
        'industry_q': (
            '"Hayleys Fabric" OR "Hayleys Advantis" OR "Dipped Products" OR '
            '"Haycarb" OR "Hayleys Agriculture" OR "Singer Sri Lanka"'
        ),
    },
    {
        'key':        'mas',
        'label':      'MAS',
        'tag':        'Apparel',
        'mentions_q': '"MAS Holdings" OR "MAS Intimates" OR "MAS Active"',
        'industry_q': (
            '"Brandix" OR "Hirdaramani" OR "apparel exports Sri Lanka" OR '
            '"garment industry Sri Lanka" OR "GSP+" OR "JAAF"'
        ),
    },
    {
        'key':        'byd',
        'label':      'BYD',
        'tag':        'Auto / EV',
        'mentions_q': '"BYD" "Sri Lanka"',
        'industry_q': (
            '"Denza Sri Lanka" OR "electric vehicle Sri Lanka" OR '
            '"EV policy Sri Lanka" OR "EV charging" OR "DFSK" OR "MG Sri Lanka"'
        ),
    },
    {
        'key':        'mifl',
        'label':      'MIFL',
        'tag':        'Finance',
        'mentions_q': '"Mahindra Ideal Finance" OR "MIFL"',
        'industry_q': (
            '"licensed finance company Sri Lanka" OR "People\'s Leasing" OR '
            '"Central Finance" OR "LB Finance" OR "leasing Sri Lanka"'
        ),
    },
    {
        'key':        'pcc',
        'label':      'Port City Colombo',
        'tag':        'Development',
        'mentions_q': '"Port City Colombo" OR "Colombo Port City"',
        'industry_q': (
            '"CHEC" OR "special economic zone Sri Lanka" OR '
            '"Colombo real estate" OR "foreign investment Colombo" OR '
            '"Colombo waterfront"'
        ),
    },

    # ── Add more clients below ────────────────────────────────────
    # Copy the block above, change key/label/tag/queries, done.
    #
    # Example:
    # {
    #     'key':        'cinnamon',
    #     'label':      'Cinnamon Life',
    #     'tag':        'Hospitality',
    #     'mentions_q': '"Cinnamon Life" OR "Cinnamon Hotels"',
    #     'industry_q': '"hotel Sri Lanka" OR "tourism Sri Lanka" OR "John Keells"',
    # },
]

# ── Media contacts ────────────────────────────────────────────────
# Key = lowercase string that will be found inside the source/outlet name.
# Value = (journalist name, primary email)
# Used to print contact details under each story in the brief.

CONTACTS = {
    # Print
    'daily mirror':             ('Shabiya Ahlam',           'shabiya.ahlam@gmail.com'),
    'daily ft':                 ('Nisthar Cassim',           'nisthar@ft.lk'),
    'ft.lk':                    ('Nisthar Cassim',           'nisthar@ft.lk'),
    'daily news':               ('Dharma Sri',               'dharmassri05@gmail.com'),
    'sunday observer':          ('Lalin Fernandopulle',      'lalinfernandopulle08@gmail.com'),
    'the island':               ('Lynn Ockersz',             'lynnockersz976@gmail.com'),
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
