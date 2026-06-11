#!/usr/bin/env python3
"""
brief.py — Morning Brief generator
Fetches 30 days of Google News per client, validates Sri Lanka relevance,
applies a hard date cutoff, builds an interactive HTML page.

Run locally:  py brief.py
Auto-runs:    GitHub Actions, weekdays 6:30 AM Sri Lanka time
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import html as html_lib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from config import CLIENTS, CONTACTS, SL_SIGNALS, WINDOW_DAYS, MAX_STORIES, OUTPUT_FILE

SL_TZ = timezone(timedelta(hours=5, minutes=30))

# ── Fetch ──────────────────────────────────────────────────────────────────────

def get_contact(source):
    if not source:
        return None
    s = source.lower()
    for key, val in CONTACTS.items():
        if key in s:
            return val
    return None


def is_sl_relevant(headline, snippet, sl_signals):
    """Return True if headline or snippet contains a Sri Lanka signal."""
    text = (headline + ' ' + snippet).lower()
    return any(sig in text for sig in sl_signals)


def parse_timestamp(pub_date):
    """Return (formatted string, unix epoch ms). Returns (label, 0) on failure."""
    if not pub_date:
        return 'Date unavailable', 0
    try:
        dt = parsedate_to_datetime(pub_date).astimezone(SL_TZ)
        label    = dt.strftime('%d %b %Y · %H:%M SL')
        epoch_ms = int(dt.timestamp() * 1000)
        return label, epoch_ms
    except Exception:
        return pub_date[:25], 0


def clean_title(title, source):
    if source and title.endswith(f' - {source}'):
        title = title[:-(len(source) + 3)]
    return html_lib.unescape(title.strip())


def clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_news(query, client_key, mode, window_days, max_results, sl_signals, cutoff_ms):
    q   = urllib.parse.quote(f'({query}) when:{window_days}d')
    url = f'https://news.google.com/rss/search?q={q}&hl=en-LK&gl=LK&ceid=LK:en'
    sys.stdout.write(f'  → fetching...\n')
    sys.stdout.flush()

    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': 'Mozilla/5.0 (compatible; MorningBrief/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            content = resp.read().decode('utf-8')
    except Exception as e:
        sys.stdout.write(f'  ✗ {e}\n'); sys.stdout.flush()
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        sys.stdout.write(f'  ✗ parse error: {e}\n'); sys.stdout.flush()
        return []

    channel = root.find('channel')
    if channel is None:
        return []

    seen       = set()
    results    = []
    disc_sl    = 0   # discarded: not SL relevant
    disc_old   = 0   # discarded: too old

    for item in channel.findall('item'):
        link = (item.findtext('link') or '').strip()
        if not link or link in seen:
            continue
        seen.add(link)

        source_el = item.find('source')
        source    = (source_el.text or '').strip() if source_el is not None else ''
        headline  = clean_title(item.findtext('title') or '', source)
        snippet   = clean_html(item.findtext('description') or '')[:320]
        pub       = item.findtext('pubDate') or ''

        date_label, epoch_ms = parse_timestamp(pub)

        # ── Hard date cutoff: reject stories older than WINDOW_DAYS ───────────
        if epoch_ms > 0 and epoch_ms < cutoff_ms:
            disc_old += 1
            continue

        # ── SL relevance gate ─────────────────────────────────────────────────
        if not is_sl_relevant(headline, snippet, sl_signals):
            disc_sl += 1
            continue

        contact = get_contact(source)

        results.append({
            'client':   client_key,
            'mode':     mode,
            'headline': headline,
            'url':      link,
            'source':   source,
            'date':     date_label,
            'ts':       epoch_ms,
            'snippet':  snippet,
            'contact':  list(contact) if contact else None,
        })

        if len(results) >= max_results:
            break

    sys.stdout.write(
        f'  ✓ {len(results)} kept · {disc_sl} not-SL · {disc_old} too-old\n'
    )
    sys.stdout.flush()
    return results


# ── HTML ───────────────────────────────────────────────────────────────────────

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
.shell{position:relative;z-index:1;max-width:900px;margin:0 auto;
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
  min-height:100vh;background:var(--paper);}
.masthead{border-bottom:3px double var(--ink);padding:24px 36px 14px;}
.mk{display:flex;align-items:center;gap:12px;font-family:"IBM Plex Mono",monospace;
  font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);
  margin-bottom:10px;}
.mk .line{flex:1;height:1px;background:var(--rule);}
h1{font-family:"Playfair Display",serif;font-size:42px;font-weight:900;
  line-height:1;letter-spacing:-.01em;text-align:center;}
h1 .it{font-style:italic;font-weight:600;}
.msub{display:flex;align-items:center;justify-content:center;gap:12px;
  margin-top:10px;padding-top:10px;border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);flex-wrap:wrap;}
.msub .dot{color:var(--gold);}
.controls{background:var(--cream);border-bottom:1px solid var(--rule);
  padding:10px 36px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;}
.ctrl-group{display:flex;align-items:center;gap:5px;flex-wrap:wrap;}
.ctrl-label{font-family:"IBM Plex Mono",monospace;font-size:9px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-right:4px;}
.ctrl-btn{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.06em;
  background:transparent;border:1px solid var(--rule);color:var(--muted);
  padding:4px 10px;border-radius:2px;cursor:pointer;transition:all .12s;}
.ctrl-btn:hover{border-color:var(--accent);color:var(--ink);}
.ctrl-btn.active{background:var(--accent);color:var(--paper);border-color:var(--accent);}
.ctrl-divider{width:1px;height:20px;background:var(--rule);margin:0 4px;}
.ctrl-search{font-family:"IBM Plex Mono",monospace;font-size:10px;
  background:var(--paper);border:1px solid var(--rule);border-radius:2px;
  padding:4px 10px;color:var(--ink);outline:none;width:160px;}
.ctrl-search:focus{border-color:var(--accent);}
.ctrl-right{margin-left:auto;}
.result-count{font-family:"IBM Plex Mono",monospace;font-size:9px;
  color:var(--faint);letter-spacing:.06em;}
.pages{padding:8px 36px 60px;}
.section{padding:20px 0 8px;border-bottom:1px solid var(--rule-soft);}
.section:last-child{border-bottom:none;}
.sec-head{display:flex;align-items:baseline;gap:14px;margin-bottom:10px;}
.sec-name{font-family:"Playfair Display",serif;font-size:24px;font-weight:700;}
.sec-tag{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--gold);background:var(--accent);
  padding:2px 7px;border-radius:2px;}
.sec-rule{flex:1;height:2px;background:var(--ink);align-self:center;}
.sec-count{font-family:"IBM Plex Mono",monospace;font-size:9px;
  color:var(--faint);text-transform:uppercase;}
.mode-group{margin-bottom:16px;}
.mode-label{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);border-bottom:1px solid var(--rule-soft);
  padding-bottom:5px;margin-bottom:8px;}
.story{padding:11px 0;border-top:1px solid var(--rule-soft);}
.story:first-child{border-top:none;}
.story-hl{font-family:"Playfair Display",serif;font-size:17px;font-weight:600;
  line-height:1.3;color:var(--ink);text-decoration:none;display:block;}
.story-hl:hover{color:var(--accent);text-decoration:underline;text-underline-offset:3px;}
.ext{font-size:11px;color:var(--faint);margin-left:3px;}
.story-snippet{font-size:13px;color:#2a2a2a;line-height:1.65;margin-top:5px;}
.story-meta{display:flex;align-items:center;gap:9px;margin-top:7px;flex-wrap:wrap;
  font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.05em;
  color:var(--muted);}
.src{font-weight:600;color:var(--ink);text-transform:uppercase;}
.sep{color:var(--rule);}
.story-contact{font-family:"IBM Plex Mono",monospace;font-size:9px;color:var(--faint);
  margin-top:3px;}
.story-contact a{color:var(--faint);text-decoration:none;}
.story-contact a:hover{color:var(--accent);}
.no-stories{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);
  padding:8px 0;letter-spacing:.04em;}
.kw-toggle{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);background:transparent;border:none;
  cursor:pointer;padding:0;text-decoration:underline;text-underline-offset:3px;
  margin-bottom:8px;display:block;}
.kw-toggle:hover{color:var(--accent);}
.kw-panel{display:none;margin-bottom:10px;padding:10px 12px;background:var(--cream);
  border:1px solid var(--rule);border-radius:2px;font-family:"IBM Plex Mono",monospace;
  font-size:10px;color:var(--muted);line-height:1.9;}
.kw-panel b{color:var(--ink);}
.kw-hint{color:var(--faint);font-size:9px;margin-top:6px;display:block;}
.foot{padding:16px 36px;border-top:1px solid var(--rule);font-family:"IBM Plex Mono",monospace;
  font-size:9px;letter-spacing:.06em;color:var(--faint);line-height:1.7;}
@media(max-width:600px){
  h1{font-size:30px;}
  .pages,.masthead,.controls,.foot{padding-left:18px;padding-right:18px;}
  .ctrl-search{width:110px;}
}
"""

