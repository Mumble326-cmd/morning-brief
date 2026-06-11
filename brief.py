#!/usr/bin/env python3
"""
brief.py — Morning Brief generator
Fetches Google News RSS for each client in config.py and writes index.html.

Run locally:  python brief.py
GitHub Actions runs this automatically every weekday morning.
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import html as html_lib
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from config import CLIENTS, CONTACTS, WINDOW_DAYS, MAX_STORIES, OUTPUT_FILE

# ── Constants ─────────────────────────────────────────────────────────────────
SL_TZ = timezone(timedelta(hours=5, minutes=30))

# ── Fetch ─────────────────────────────────────────────────────────────────────

def get_contact(source):
    """Look up journalist contact for a given outlet name."""
    if not source:
        return None
    s = source.lower()
    for key, val in CONTACTS.items():
        if key in s:
            return val
    return None


def fetch_news(query, window_days=None, max_results=None):
    """Fetch Google News RSS for a query, return list of story dicts."""
    window_days  = window_days  or WINDOW_DAYS
    max_results  = max_results  or MAX_STORIES

    q   = urllib.parse.quote(f'({query}) when:{window_days}d')
    url = f'https://news.google.com/rss/search?q={q}&hl=en-LK&gl=LK&ceid=LK:en'
    print(f'  → {url[:90]}...')

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; MorningBrief/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode('utf-8')
    except Exception as e:
        print(f'  ✗ Fetch error: {e}')
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f'  ✗ Parse error: {e}')
        return []

    channel = root.find('channel')
    if channel is None:
        return []

    seen, results = set(), []
    for item in channel.findall('item'):
        link = (item.findtext('link') or '').strip()
        if not link or link in seen:
            continue
        seen.add(link)

        source_el = item.find('source')
        source    = source_el.text.strip() if source_el is not None else ''
        title     = _clean_title(item.findtext('title') or '', source)
        pub       = item.findtext('pubDate') or ''
        snippet   = _clean_html(item.findtext('description') or '')

        results.append({
            'headline': title,
            'url':      link,
            'source':   source,
            'date':     _format_date(pub),
            'snippet':  snippet[:280] if snippet else '',
            'contact':  get_contact(source),
        })
        if len(results) >= max_results:
            break

    print(f'  ✓ {len(results)} result(s)')
    return results


def _clean_title(title, source):
    if source and title.endswith(f' - {source}'):
        title = title[:-(len(source) + 3)]
    return html_lib.unescape(title.strip())


def _clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _format_date(pub_date):
    if not pub_date:
        return 'Date unavailable'
    try:
        dt = parsedate_to_datetime(pub_date).astimezone(SL_TZ)
        return dt.strftime('%d %b %Y · %H:%M SL')
    except Exception:
        return pub_date[:25]


# ── HTML ──────────────────────────────────────────────────────────────────────

def h(s):
    return html_lib.escape(str(s) if s is not None else '')


CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  --ink:#0d0d0d;--paper:#f5f0e8;--cream:#ede8dc;
  --rule:#c8bfae;--rule-soft:#ddd4c2;--accent:#1a1a2e;
  --gold:#c9a84c;--muted:#6b6357;--faint:#8a8275;
}
html,body{background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",sans-serif;font-size:14px;
  line-height:1.6;-webkit-font-smoothing:antialiased;}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
  opacity:.025;z-index:0;
  background-image:radial-gradient(var(--ink) .5px,transparent .5px);
  background-size:4px 4px;}
.shell{position:relative;z-index:1;max-width:880px;margin:0 auto;
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
  min-height:100vh;background:var(--paper);}
.masthead{border-bottom:3px double var(--ink);padding:26px 36px 16px;}
.mk{display:flex;align-items:center;gap:12px;
  font-family:"IBM Plex Mono",monospace;font-size:9.5px;
  letter-spacing:.18em;text-transform:uppercase;color:var(--muted);
  margin-bottom:10px;}
.mk .line{flex:1;height:1px;background:var(--rule);}
h1{font-family:"Playfair Display",serif;font-size:44px;font-weight:900;
  line-height:1;letter-spacing:-.01em;text-align:center;}
h1 .it{font-style:italic;font-weight:600;}
.msub{display:flex;align-items:center;justify-content:center;gap:14px;
  margin-top:12px;padding-top:10px;border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--muted);
  flex-wrap:wrap;}
.msub .dot{color:var(--gold);}
.pages{padding:8px 36px 60px;}
.section{padding:22px 0 8px;border-bottom:1px solid var(--rule-soft);}
.section:last-child{border-bottom:none;}
.sec-head{display:flex;align-items:baseline;gap:14px;margin-bottom:14px;}
.sec-name{font-family:"Playfair Display",serif;font-size:26px;
  font-weight:700;letter-spacing:-.01em;}
.sec-tag{font-family:"IBM Plex Mono",monospace;font-size:9px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--gold);
  background:var(--accent);padding:2px 7px;border-radius:2px;}
.sec-rule{flex:1;height:2px;background:var(--ink);align-self:center;}
.mode-block{margin-bottom:18px;}
.mode-label{font-family:"IBM Plex Mono",monospace;font-size:9px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--faint);
  border-bottom:1px solid var(--rule-soft);padding-bottom:5px;
  margin-bottom:10px;}
.empty{font-family:"IBM Plex Mono",monospace;font-size:11px;
  color:var(--faint);padding:8px 0;}
.story{padding:12px 0;border-top:1px solid var(--rule-soft);}
.story:first-child{border-top:none;}
.story-hl{font-family:"Playfair Display",serif;font-size:17px;
  font-weight:600;line-height:1.3;color:var(--ink);text-decoration:none;
  display:block;}
.story-hl:hover{color:var(--accent);text-decoration:underline;
  text-underline-offset:3px;}
.ext{font-size:11px;color:var(--faint);margin-left:3px;}
.snippet{font-size:13px;color:#2a2a2a;line-height:1.65;margin-top:6px;}
.meta{display:flex;align-items:center;gap:10px;margin-top:8px;
  flex-wrap:wrap;font-family:"IBM Plex Mono",monospace;font-size:9.5px;
  letter-spacing:.05em;color:var(--muted);}
.src{font-weight:600;color:var(--ink);text-transform:uppercase;}
.sep{color:var(--rule);}
.contact{font-family:"IBM Plex Mono",monospace;font-size:9px;
  color:var(--faint);margin-top:4px;}
.contact a{color:var(--faint);text-decoration:none;}
.contact a:hover{color:var(--accent);}
.foot{padding:18px 36px;border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",monospace;font-size:9px;
  letter-spacing:.06em;color:var(--faint);line-height:1.7;}
@media(max-width:600px){
  h1{font-size:32px;}
  .pages,.masthead,.foot{padding-left:18px;padding-right:18px;}
}
"""

