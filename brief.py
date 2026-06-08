#!/usr/bin/env python3
"""
Morning Brief — Daily Client News Scanner
Runs via GitHub Actions daily, publishes result to GitHub Pages as index.html.
Free. No API keys. No AI. No cost.
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import html as html_lib
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ── Sri Lanka timezone ─────────────────────────────────
SL_TZ = timezone(timedelta(hours=5, minutes=30))

# ── Clients ────────────────────────────────────────────
CLIENTS = [
    {
        'key': 'hnb',
        'label': 'HNB',
        'tag': 'Banking',
        'mentions_q': '"HNB" OR "Hatton National Bank"',
        'industry_q': (
            '"CBSL" OR "Central Bank of Sri Lanka" OR "Sampath Bank" OR '
            '"Commercial Bank of Ceylon" OR "NDB Bank" OR "Seylan Bank" OR '
            '"Bank of Ceylon" OR "banking sector Sri Lanka" OR '
            '"bank interest rates" OR "monetary policy Sri Lanka"'
        ),
    },
    {
        'key': 'hayleys',
        'label': 'Hayleys',
        'tag': 'Conglomerate',
        'mentions_q': '"Hayleys" OR "Hayleys PLC"',
        'industry_q': (
            '"Hayleys Fabric" OR "Hayleys Advantis" OR "Dipped Products" OR '
            '"Haycarb" OR "Hayleys Agriculture" OR "Singer Sri Lanka" OR '
            '"Sri Lanka conglomerate"'
        ),
    },
    {
        'key': 'mas',
        'label': 'MAS',
        'tag': 'Apparel',
        'mentions_q': '"MAS Holdings" OR "MAS Intimates" OR "MAS Active"',
        'industry_q': (
            '"Brandix" OR "Hirdaramani" OR "apparel exports Sri Lanka" OR '
            '"garment industry Sri Lanka" OR "GSP+" OR "JAAF" OR '
            '"Sri Lanka manufacturing"'
        ),
    },
    {
        'key': 'byd',
        'label': 'BYD',
        'tag': 'Auto / EV',
        'mentions_q': '"BYD" "Sri Lanka"',
        'industry_q': (
            '"Denza Sri Lanka" OR "electric vehicle Sri Lanka" OR '
            '"EV policy Sri Lanka" OR "EV charging Sri Lanka" OR '
            '"DFSK" OR "MG Sri Lanka" OR "zero emission vehicle"'
        ),
    },
    {
        'key': 'mifl',
        'label': 'MIFL',
        'tag': 'Finance',
        'mentions_q': '"Mahindra Ideal Finance" OR "MIFL"',
        'industry_q': (
            '"licensed finance company Sri Lanka" OR "People\'s Leasing" OR '
            '"Central Finance" OR "LB Finance" OR "leasing Sri Lanka" OR '
            '"CBSL finance companies"'
        ),
    },
    {
        'key': 'pcc',
        'label': 'Port City Colombo',
        'tag': 'Development',
        'mentions_q': '"Port City Colombo" OR "Colombo Port City"',
        'industry_q': (
            '"CHEC" OR "special economic zone Sri Lanka" OR '
            '"Colombo real estate" OR "foreign investment Colombo" OR '
            '"Colombo waterfront" OR "SEZ Sri Lanka"'
        ),
    },
]

# ── Media contacts ──────────────────────────────────────
CONTACTS = {
    'daily mirror':           ('Shabiya Ahlam',           'shabiya.ahlam@gmail.com'),
    'daily ft':               ('Nisthar Cassim',           'nisthar@ft.lk'),
    'ft.lk':                  ('Nisthar Cassim',           'nisthar@ft.lk'),
    'daily news':             ('Dharma Sri',               'dharmassri05@gmail.com'),
    'sunday observer':        ('Lalin Fernandopulle',      'lalinfernandopulle08@gmail.com'),
    'the island':             ('Lynn Ockersz',             'lynnockersz976@gmail.com'),
    'the morning':            ('Madhusha Thevapalkumara',  'madhusha.news@gmail.com'),
    'sunday morning':         ('Madhusha Thevapalkumara',  'madhusha.news@gmail.com'),
    'sunday times':           ('Feizal Samath',            'bt@sundaytimes.wnl.lk'),
    'ceylon today':           ('Ishara',                   'isharaorg@gmail.com'),
    'ada derana':             ('Sisira Kannangara',        'sisira.derana@gmail.com'),
    'economy next':           ('Asantha Sirimanne',        'asanthamail@gmail.com'),
    'economynext':            ('Asantha Sirimanne',        'asanthamail@gmail.com'),
    'lbo':                    ('Ashanthi Ratnasingham',    'ashanthir2@gmail.com'),
    'lanka business online':  ('Ashanthi Ratnasingham',   'ashanthir2@gmail.com'),
    'colombo gazette':        ('Easwaran Rutnam',          'easwaran@live.com'),
    'business cafe':          ('Asanka',                   'asanka@businesscafe.lk'),
    'ceylon business reporter': ('Isuru',                  'cbrwebeditor@gmail.com'),
    'lankapuvath':            ('Chanaka Inoj',              'chanakainoj@yahoo.com'),
    'lanka business news':    ('Milantha',                  'editor@lankabusinessnews.com'),
    'topic.lk':               ('Indrajith',                 'indrajithneth@gmail.com'),
    'newslanka':              ('Claude Gunasekera',          'claudegunasekera@gmail.com'),
    'e&b sri lanka':          ('Nimna',                     'enbsrilanka@gmail.com'),
    'sunday reader':          ('Roy Silva',                  'roymarcussilva@gmail.com'),
}

WINDOW_DAYS = 7
MAX_PER_SECTION = 5

# ── Helpers ─────────────────────────────────────────────

def get_contact(source):
    if not source:
        return None
    s = source.lower()
    for key, val in CONTACTS.items():
        if key in s:
            return val
    return None

def fetch_news(query, window_days=WINDOW_DAYS, max_results=MAX_PER_SECTION):
    q = urllib.parse.quote(f'({query}) when:{window_days}d')
    url = f'https://news.google.com/rss/search?q={q}&hl=en-LK&gl=LK&ceid=LK:en'
    print(f'    GET {url[:80]}...')
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; MorningBrief/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode('utf-8')
    except Exception as e:
        print(f'    ERROR fetching: {e}')
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f'    ERROR parsing XML: {e}')
        return []

    channel = root.find('channel')
    if channel is None:
        return []

    seen = set()
    results = []

    for item in channel.findall('item'):
        link = (item.findtext('link') or '').strip()
        if not link or link in seen:
            continue
        seen.add(link)

        source_el = item.find('source')
        source = source_el.text if source_el is not None else ''
        title  = clean_title(item.findtext('title') or '', source)
        pub    = item.findtext('pubDate') or ''
        snip   = clean_html(item.findtext('description') or '')

        results.append({
            'headline': title,
            'url':      link,
            'source':   source,
            'date':     format_date(pub),
            'snippet':  snip[:280] if snip else '',
            'contact':  get_contact(source),
        })
        if len(results) >= max_results:
            break

    print(f'    {len(results)} result(s)')
    return results

def clean_title(title, source):
    """Google News appends ' - SourceName' to titles; strip it."""
    if source and title.endswith(f' - {source}'):
        title = title[:-(len(source) + 3)]
    return html_lib.unescape(title.strip())

def clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def format_date(pub_date):
    if not pub_date:
        return 'Date unavailable'
    try:
        dt = parsedate_to_datetime(pub_date).astimezone(SL_TZ)
        return dt.strftime('%d %b %Y · %H:%M SL')
    except Exception:
        return pub_date[:25] if pub_date else ''

def h(s):
    return html_lib.escape(str(s) if s is not None else '')

# ── HTML generation ─────────────────────────────────────

CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{--ink:#0d0d0d;--paper:#f5f0e8;--cream:#ede8dc;--rule:#c8bfae;--rule-soft:#ddd4c2;--accent:#1a1a2e;--gold:#c9a84c;--muted:#6b6357;--faint:#8a8275;}
html,body{background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans",sans-serif;font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased;}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.025;z-index:0;background-image:radial-gradient(var(--ink) .5px,transparent .5px);background-size:4px 4px;}
.shell{position:relative;z-index:1;max-width:880px;margin:0 auto;border-left:1px solid var(--rule);border-right:1px solid var(--rule);min-height:100vh;background:var(--paper);}
.masthead{border-bottom:3px double var(--ink);padding:26px 36px 16px;}
.mk{display:flex;align-items:center;gap:12px;font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:10px;}
.mk .line{flex:1;height:1px;background:var(--rule);}
h1{font-family:"Playfair Display",serif;font-size:44px;font-weight:900;line-height:1;letter-spacing:-.01em;text-align:center;}
h1 .it{font-style:italic;font-weight:600;}
.msub{display:flex;align-items:center;justify-content:center;gap:14px;margin-top:12px;padding-top:10px;border-top:1px solid var(--rule);font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);flex-wrap:wrap;}
.msub .dot{color:var(--gold);}
.pages{padding:8px 36px 60px;}
.section{padding:22px 0 8px;border-bottom:1px solid var(--rule-soft);}
.section:last-child{border-bottom:none;}
.sec-head{display:flex;align-items:baseline;gap:14px;margin-bottom:14px;}
.sec-name{font-family:"Playfair Display",serif;font-size:26px;font-weight:700;letter-spacing:-.01em;}
.sec-tag{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);background:var(--accent);padding:2px 7px;border-radius:2px;}
.sec-rule{flex:1;height:2px;background:var(--ink);align-self:center;}
.mode-block{margin-bottom:18px;}
.mode-label{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);border-bottom:1px solid var(--rule-soft);padding-bottom:5px;margin-bottom:10px;}
.sec-empty{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);padding:8px 0;}
.story{padding:12px 0;border-top:1px solid var(--rule-soft);}
.story:first-child{border-top:none;}
.story-headline{font-family:"Playfair Display",serif;font-size:17px;font-weight:600;line-height:1.3;color:var(--ink);text-decoration:none;display:block;}
.story-headline:hover{color:var(--accent);text-decoration:underline;text-underline-offset:3px;}
.ext{font-size:11px;color:var(--faint);margin-left:3px;}
.story-snippet{font-size:13px;color:#2a2a2a;line-height:1.65;margin-top:6px;}
.story-meta{display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap;font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.05em;color:var(--muted);}
.meta-source{font-weight:600;color:var(--ink);text-transform:uppercase;}
.meta-sep{color:var(--rule);}
.story-contact{font-family:"IBM Plex Mono",monospace;font-size:9px;color:var(--faint);margin-top:4px;}
.story-contact a{color:var(--faint);text-decoration:none;}
.story-contact a:hover{color:var(--accent);}
.foot{padding:18px 36px;border-top:1px solid var(--rule);font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.06em;color:var(--faint);line-height:1.7;}
@media(max-width:600px){h1{font-size:32px;}.pages,.masthead,.foot{padding-left:18px;padding-right:18px;}}
"""