FONTS = (
    'https://fonts.googleapis.com/css2?'
    'family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,900;1,400;1,600'
    '&family=IBM+Plex+Mono:wght@400;500;600'
    '&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap'
)

JS = r"""
const STORIES   = JSON.parse(document.getElementById('story-data').textContent);
const CLIENTS   = JSON.parse(document.getElementById('client-data').textContent);
const GENERATED = parseInt(document.getElementById('gen-ts').textContent);
const MS = { '1d':86400000,'7d':604800000,'14d':1209600000,'30d':2592000000 };
let state = { win:'7d', client:'all', mode:'all', q:'' };

function setWin(v)    { state.win=v;    syncBtns('win'); }
function setClient(v) { state.client=v; syncBtns('client'); }
function setMode(v)   { state.mode=v;   syncBtns('mode'); }
function setQ(v)      { state.q=v.toLowerCase().trim(); render(); }

function syncBtns(dim) {
  const sel = { win:'[data-win]', client:'[data-cl]', mode:'[data-mode]' }[dim];
  const attr = { win:'data-win', client:'data-cl', mode:'data-mode' }[dim];
  document.querySelectorAll(sel).forEach(b =>
    b.classList.toggle('active', b.getAttribute(attr) === state[dim])
  );
  render();
}

function render() {
  const cutoff = GENERATED - MS[state.win];
  const q = state.q;
  let total = 0;
  CLIENTS.forEach(cl => {
    const sec = document.getElementById('sec-'+cl.key);
    if (!sec) return;
    const secVis = state.client==='all' || state.client===cl.key;
    let secCount = 0;
    ['mentions','industry'].forEach(mode => {
      const grp = sec.querySelector('.mode-group[data-mode="'+mode+'"]');
      if (!grp) return;
      const modeVis = state.mode==='all' || state.mode===mode;
      grp.style.display = (secVis && modeVis) ? '' : 'none';
      if (!secVis || !modeVis) return;
      let n = 0;
      grp.querySelectorAll('.story').forEach(s => {
        const ts   = parseInt(s.dataset.ts) || GENERATED;
        const text = (s.dataset.text||'').toLowerCase();
        const show = ts >= cutoff && (!q || text.includes(q));
        s.style.display = show ? '' : 'none';
        if (show) { n++; secCount++; total++; }
      });
      const empty = grp.querySelector('.no-stories');
      if (empty) empty.style.display = n===0 ? '' : 'none';
    });
    sec.style.display = (secVis && secCount>0) ? '' : 'none';
    const cnt = sec.querySelector('.sec-count');
    if (cnt) cnt.textContent = secCount + (secCount===1?' story':' stories');
  });
  const rc = document.getElementById('result-count');
  if (rc) rc.textContent = total + (total===1?' story':' stories');
}

function toggleKw(id) {
  const p = document.getElementById('kw-'+id);
  if (p) p.style.display = p.style.display==='none' ? 'block' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
  syncBtns('win'); syncBtns('client'); syncBtns('mode');
});
"""