FONTS = (
    'https://fonts.googleapis.com/css2?'
    'family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,900;1,400;1,600'
    '&family=IBM+Plex+Mono:wght@400;500;600'
    '&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap'
)


def _stories_html(stories):
    if not stories:
        return f'<p class="empty">No coverage in the last {WINDOW_DAYS} days.</p>'
    out = ''
    for s in stories:
        contact_html = ''
        if s['contact']:
            name, email = s['contact']
            contact_html = (
                f'<p class="contact">{h(name)} &middot; '
                f'<a href="mailto:{h(email)}">{h(email)}</a></p>'
            )
        out += (
            f'<div class="story">'
            f'<a class="story-hl" href="{h(s["url"])}" target="_blank" rel="noopener">'
            f'{h(s["headline"])} <span class="ext">&#8599;</span></a>'
            f'<p class="snippet">{h(s["snippet"])}</p>'
            f'<div class="meta">'
            f'<span class="src">{h(s["source"])}</span>'
            f'<span class="sep">/</span>'
            f'<span>{h(s["date"])}</span>'
            f'</div>'
            f'{contact_html}'
            f'</div>'
        )
    return out


def build_html(all_results, generated_at):
    now_sl   = generated_at.astimezone(SL_TZ)
    dateline = now_sl.strftime('%A, %d %B %Y')
    gen_time = now_sl.strftime('%H:%M SL')

    # Build client names list for masthead
    client_names = ' &middot; '.join(h(c['label']) for c in CLIENTS)

    sections = ''
    for c in CLIENTS:
        k        = c['key']
        m_html   = _stories_html(all_results.get(f'{k}_mentions', []))
        i_html   = _stories_html(all_results.get(f'{k}_industry', []))
        sections += (
            f'<div class="section">'
            f'<div class="sec-head">'
            f'<span class="sec-name">{h(c["label"])}</span>'
            f'<span class="sec-tag">{h(c["tag"])}</span>'
            f'<span class="sec-rule"></span>'
            f'</div>'
            f'<div class="mode-block">'
            f'<p class="mode-label">Mentions</p>{m_html}'
            f'</div>'
            f'<div class="mode-block">'
            f'<p class="mode-label">Industry</p>{i_html}'
            f'</div>'
            f'</div>'
        )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8"/>\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0"/>\n'
        f'<title>The Morning Brief — {dateline}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link href="{FONTS}" rel="stylesheet">\n'
        f'<style>{CSS}</style>\n'
        '</head>\n'
        '<body>\n'
        '<div class="shell">\n'
        '<header class="masthead">\n'
        '  <div class="mk"><span class="line"></span>'
        '<span>Adfactors PR &middot; Colombo</span>'
        '<span class="line"></span></div>\n'
        '  <h1>The Morning <span class="it">Brief</span></h1>\n'
        '  <div class="msub">'
        f'<span>{dateline}</span>'
        '<span class="dot">&bull;</span>'
        f'<span>Generated {gen_time}</span>'
        '<span class="dot">&bull;</span>'
        f'<span>{client_names}</span>'
        '</div>\n'
        '</header>\n'
        f'<div class="pages">{sections}</div>\n'
        '<div class="foot">'
        f'Auto-generated &middot; Google News (Sri Lanka) &middot; '
        f'Last {WINDOW_DAYS} days &middot; Verify before circulating'
        '</div>\n'
        '</div>\n'
        '</body>\n'
        '</html>\n'
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('Morning Brief — starting\n')
    generated_at = datetime.now(timezone.utc)
    all_results  = {}

    for c in CLIENTS:
        print(f'[{c["label"]}] Mentions')
        all_results[f'{c["key"]}_mentions'] = fetch_news(c['mentions_q'])
        print(f'[{c["label"]}] Industry')
        all_results[f'{c["key"]}_industry'] = fetch_news(c['industry_q'])
        print()

    print('Building HTML...')
    page = build_html(all_results, generated_at)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(page)

    print(f'Done — {OUTPUT_FILE} written ({len(page):,} bytes)')
    print(f'Open {OUTPUT_FILE} in a browser to preview.')


if __name__ == '__main__':
    main()