def stories_block(stories):
    if not stories:
        return f'<div class="sec-empty">No coverage in the last {WINDOW_DAYS} days.</div>'
    out = ''
    for s in stories:
        contact_html = ''
        if s['contact']:
            name, email = s['contact']
            contact_html = (
                f'<div class="story-contact">{h(name)} &middot; '
                f'<a href="mailto:{h(email)}">{h(email)}</a></div>'
            )
        out += (
            f'<div class="story">'
            f'<a class="story-headline" href="{h(s["url"])}" target="_blank" rel="noopener">'
            f'{h(s["headline"])} <span class="ext">&#8599;</span></a>'
            f'<div class="story-snippet">{h(s["snippet"])}</div>'
            f'<div class="story-meta">'
            f'<span class="meta-source">{h(s["source"])}</span>'
            f'<span class="meta-sep">/</span>'
            f'<span>{h(s["date"])}</span>'
            f'</div>'
            f'{contact_html}'
            f'</div>'
        )
    return out

def build_html(all_results, generated_at):
    now_sl    = generated_at.astimezone(SL_TZ)
    dateline  = now_sl.strftime('%A, %d %B %Y')
    gen_time  = now_sl.strftime('%H:%M SL')

    sections = ''
    for c in CLIENTS:
        k = c['key']
        m_html = stories_block(all_results.get(f'{k}_mentions', []))
        i_html = stories_block(all_results.get(f'{k}_industry', []))
        sections += (
            f'<div class="section">'
            f'<div class="sec-head">'
            f'<span class="sec-name">{h(c["label"])}</span>'
            f'<span class="sec-tag">{h(c["tag"])}</span>'
            f'<span class="sec-rule"></span>'
            f'</div>'
            f'<div class="mode-block">'
            f'<div class="mode-label">Mentions</div>'
            f'{m_html}'
            f'</div>'
            f'<div class="mode-block">'
            f'<div class="mode-label">Industry</div>'
            f'{i_html}'
            f'</div>'
            f'</div>'
        )

    fonts = (
        'https://fonts.googleapis.com/css2?'
        'family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,900;1,400;1,600'
        '&family=IBM+Plex+Mono:wght@400;500;600'
        '&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap'
    )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8"/>\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0"/>\n'
        f'<title>The Morning Brief — {dateline}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link href="{fonts}" rel="stylesheet">\n'
        f'<style>{CSS}</style>\n'
        '</head>\n'
        '<body>\n'
        '<div class="shell">\n'
        '  <header class="masthead">\n'
        '    <div class="mk"><span class="line"></span>'
        '<span>Adfactors PR &middot; Colombo</span>'
        '<span class="line"></span></div>\n'
        '    <h1>The Morning <span class="it">Brief</span></h1>\n'
        '    <div class="msub">'
        f'<span>{dateline}</span>'
        '<span class="dot">&bull;</span>'
        f'<span>Generated {gen_time}</span>'
        '<span class="dot">&bull;</span>'
        '<span>HNB &middot; Hayleys &middot; MAS &middot; BYD &middot; MIFL &middot; Port City</span>'
        '</div>\n'
        '  </header>\n'
        f'  <div class="pages">{sections}</div>\n'
        '  <div class="foot">'
        f'Auto-generated &middot; Google News (Sri Lanka) &middot; Last {WINDOW_DAYS} days &middot; '
        'Verify before circulating'
        '</div>\n'
        '</div>\n'
        '</body>\n'
        '</html>'
    )

# ── Main ────────────────────────────────────────────────

def main():
    print('Morning Brief — starting...')
    generated_at = datetime.now(timezone.utc)
    all_results  = {}

    for c in CLIENTS:
        print(f'\n[{c["label"]}] Mentions')
        all_results[f'{c["key"]}_mentions'] = fetch_news(c['mentions_q'])
        print(f'[{c["label"]}] Industry')
        all_results[f'{c["key"]}_industry'] = fetch_news(c['industry_q'])

    print('\nBuilding HTML...')
    page = build_html(all_results, generated_at)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(page)

    print('Done — index.html written.')

if __name__ == '__main__':
    main()