def build_html(all_stories, generated_at):
    now_sl   = generated_at.astimezone(SL_TZ)
    dateline = now_sl.strftime('%A, %d %B %Y')
    gen_time = now_sl.strftime('%H:%M SL')
    gen_ts   = int(generated_at.timestamp() * 1000)

    client_js   = json.dumps([{'key': c['key'], 'label': c['label']} for c in CLIENTS])
    story_json  = json.dumps(all_stories, ensure_ascii=False)
    client_names = ' &middot; '.join(h(c['label']) for c in CLIENTS)

    # Client filter buttons
    client_btns = '<button class="ctrl-btn active" data-cl="all" onclick="setClient(\'all\')">All</button>'
    for c in CLIENTS:
        client_btns += (
            f'<button class="ctrl-btn" data-cl="{h(c["key"])}" '
            f'onclick="setClient(\'{h(c["key"])}\');">{h(c["label"])}</button>'
        )

    sections = ''
    for c in CLIENTS:
        key    = c['key']
        m_list = [s for s in all_stories if s['client']==key and s['mode']=='mentions']
        i_list = [s for s in all_stories if s['client']==key and s['mode']=='industry']

        def stories_html(items):
            if not items:
                return '<p class="no-stories" style="display:none;">No coverage found.</p>'
            out = ''
            for s in items:
                ct = ''
                if s['contact']:
                    n, e = s['contact']
                    ct = (f'<p class="story-contact">{h(n)} &middot; '
                          f'<a href="mailto:{h(e)}">{h(e)}</a></p>')
                search_text = html_lib.escape(
                    (s['headline']+' '+s['snippet']+' '+s['source']).lower()
                )
                out += (
                    f'<div class="story" data-ts="{s["ts"]}" data-text="{search_text}">'
                    f'<a class="story-hl" href="{h(s["url"])}" target="_blank" rel="noopener">'
                    f'{h(s["headline"])} <span class="ext">&#8599;</span></a>'
                    f'<p class="story-snippet">{h(s["snippet"])}</p>'
                    f'<div class="story-meta">'
                    f'<span class="src">{h(s["source"])}</span>'
                    f'<span class="sep">/</span><span>{h(s["date"])}</span>'
                    f'</div>{ct}</div>'
                )
            return out

        kw_html = (
            f'<button class="kw-toggle" onclick="toggleKw(\'{key}\')">'
            f'view search terms ▾</button>'
            f'<div class="kw-panel" id="kw-{key}" style="display:none;">'
            f'<div><b>Mentions:</b> {h(c["mentions_q"])}</div>'
            f'<div><b>Industry:</b> {h(c["industry_q"])}</div>'
            f'<span class="kw-hint">Edit in config.py via Claude Code → push → re-run Action</span>'
            f'</div>'
        )

        sections += (
            f'<div class="section" id="sec-{key}">'
            f'<div class="sec-head">'
            f'<span class="sec-name">{h(c["label"])}</span>'
            f'<span class="sec-tag">{h(c["tag"])}</span>'
            f'<span class="sec-rule"></span>'
            f'<span class="sec-count"></span>'
            f'</div>'
            f'{kw_html}'
            f'<div class="mode-group" data-mode="mentions">'
            f'<p class="mode-label">Mentions</p>{stories_html(m_list)}</div>'
            f'<div class="mode-group" data-mode="industry">'
            f'<p class="mode-label">Industry</p>{stories_html(i_list)}</div>'
            f'</div>'
        )

    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8"/>\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0"/>\n'
        f'<title>The Morning Brief — {dateline}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link href="{FONTS}" rel="stylesheet">\n'
        f'<style>{CSS}</style>\n'
        '</head>\n<body>\n<div class="shell">\n'
        '<header class="masthead">\n'
        '  <div class="mk"><span class="line"></span>'
        '<span>Adfactors PR &middot; Colombo</span><span class="line"></span></div>\n'
        '  <h1>The Morning <span class="it">Brief</span></h1>\n'
        '  <div class="msub">'
        f'<span>{dateline}</span><span class="dot">&bull;</span>'
        f'<span>Generated {gen_time}</span><span class="dot">&bull;</span>'
        f'<span>{client_names}</span></div>\n</header>\n'

        '<div class="controls">\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Window</span>\n'
        '  <button class="ctrl-btn" data-win="1d" onclick="setWin(\'1d\')">1d</button>\n'
        '  <button class="ctrl-btn active" data-win="7d" onclick="setWin(\'7d\')">7d</button>\n'
        '  <button class="ctrl-btn" data-win="14d" onclick="setWin(\'14d\')">14d</button>\n'
        '  <button class="ctrl-btn" data-win="30d" onclick="setWin(\'30d\')">30d</button></div>\n'
        '  <div class="ctrl-divider"></div>\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Client</span>\n'
        f'  {client_btns}</div>\n'
        '  <div class="ctrl-divider"></div>\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Mode</span>\n'
        '  <button class="ctrl-btn active" data-mode="all" onclick="setMode(\'all\')">All</button>\n'
        '  <button class="ctrl-btn" data-mode="mentions" onclick="setMode(\'mentions\')">Mentions</button>\n'
        '  <button class="ctrl-btn" data-mode="industry" onclick="setMode(\'industry\')">Industry</button></div>\n'
        '  <div class="ctrl-divider"></div>\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Search</span>\n'
        '  <input class="ctrl-search" type="text" placeholder="filter stories…" oninput="setQ(this.value)"></div>\n'
        '  <div class="ctrl-right"><span class="result-count" id="result-count"></span></div>\n'
        '</div>\n'

        f'<div class="pages" id="pages">{sections}</div>\n'
        '<div class="foot">Auto-generated &middot; Google News (Sri Lanka) &middot; '
        f'Fetched last {WINDOW_DAYS} days &middot; SL-validated &middot; '
        'Verify before circulating</div>\n'
        '</div>\n'
        f'<script id="story-data" type="application/json">{story_json}</script>\n'
        f'<script id="client-data" type="application/json">{client_js}</script>\n'
        f'<script id="gen-ts" type="application/json">{gen_ts}</script>\n'
        f'<script>{JS}</script>\n'
        '</body>\n</html>\n'
    )


# ── Keywords ──────────────────────────────────────────────────────────────────

def load_keywords():
    import os
    if not os.path.exists('keywords.json'):
        return None
    with open('keywords.json', encoding='utf-8') as f:
        return json.load(f)

def build_query(terms, exclude=None):
    if not terms:
        return ''
    q = ' OR '.join(f'"{t}"' for t in terms)
    if exclude:
        q += ' ' + ' '.join(f'-"{e}"' for e in exclude)
    return q


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('Morning Brief — starting\n')

    generated_at = datetime.now(timezone.utc)
    # Hard cutoff: discard stories published before this timestamp
    cutoff_dt    = generated_at - timedelta(days=WINDOW_DAYS)
    cutoff_ms    = int(cutoff_dt.timestamp() * 1000)

    kw = load_keywords()
    if kw:
        for c in CLIENTS:
            if c['key'] in kw:
                ck       = kw[c['key']]
                excl_m   = ck.get('exclude', [])
                excl_i   = ck.get('industry_exclude', [])
                if 'mentions' in ck:
                    c['mentions_q'] = build_query(ck['mentions'], excl_m)
                if 'industry' in ck:
                    c['industry_q'] = build_query(ck['industry'], excl_i)
        print('Keywords loaded from keywords.json')

    all_stories = []

    for c in CLIENTS:
        print(f'[{c["label"]}] Mentions')
        all_stories.extend(fetch_news(
            c['mentions_q'], c['key'], 'mentions',
            WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms
        ))
        print(f'[{c["label"]}] Industry')
        all_stories.extend(fetch_news(
            c['industry_q'], c['key'], 'industry',
            WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms
        ))
        print()

    print(f'Total stories: {len(all_stories)}')
    print('Building HTML...')
    page = build_html(all_stories, generated_at)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(page)

    print(f'Done — {OUTPUT_FILE} written ({len(page):,} bytes)')
    print(f'Open {OUTPUT_FILE} in a browser to preview locally.')


if __name__ == '__main__':
    main()
