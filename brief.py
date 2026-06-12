#!/usr/bin/env python3
"""
brief.py — Morning Brief generator (improved version)
Fetches 30 days of Google News per client, validates Sri Lanka relevance,
applies classification (mention/industry/market_watch/risk_watch),
detects and groups duplicates, ranks sources, and builds an interactive HTML page.

Run locally:  python brief.py
Auto-runs:    GitHub Actions, daily
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
from pathlib import Path

from config import CLIENTS, SL_SIGNALS, WINDOW_DAYS, MAX_STORIES, OUTPUT_FILE
from utils import (
    load_json, save_json, normalize_text, extract_domain, source_rank,
    classify_story, cluster_stories, choose_primary_story,
    save_archive, validate_no_private_contacts
)

SL_TZ = timezone(timedelta(hours=5, minutes=30))

# ── Fetch ──────────────────────────────────────────────────────────────────────

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
    """Remove source suffix from title if present."""
    if source and title.endswith(f' - {source}'):
        title = title[:-(len(source) + 3)]
    return html_lib.unescape(title.strip())

def clean_html(text):
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def is_sl_relevant(headline, snippet, sl_signals):
    """Return True if headline or snippet contains a Sri Lanka signal."""
    text = (headline + ' ' + snippet).lower()
    return any(sig in text for sig in sl_signals)

def fetch_news(query, client_key, window_days, max_results, sl_signals, cutoff_ms):
    """Fetch news from Google News RSS."""
    if not query or not query.strip():
        return []
    
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
    disc_sl    = 0
    disc_old   = 0

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

        # Hard date cutoff
        if epoch_ms > 0 and epoch_ms < cutoff_ms:
            disc_old += 1
            continue

        # SL relevance gate
        if not is_sl_relevant(headline, snippet, sl_signals):
            disc_sl += 1
            continue

        domain = extract_domain(link)

        results.append({
            'client':   client_key,
            'headline': headline,
            'url':      link,
            'source':   source,
            'domain':   domain,
            'date':     date_label,
            'ts':       epoch_ms,
            'snippet':  snippet,
        })

        if len(results) >= max_results:
            break

    sys.stdout.write(f'  ✓ {len(results)} kept · {disc_sl} not-SL · {disc_old} too-old\n')
    sys.stdout.flush()
    return results

# ── Build Query ────────────────────────────────────────────────────────────────

def build_query(terms, context=None):
    """Build Google News query from keyword terms.
    context: if given, ANDed with the OR group — e.g. 'Sri Lanka' turns
    ("BYD" OR "JKCG") into ("BYD" OR "JKCG") "Sri Lanka", keeping the
    RSS feed from being flooded by global results for short ambiguous terms.
    """
    if not terms:
        return ''
    inner = ' OR '.join(f'"{t}"' for t in terms)
    if context:
        return f'({inner}) "{context}"'
    return inner

# ── HTML Rendering ────────────────────────────────────────────────────────────

def h(s):
    """HTML escape."""
    return html_lib.escape(str(s) if s is not None else '')

CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  --ink:#0d0d0d;--paper:#f5f0e8;--cream:#ede8dc;
  --rule:#c8bfae;--rule-soft:#ddd4c2;--accent:#1a1a2e;
  --gold:#c9a84c;--muted:#6b6357;--faint:#8a8275;
  --category-mention:#2d5016;--category-industry:#4a5859;
  --category-market:#a67c52;--category-risk:#8b0000;
  --category-lowrel:#bfb3a0;
}
html,body{background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",sans-serif;font-size:14px;
  line-height:1.6;-webkit-font-smoothing:antialiased;}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
  opacity:.025;z-index:0;
  background-image:radial-gradient(var(--ink) .5px,transparent .5px);
  background-size:4px 4px;}
.shell{position:relative;z-index:1;max-width:920px;margin:0 auto;
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
.pages{padding:20px 0 60px;}
.section{padding:20px 0;}
.sec-head{display:flex;align-items:baseline;gap:14px;margin-bottom:12px;}
.sec-name{font-family:"Playfair Display",serif;font-size:26px;font-weight:700;}
.sec-tag{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--gold);background:var(--accent);
  padding:2px 7px;border-radius:2px;}
.sec-rule{flex:1;height:2px;background:var(--ink);align-self:center;}
.sec-count{font-family:"IBM Plex Mono",monospace;font-size:9px;
  color:var(--faint);text-transform:uppercase;}
.story{padding:12px 0;border-bottom:1px solid var(--rule-soft);}
.story-hl{font-family:"Playfair Display",serif;font-size:17px;font-weight:600;
  line-height:1.3;color:var(--ink);text-decoration:none;display:block;}
.story-hl:hover{color:var(--accent);text-decoration:underline;text-underline-offset:3px;}
.ext{font-size:11px;color:var(--faint);margin-left:3px;}
.story-snippet{font-size:13px;color:#2a2a2a;line-height:1.65;margin-top:6px;}
.story-meta{display:flex;align-items:center;gap:9px;margin-top:8px;flex-wrap:wrap;
  font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.05em;
  color:var(--muted);}
.src{font-weight:600;color:var(--ink);text-transform:uppercase;}
.sep{color:var(--rule);}
.story-tags{display:flex;align-items:center;gap:6px;margin-top:6px;flex-wrap:wrap;}
.story-tag{font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.08em;
  text-transform:uppercase;padding:2px 6px;border-radius:2px;font-weight:600;
  display:inline-block;}
.tag-mention{background:var(--category-mention);color:var(--paper);}
.tag-industry{background:var(--category-industry);color:var(--paper);}
.tag-market{background:var(--category-market);color:var(--paper);}
.tag-risk{background:var(--category-risk);color:var(--paper);}
.tag-lowrel{background:var(--category-lowrel);color:var(--ink);}
.also-covered{font-family:"IBM Plex Mono",monospace;font-size:9px;color:var(--faint);
  margin-top:6px;padding:6px 8px;background:var(--cream);border-left:2px solid var(--gold);}
.also-covered strong{color:var(--muted);}
.no-stories{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);
  padding:12px 0;letter-spacing:.04em;}
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

STUDIO_CSS = """
/* ── Keyword Studio ─────────────────────────────────────────────── */
.studio-overlay{position:fixed;inset:0;z-index:200;display:flex;justify-content:flex-end;
  background:rgba(13,13,13,.5);backdrop-filter:blur(2px);}
.studio-overlay.hidden{display:none;}
.studio-panel{width:min(700px,100vw);height:100vh;background:var(--paper);
  border-left:2px solid var(--ink);display:flex;flex-direction:column;overflow:hidden;}
.studio-head{display:flex;align-items:center;gap:12px;padding:18px 28px 14px;
  border-bottom:3px double var(--ink);flex-shrink:0;}
.studio-head h2{font-family:'Playfair Display',serif;font-size:20px;font-weight:700;flex:1;}
.studio-head-sub{font-family:'IBM Plex Mono',monospace;font-size:9px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}
.studio-close{font-family:'IBM Plex Mono',monospace;font-size:13px;line-height:1;
  background:transparent;border:1px solid var(--rule);color:var(--muted);
  width:28px;height:28px;border-radius:2px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.studio-close:hover{background:var(--accent);color:var(--paper);border-color:var(--accent);}
.studio-body{flex:1;overflow-y:auto;padding:0 28px 100px;}
.studio-section{padding:18px 0;border-bottom:1px solid var(--rule-soft);}
.studio-section:last-child{border-bottom:none;}
.studio-section-title{font-family:'IBM Plex Mono',monospace;font-size:9px;
  letter-spacing:.15em;text-transform:uppercase;color:var(--faint);margin-bottom:12px;}

/* Coverage Health */
.health-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:8px;}
.health-card{padding:10px 12px;border-radius:2px;border:1px solid var(--rule);
  font-family:'IBM Plex Mono',monospace;}
.health-card.zero{border-color:var(--category-risk);background:rgba(139,0,0,.05);}
.health-card.ok{border-color:var(--category-mention);background:rgba(45,80,22,.04);}
.health-card-name{font-family:'Playfair Display',serif;font-size:14px;font-weight:700;
  margin-bottom:3px;}
.health-card-count{font-size:9px;letter-spacing:.06em;color:var(--faint);}
.health-card.zero .health-card-count{color:var(--category-risk);font-weight:600;}
.health-card.ok .health-card-count{color:var(--category-mention);}
.health-fallbacks{margin-top:8px;}
.health-fb-label{font-size:8px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--faint);margin-bottom:4px;}
.fallback-chip{display:inline-block;font-family:'IBM Plex Mono',monospace;font-size:8px;
  background:var(--cream);border:1px solid var(--rule-soft);
  padding:2px 7px;border-radius:2px;cursor:pointer;margin:2px 2px 0 0;transition:all .12s;}
.fallback-chip:hover{border-color:var(--accent);background:var(--accent);color:var(--paper);}

/* Client keyword editors */
.studio-client{padding:14px 0;border-bottom:1px solid var(--rule-soft);}
.studio-client:last-child{border-bottom:none;}
.studio-cl-head{display:flex;align-items:center;gap:10px;margin-bottom:0;cursor:pointer;
  user-select:none;}
.studio-cl-name{font-family:'Playfair Display',serif;font-size:17px;font-weight:700;}
.studio-cl-sector{font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--gold);background:var(--accent);
  padding:2px 6px;border-radius:2px;}
.studio-cl-toggle{font-family:'IBM Plex Mono',monospace;font-size:9px;
  color:var(--faint);margin-left:auto;}
.studio-cl-body{display:none;margin-top:12px;}
.studio-cl-body.open{display:block;}

.ks-mode{margin-bottom:11px;}
.ks-mode-label{display:flex;align-items:center;gap:7px;
  font-family:'IBM Plex Mono',monospace;font-size:8px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:6px;}
.ks-mode-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.ks-dot-mention{background:var(--category-mention);}
.ks-dot-industry{background:var(--category-industry);}
.ks-dot-market{background:var(--category-market);}
.ks-dot-risk{background:var(--category-risk);}
.ks-dot-exclude{background:var(--faint);}
.ks-tags{display:flex;flex-wrap:wrap;gap:5px;align-items:center;}
.ks-tag{display:inline-flex;align-items:center;gap:4px;
  font-family:'IBM Plex Mono',monospace;font-size:9.5px;
  background:var(--cream);border:1px solid var(--rule);
  padding:3px 8px;border-radius:2px;color:var(--ink);}
.ks-rm{cursor:pointer;color:var(--faint);font-size:11px;font-weight:600;padding:0 1px;}
.ks-rm:hover{color:var(--category-risk);}
.ks-add{font-family:'IBM Plex Mono',monospace;font-size:9.5px;
  background:transparent;border:1px dashed var(--rule);
  padding:3px 8px;border-radius:2px;color:var(--muted);outline:none;min-width:130px;}
.ks-add::placeholder{color:var(--faint);}
.ks-add:focus{border-style:solid;border-color:var(--accent);color:var(--ink);}

/* Manual clip badge in brief */
.tag-manual{background:var(--gold);color:var(--accent);}
.story-manual-reason{font-family:'IBM Plex Mono',monospace;font-size:9px;
  color:var(--muted);margin-top:5px;padding:5px 8px;
  border-left:2px solid var(--gold);background:var(--cream);font-style:italic;}

/* ── Clippings panel ──────────────────────────────────── */
.clip-form{display:grid;gap:7px;margin-bottom:14px;}
.clip-row{display:flex;gap:6px;align-items:flex-start;}
.clip-label{font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--faint);width:72px;flex-shrink:0;padding-top:5px;}
.clip-input,.clip-select{font-family:'IBM Plex Mono',monospace;font-size:10px;flex:1;
  background:var(--paper);border:1px solid var(--rule);border-radius:2px;
  padding:4px 8px;color:var(--ink);outline:none;}
.clip-input:focus,.clip-select:focus{border-color:var(--accent);}
.clip-input.url{font-size:9px;}
.clip-textarea{font-family:'IBM Plex Mono',monospace;font-size:10px;flex:1;
  background:var(--paper);border:1px solid var(--rule);border-radius:2px;
  padding:4px 8px;color:var(--ink);outline:none;resize:vertical;min-height:48px;}
.clip-textarea:focus{border-color:var(--accent);}
.clip-fetch-btn{font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.08em;
  text-transform:uppercase;border:1px solid var(--rule);background:transparent;
  color:var(--muted);padding:4px 9px;border-radius:2px;cursor:pointer;white-space:nowrap;flex-shrink:0;}
.clip-fetch-btn:hover{border-color:var(--accent);color:var(--ink);}
.clip-fetch-status{font-family:'IBM Plex Mono',monospace;font-size:8.5px;
  color:var(--muted);min-height:1.4em;}
.clip-add-btn{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.08em;
  text-transform:uppercase;background:var(--category-mention);color:var(--paper);
  border:1px solid var(--category-mention);padding:6px 14px;border-radius:2px;
  cursor:pointer;width:100%;margin-top:2px;}
.clip-add-btn:hover{opacity:.85;}
.clip-list{display:flex;flex-direction:column;gap:7px;margin-top:4px;}
.clip-item{padding:9px 10px;background:var(--cream);border:1px solid var(--rule);
  border-left:3px solid var(--gold);border-radius:2px;}
.clip-item-hl{font-family:'Playfair Display',serif;font-size:13px;font-weight:600;
  line-height:1.3;margin-bottom:3px;}
.clip-item-meta{font-family:'IBM Plex Mono',monospace;font-size:8px;
  color:var(--faint);display:flex;gap:8px;flex-wrap:wrap;margin-bottom:3px;}
.clip-item-reason{font-family:'IBM Plex Mono',monospace;font-size:9px;
  color:var(--muted);font-style:italic;margin-bottom:4px;}
.clip-item-rm{font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--faint);cursor:pointer;background:none;
  border:none;padding:0;text-decoration:underline;}
.clip-item-rm:hover{color:var(--category-risk);}
.clip-empty{font-family:'IBM Plex Mono',monospace;font-size:9px;color:var(--faint);
  padding:8px 0;text-align:center;}
.clip-dl-row{margin-top:10px;display:flex;gap:8px;align-items:center;}

/* Studio footer */
.studio-foot{position:sticky;bottom:0;flex-shrink:0;
  background:var(--cream);border-top:1px solid var(--rule);
  padding:11px 28px;display:flex;align-items:center;gap:10px;}
.ks-status{font-family:'IBM Plex Mono',monospace;font-size:9px;
  letter-spacing:.05em;color:var(--faint);flex:1;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
.ks-status.ok{color:var(--category-mention);}
.ks-status.warn{color:var(--category-market);}
.ks-btn{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.08em;
  text-transform:uppercase;border:1px solid var(--rule);background:transparent;
  color:var(--muted);padding:5px 12px;border-radius:2px;cursor:pointer;transition:all .14s;
  white-space:nowrap;}
.ks-btn:hover{border-color:var(--accent);color:var(--ink);}
.ks-btn.primary{background:var(--accent);color:var(--paper);border-color:var(--accent);}
.ks-btn.primary:hover{opacity:.85;}
"""

JS = r"""
const STORIES = JSON.parse(document.getElementById('story-data').textContent);
const CLIENTS = JSON.parse(document.getElementById('client-data').textContent);
const GENERATED = parseInt(document.getElementById('gen-ts').textContent);
const MS = { '1d':86400000,'7d':604800000,'14d':1209600000,'30d':2592000000 };
let state = { win:'7d', client:'all', category:'all', q:'', showLowRel:false };

function setWin(v)      { state.win=v;       syncBtns('win'); }
function setClient(v)   { state.client=v;    syncBtns('client'); }
function setCategory(v) { state.category=v;  syncBtns('category'); }
function setQ(v)        { state.q=v.toLowerCase().trim(); render(); }

function toggleLowRel() {
  state.showLowRel = !state.showLowRel;
  const btn = document.getElementById('lowrel-btn');
  if (btn) btn.classList.toggle('active', state.showLowRel);
  render();
}

function syncBtns(dim) {
  const sel = { win:'[data-win]', client:'[data-cl]', category:'[data-cat]' }[dim];
  const attr = { win:'data-win', client:'data-cl', category:'data-cat' }[dim];
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
    sec.querySelectorAll('.story').forEach(s => {
      const ts = parseInt(s.dataset.ts) || GENERATED;
      const text = (s.dataset.text||'').toLowerCase();
      const cat = s.dataset.cat || 'mention';
      const catVis = state.category==='all' || state.category===cat;
      const lowOk = cat !== 'low_relevance' || state.showLowRel;
      const show = ts >= cutoff && secVis && catVis && lowOk && (!q || text.includes(q));
      s.style.display = show ? '' : 'none';
      if (show) { secCount++; total++; }
    });
    sec.style.display = (secVis && secCount>0) ? '' : 'none';
    const cnt = sec.querySelector('.sec-count');
    if (cnt) cnt.textContent = secCount + (secCount===1?' story':' stories');
  });
  const rc = document.getElementById('result-count');
  if (rc) rc.textContent = total + (total===1?' story':' stories');
}

document.addEventListener('DOMContentLoaded', () => {
  syncBtns('win'); syncBtns('client'); syncBtns('category');
});
"""

STUDIO_JS = r"""
/* ── Keyword Studio ─────────────────────────────────────────────── */
const KW_RAW = JSON.parse(document.getElementById('kw-data').textContent);

const FALLBACK_SUGGESTIONS = {
  byd: {
    direct_mentions: ['JKCG Auto Sri Lanka','John Keells CG Auto','BYD Lanka dealer','BYD electric Sri Lanka'],
    industry_watch:  ['vehicle import policy Sri Lanka','EV tax Sri Lanka','electric car market Sri Lanka','motor vehicle permit Sri Lanka'],
  },
  mifl: {
    direct_mentions: ['Ideal Finance Sri Lanka','Mahindra Finance Sri Lanka','Mahindra leasing Lanka','Ideal Finance Limited'],
    industry_watch:  ['hire purchase Sri Lanka','micro finance Sri Lanka','NBFI regulation Sri Lanka','vehicle leasing Sri Lanka'],
  },
};

let KW = deepClone(KW_RAW);

function deepClone(o){ return JSON.parse(JSON.stringify(o)); }

function openStudio() {
  KW    = deepClone(KW_RAW);
  CLIPS = deepClone(CLIPS_RAW);
  document.getElementById('studio-overlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  renderHealth();
  renderClients();
  initClipClientSelect();
  renderClips();
  setKsStatus('Keywords loaded · edit then download to apply', '');
}

function closeStudio() {
  document.getElementById('studio-overlay').classList.add('hidden');
  document.body.style.overflow = '';
}

/* Coverage Health */
function clientCounts() {
  const c = {};
  CLIENTS.forEach(cl => { c[cl.key] = 0; });
  STORIES.forEach(s => { if (c.hasOwnProperty(s.client)) c[s.client]++; });
  return c;
}

function renderHealth() {
  const counts = clientCounts();
  const grid = document.getElementById('ks-health-grid');
  grid.innerHTML = '';
  const zeroes = CLIENTS.filter(cl => (counts[cl.key]||0) === 0);
  const haves  = CLIENTS.filter(cl => (counts[cl.key]||0) > 0);
  [...zeroes, ...haves].forEach(cl => {
    const n = counts[cl.key] || 0;
    const card = document.createElement('div');
    card.className = 'health-card ' + (n === 0 ? 'zero' : 'ok');
    let fbHtml = '';
    if (n === 0 && FALLBACK_SUGGESTIONS[cl.key]) {
      const fb = FALLBACK_SUGGESTIONS[cl.key];
      const chips = [
        ...(fb.direct_mentions||[]).map(t => ({t, cat:'direct_mentions'})),
        ...(fb.industry_watch||[]).map(t => ({t, cat:'industry_watch'})),
      ].map(({t, cat}) =>
        `<span class="fallback-chip" title="Add to ${cat.replace(/_/g,' ')}"
          onclick="addFallback('${jsesc(cl.key)}','${jsesc(cat)}','${jsesc(t)}')">&plus; ${htmlesc(t)}</span>`
      ).join('');
      fbHtml = `<div class="health-fallbacks"><div class="health-fb-label">Suggested fallbacks</div>${chips}</div>`;
    }
    card.innerHTML =
      `<div class="health-card-name">${htmlesc(cl.label)}</div>` +
      `<div class="health-card-count">${n===0 ? '⚠ No coverage' : n+' '+(n===1?'story':'stories')}</div>` +
      fbHtml;
    grid.appendChild(card);
  });
}

function addFallback(clientKey, category, term) {
  if (!KW[clientKey]) return;
  if (!KW[clientKey][category]) KW[clientKey][category] = [];
  if (!KW[clientKey][category].includes(term)) {
    KW[clientKey][category].push(term);
    setKsStatus('Added "' + term + '" — download to apply', 'ok');
    renderClients();
    expandClient(clientKey);
  }
}

/* Client keyword editors */
const MODES = [
  {key:'direct_mentions', label:'Mentions',    dot:'ks-dot-mention'},
  {key:'industry_watch',  label:'Industry',    dot:'ks-dot-industry'},
  {key:'market_watch',    label:'Market Watch',dot:'ks-dot-market'},
  {key:'risk_watch',      label:'Risk Watch',  dot:'ks-dot-risk'},
  {key:'exclude',         label:'Exclusions',  dot:'ks-dot-exclude'},
];

function renderClients() {
  const counts = clientCounts();
  const container = document.getElementById('ks-clients');
  const openStates = {};
  container.querySelectorAll('.studio-cl-body.open').forEach(el => {
    openStates[el.dataset.client] = true;
  });
  container.innerHTML = '';
  CLIENTS.forEach(cl => {
    const data = KW[cl.key] || {};
    const isOpen = !!openStates[cl.key];
    const div = document.createElement('div');
    div.className = 'studio-client';
    const modesHtml = MODES.map(m => {
      const terms = data[m.key] || [];
      const tags = terms.map((t, i) =>
        `<span class="ks-tag">${htmlesc(t)}<span class="ks-rm"
          onclick="removeTerm('${jsesc(cl.key)}','${jsesc(m.key)}',${i})">&#x2715;</span></span>`
      ).join('');
      return `<div class="ks-mode">
        <div class="ks-mode-label"><span class="ks-mode-dot ${m.dot}"></span>${m.label}</div>
        <div class="ks-tags" id="kst-${jsesc(cl.key)}-${m.key}">
          ${tags}
          <input class="ks-add" id="ksadd-${jsesc(cl.key)}-${m.key}"
            placeholder="+ add term, press Enter"
            data-client="${jsesc(cl.key)}" data-mode="${jsesc(m.key)}">
        </div>
      </div>`;
    }).join('');
    div.innerHTML =
      `<div class="studio-cl-head" onclick="toggleClient('${jsesc(cl.key)}')">
        <span class="studio-cl-name">${htmlesc(cl.label)}</span>
        <span class="studio-cl-sector">${htmlesc(data.sector||'')}</span>
        <span class="studio-cl-toggle" id="ks-tog-${jsesc(cl.key)}">${isOpen?'▾ collapse':'▸ expand'}</span>
      </div>
      <div class="studio-cl-body${isOpen?' open':''}" data-client="${jsesc(cl.key)}" id="ks-body-${jsesc(cl.key)}">${modesHtml}</div>`;
    container.appendChild(div);
  });
  container.querySelectorAll('.ks-add').forEach(inp => {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        const val = inp.value.trim().replace(/^,+|,+$/g,'');
        if (val) {
          addTerm(inp.dataset.client, inp.dataset.mode, val);
          inp.value = '';
        }
      }
    });
  });
}

function toggleClient(key) {
  const body = document.getElementById('ks-body-' + key);
  const tog  = document.getElementById('ks-tog-'  + key);
  if (!body) return;
  const open = body.classList.toggle('open');
  if (tog) tog.textContent = open ? '▾ collapse' : '▸ expand';
}

function expandClient(key) {
  const body = document.getElementById('ks-body-' + key);
  const tog  = document.getElementById('ks-tog-'  + key);
  if (body && !body.classList.contains('open')) {
    body.classList.add('open');
    if (tog) tog.textContent = '▾ collapse';
  }
}

function addTerm(clientKey, mode, val) {
  if (!KW[clientKey]) KW[clientKey] = {};
  if (!KW[clientKey][mode]) KW[clientKey][mode] = [];
  if (!KW[clientKey][mode].includes(val)) {
    KW[clientKey][mode].push(val);
    setKsStatus('Added "' + val + '" — download to apply', 'ok');
    renderClients();
    expandClient(clientKey);
  }
}

function removeTerm(clientKey, mode, idx) {
  if (KW[clientKey] && KW[clientKey][mode]) {
    const removed = KW[clientKey][mode].splice(idx, 1)[0];
    setKsStatus('Removed "' + removed + '" — download to apply', 'warn');
    renderClients();
    expandClient(clientKey);
  }
}

function downloadKW() {
  const blob = new Blob([JSON.stringify(KW, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'keywords.json';
  a.click();
  setKsStatus('Downloaded keywords.json — replace the file and re-run brief.py', 'ok');
}

function setKsStatus(msg, cls) {
  const el = document.getElementById('ks-status');
  if (!el) return;
  el.textContent = msg;
  el.className = 'ks-status' + (cls ? ' '+cls : '');
}

function htmlesc(s) {
  return String(s==null?'':s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function jsesc(s) {
  return String(s==null?'':s).replace(/'/g,"\\'").replace(/\\/g,'\\\\');
}

/* ── Manual Clippings ──────────────────────────────────────────── */
const CLIPS_RAW = JSON.parse(document.getElementById('clips-data').textContent);
let CLIPS = deepClone(CLIPS_RAW);

function initClipClientSelect() {
  const sel = document.getElementById('clip-client');
  if (!sel) return;
  sel.innerHTML = '<option value="">— select client —</option>' +
    CLIENTS.map(c => `<option value="${htmlesc(c.key)}">${htmlesc(c.label)}</option>`).join('');
}

function renderClips() {
  const list = document.getElementById('clip-list');
  if (!list) return;
  const arts = CLIPS.articles || [];
  if (!arts.length) {
    list.innerHTML = '<div class="clip-empty">No manual clippings yet — paste a URL above to add one.</div>';
    return;
  }
  list.innerHTML = arts.map((a, i) =>
    `<div class="clip-item">
      <div class="clip-item-hl">${htmlesc(a.headline)}</div>
      <div class="clip-item-meta">
        <span>${htmlesc(a.source||'')}</span>
        <span>${htmlesc(a.date||'')}</span>
        <span>${htmlesc(a.client_label||a.client||'')}</span>
        <span>${htmlesc((a.category||'').replace(/_/g,' '))}</span>
      </div>
      ${a.reason ? `<div class="clip-item-reason">${htmlesc(a.reason)}</div>` : ''}
      <button class="clip-item-rm" onclick="removeClip(${i})">remove</button>
    </div>`
  ).join('');
}

function removeClip(i) {
  CLIPS.articles.splice(i, 1);
  renderClips();
  setKsStatus('Clipping removed — download to apply', 'warn');
}

async function fetchClipMeta() {
  const urlVal = document.getElementById('clip-url').value.trim();
  if (!urlVal) return;
  const st = document.getElementById('clip-fetch-status');
  st.textContent = 'Fetching page details…';
  try {
    const proxy = 'https://api.allorigins.win/get?url=' + encodeURIComponent(urlVal);
    const resp = await fetch(proxy, {signal: AbortSignal.timeout(9000)});
    const data = await resp.json();
    const raw  = data.contents || '';
    const doc  = new DOMParser().parseFromString(raw, 'text/html');
    const og   = sel => { const el = doc.querySelector(sel); return el ? (el.getAttribute('content')||'') : ''; };
    const title   = og('meta[property="og:title"]') || doc.title || '';
    const siteName= og('meta[property="og:site_name"]') || og('meta[name="publisher"]') || '';
    const desc    = og('meta[property="og:description"]') || og('meta[name="description"]') || '';
    const pubDate = og('meta[property="article:published_time"]') || og('meta[name="article:published_time"]') || '';
    if (title) document.getElementById('clip-headline').value =
      title.replace(/\s[-|]\s[^-|]+$/, '').trim();
    if (siteName) document.getElementById('clip-source').value = siteName;
    if (desc)  document.getElementById('clip-snippet').value  = desc.slice(0,280);
    if (pubDate) {
      try {
        const d = new Date(pubDate);
        document.getElementById('clip-date').value =
          d.toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});
      } catch(e){}
    }
    st.textContent = title ? '✓ Details fetched — review and adjust if needed' :
      '⚠ Could not extract details — fill in manually';
  } catch(e) {
    st.textContent = '⚠ Auto-fill failed (CORS or timeout) — fill in manually';
  }
}

function addClip() {
  const g   = id => document.getElementById(id).value.trim();
  const url = g('clip-url'), headline = g('clip-headline');
  const client = g('clip-client'), category = g('clip-category');
  if (!url || !headline || !client || !category) {
    setKsStatus('URL, headline, client and category are required', 'err'); return;
  }
  const clientLabel = (CLIENTS.find(c => c.key === client)||{}).label || client;
  const now = new Date();
  let domain = '';
  try { domain = new URL(url).hostname; } catch(e){}
  if (!CLIPS.articles) CLIPS.articles = [];
  CLIPS.articles.push({
    id: 'manual_' + now.getTime(),
    url, headline,
    source:   g('clip-source')  || 'Unknown',
    date:     g('clip-date')    || now.toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'}),
    ts:       now.getTime(),
    snippet:  g('clip-snippet'),
    client,   client_label: clientLabel,
    category, reason: g('clip-reason'),
    domain,   added_at: now.toISOString().slice(0,10)
  });
  ['clip-url','clip-headline','clip-source','clip-snippet','clip-reason'].forEach(id =>
    { document.getElementById(id).value = ''; }
  );
  document.getElementById('clip-date').value = '';
  document.getElementById('clip-fetch-status').textContent = '';
  renderClips();
  setKsStatus('Clipping added — download manual_articles.json to apply', 'ok');
}

function downloadClips() {
  const out = {
    _info: 'Manually curated articles for the Morning Brief. The "reason" field on each entry records the editorial decision — this is institutional memory: coverage gaps, competitive intelligence, or classification edge cases. brief.py merges these into the story feed on every run. Any Claude session revisiting this project can read this file to understand past coverage decisions.',
    articles: CLIPS.articles || []
  };
  const blob = new Blob([JSON.stringify(out, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'manual_articles.json'; a.click();
  setKsStatus('Downloaded manual_articles.json — save to repo root and re-run brief.py', 'ok');
}
"""

def render_story_card(story, cluster_info=None):
    """Render a single story card HTML."""
    headline_html = h(story.get('headline', ''))
    url = story.get('url', '#')
    source = h(story.get('source', 'Unknown'))
    date = h(story.get('date', ''))
    snippet = h(story.get('snippet', ''))
    category = story.get('category', 'mention')
    is_manual = story.get('is_manual', False)
    reason = h(story.get('reason', ''))

    search_text = html_lib.escape(
        (story.get('headline', '') + ' ' + story.get('snippet', '') + ' ' + story.get('source', '')).lower()
    )

    cat_class   = f'tag-{category}'
    cat_display = category.replace('_', ' ').title()

    also_covered_html = ''
    if cluster_info and cluster_info.get('also_covered_by'):
        sources = ', '.join(h(s.get('source', 'Source')) for s in cluster_info['also_covered_by'])
        also_covered_html = f'<div class="also-covered"><strong>Also covered by:</strong> {sources}</div>'

    manual_tag    = '<span class="story-tag tag-manual">&#9986; Manual Clip</span>' if is_manual else ''
    reason_html   = (
        f'<div class="story-manual-reason">{reason}</div>'
        if (is_manual and reason) else ''
    )

    return (
        f'<div class="story" data-ts="{story["ts"]}" data-text="{search_text}" data-cat="{category}">'
        f'<a class="story-hl" href="{h(url)}" target="_blank" rel="noopener">'
        f'{headline_html} <span class="ext">&#8599;</span></a>'
        f'<p class="story-snippet">{snippet}</p>'
        f'<div class="story-meta">'
        f'<span class="src">{source}</span>'
        f'<span class="sep">/</span><span>{date}</span>'
        f'</div>'
        f'<div class="story-tags"><span class="story-tag {cat_class}">{cat_display}</span>{manual_tag}</div>'
        f'{reason_html}'
        f'{also_covered_html}</div>'
    )

def build_html(clustered_stories, clients_config, generated_at, keywords=None, manual_data=None):
    """Build the HTML output."""
    now_sl   = generated_at.astimezone(SL_TZ)
    dateline = now_sl.strftime('%A, %d %B %Y')
    gen_time = now_sl.strftime('%H:%M SL')
    gen_ts   = int(generated_at.timestamp() * 1000)

    client_js   = json.dumps([{'key': c['key'], 'label': c['label']} for c in clients_config])
    client_names = ' &middot; '.join(h(c['label']) for c in clients_config)

    # Build control buttons
    client_btns = '<button class="ctrl-btn active" data-cl="all" onclick="setClient(\'all\')">All</button>'
    for c in clients_config:
        client_btns += (
            f'<button class="ctrl-btn" data-cl="{h(c["key"])}" '
            f'onclick="setClient(\'{h(c["key"])}\');">{h(c["label"])}</button>'
        )

    # Build category buttons
    category_btns = '<button class="ctrl-btn active" data-cat="all" onclick="setCategory(\'all\')">All</button>'
    for cat in ['mention', 'industry', 'market_watch', 'risk_watch']:
        cat_display = cat.replace('_', ' ').title()
        category_btns += (
            f'<button class="ctrl-btn" data-cat="{h(cat)}" '
            f'onclick="setCategory(\'{h(cat)}\');">{cat_display}</button>'
        )

    # Build sections
    sections = ''
    for client in clients_config:
        client_key = client['key']
        client_stories = [s for s in clustered_stories if s['client'] == client_key]
        
        if not client_stories:
            continue
        
        stories_html = ''
        for story in client_stories:
            stories_html += render_story_card(story, story.get('_cluster_info'))
        
        if not stories_html:
            stories_html = '<p class="no-stories">No stories in this view.</p>'
        
        sections += (
            f'<div class="section" id="sec-{client_key}">'
            f'<div class="sec-head">'
            f'<span class="sec-name">{h(client["label"])}</span>'
            f'<span class="sec-tag">{h(client.get("sector", ""))}</span>'
            f'<span class="sec-rule"></span>'
            f'<span class="sec-count"></span>'
            f'</div>'
            f'<div>{stories_html}</div>'
            f'</div>'
        )
    
    # Flatten clustered stories for JSON embedding
    flat_stories = []
    for cs in clustered_stories:
        flat_story = {k: v for k, v in cs.items() if k != '_cluster_info'}
        flat_stories.append(flat_story)
    
    story_json = json.dumps(flat_stories, ensure_ascii=False)
    kw_json    = json.dumps(keywords or {}, ensure_ascii=False)

    raw_clips     = manual_data or {}
    clean_articles = [
        {k: v for k, v in a.items() if k != '_cluster_info'}
        for a in raw_clips.get('articles', [])
    ]
    clips_json = json.dumps(
        {'_info': raw_clips.get('_info', ''), 'articles': clean_articles},
        ensure_ascii=False
    )

    studio_overlay = (
        '<div id="studio-overlay" class="studio-overlay hidden" onclick="if(event.target===this)closeStudio()">\n'
        '  <div class="studio-panel">\n'
        '    <div class="studio-head">\n'
        '      <h2>Keyword Studio</h2>\n'
        '      <span class="studio-head-sub">Morning Brief &middot; Adfactors PR</span>\n'
        '      <button class="studio-close" onclick="closeStudio()" title="Close">&#x2715;</button>\n'
        '    </div>\n'
        '    <div class="studio-body">\n'
        '      <div class="studio-section">\n'
        '        <div class="studio-section-title">Coverage Health &mdash; current brief</div>\n'
        '        <div class="health-grid" id="ks-health-grid"></div>\n'
        '      </div>\n'
        '      <div class="studio-section">\n'
        '        <div class="studio-section-title">Manual Clippings &mdash; paste a URL, auto-fill, classify, download</div>\n'
        '        <div class="clip-form">\n'
        '          <div class="clip-row"><span class="clip-label">URL</span>'
        '<input class="clip-input url" id="clip-url" type="url" placeholder="https://ft.lk/…">'
        '<button class="clip-fetch-btn" onclick="fetchClipMeta()">Auto-fill ↗</button></div>\n'
        '          <div class="clip-fetch-status" id="clip-fetch-status"></div>\n'
        '          <div class="clip-row"><span class="clip-label">Headline</span>'
        '<input class="clip-input" id="clip-headline" type="text" placeholder="Article headline"></div>\n'
        '          <div class="clip-row"><span class="clip-label">Source</span>'
        '<input class="clip-input" id="clip-source" type="text" placeholder="Daily FT"></div>\n'
        '          <div class="clip-row"><span class="clip-label">Date</span>'
        '<input class="clip-input" id="clip-date" type="text" placeholder="12 Jun 2026"></div>\n'
        '          <div class="clip-row"><span class="clip-label">Snippet</span>'
        '<textarea class="clip-textarea" id="clip-snippet" placeholder="Brief summary (optional)"></textarea></div>\n'
        '          <div class="clip-row"><span class="clip-label">Client</span>'
        '<select class="clip-select" id="clip-client"><option value="">— select —</option></select></div>\n'
        '          <div class="clip-row"><span class="clip-label">Category</span>'
        '<select class="clip-select" id="clip-category">'
        '<option value="mention">Mention</option>'
        '<option value="industry" selected>Industry</option>'
        '<option value="market_watch">Market Watch</option>'
        '<option value="risk_watch">Risk Watch</option>'
        '</select></div>\n'
        '          <div class="clip-row"><span class="clip-label">Reason</span>'
        '<textarea class="clip-textarea" id="clip-reason" '
        'placeholder="Why are you adding this? Becomes institutional memory for future briefs and Claude sessions."></textarea></div>\n'
        '          <button class="clip-add-btn" onclick="addClip()">+ Add to Clippings</button>\n'
        '        </div>\n'
        '        <div class="clip-list" id="clip-list"></div>\n'
        '        <div class="clip-dl-row">'
        '<button class="ks-btn" onclick="downloadClips()">&#x2193; Download manual_articles.json</button>'
        '</div>\n'
        '      </div>\n'
        '      <div class="studio-section">\n'
        '        <div class="studio-section-title">Keywords per Client &mdash; click to expand &middot; Enter to add &middot; &times; to remove</div>\n'
        '        <div id="ks-clients"></div>\n'
        '      </div>\n'
        '    </div>\n'
        '    <div class="studio-foot">\n'
        '      <span class="ks-status" id="ks-status">Ready</span>\n'
        '      <button class="ks-btn" onclick="KW=deepClone(KW_RAW);renderClients();setKsStatus(\'Reset to current keywords\',\'\')">Reset</button>\n'
        '      <button class="ks-btn primary" onclick="downloadKW()">&#x2193; Download keywords.json</button>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>\n'
    )

    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8"/>\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0"/>\n'
        f'<title>The Morning Brief — {dateline}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link href="{FONTS}" rel="stylesheet">\n'
        f'<style>{CSS}{STUDIO_CSS}</style>\n'
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
        '  <div class="ctrl-group"><span class="ctrl-label">Category</span>\n'
        f'  {category_btns}</div>\n'
        '  <div class="ctrl-divider"></div>\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Search</span>\n'
        '  <input class="ctrl-search" type="text" placeholder="filter stories…" oninput="setQ(this.value)"></div>\n'
        '  <div class="ctrl-right">'
        '<span class="result-count" id="result-count"></span>'
        '  <button class="ctrl-btn" style="margin-left:10px;" '
        'onclick="location.reload()" title="Reload page to fetch latest brief">&#8635; Refresh</button>'
        '  <button class="ctrl-btn" id="lowrel-btn" style="margin-left:6px;" '
        'onclick="toggleLowRel()" title="Toggle visibility of low relevance stories">Show low relevance</button>'
        '  <button class="ctrl-btn" style="margin-left:6px;border-color:var(--gold);color:var(--gold);" '
        'onclick="openStudio()">&#9998; Keyword Studio</button>'
        '</div>\n'
        '</div>\n'

        f'<div class="pages" id="pages">{sections}</div>\n'
        '<div class="foot">'
        'Auto-generated &middot; Google News (Sri Lanka) &middot; '
        f'Fetched last {WINDOW_DAYS} days &middot; SL-validated &middot; '
        'Duplicates grouped &middot; '
        'Verify before circulating &middot; '
        'No media contacts stored &middot; '
        '<a href="data/latest.json" style="color:var(--faint);text-decoration:none;">Raw data</a>'
        '</div>\n'
        '</div>\n'
        f'{studio_overlay}'
        f'<script id="story-data" type="application/json">{story_json}</script>\n'
        f'<script id="client-data" type="application/json">{client_js}</script>\n'
        f'<script id="gen-ts" type="application/json">{gen_ts}</script>\n'
        f'<script id="kw-data" type="application/json">{kw_json}</script>\n'
        f'<script id="clips-data" type="application/json">{clips_json}</script>\n'
        f'<script>{JS}\n{STUDIO_JS}</script>\n'
        '</body>\n</html>\n'
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('Morning Brief — Starting\n')

    generated_at = datetime.now(timezone.utc)
    cutoff_dt    = generated_at - timedelta(days=WINDOW_DAYS)
    cutoff_ms    = int(cutoff_dt.timestamp() * 1000)

    # Load configurations
    keywords = load_json('keywords.json', {})
    outlets_config = load_json('outlets.json', {})

    all_stories = []

    # ── Fetch all stories ──────────────────────────────────────────────────────
    for client in CLIENTS:
        client_key = client['key']
        client_config = keywords.get(client_key, {})
        
        if not client_config:
            print(f'[{client["label"]}] Skipped (no config)')
            continue
        
        # query_context only applies to direct_mentions — it's needed for
        # ambiguous short brand names (BYD, MAS, HNB) that flood the RSS feed
        # with global results. Industry / market / risk terms are already SL-specific
        # and adding context makes the query too long, returning 0 results.
        ctx = client_config.get('query_context', '')

        # Fetch direct mentions. Clients with 10+ terms (HNB, Hayleys) are split
        # into a primary fetch (main brand + most-used subsidiary, first 4 terms)
        # and a secondary fetch (the rest), so the dominant brand name doesn't
        # crowd subsidiaries out of the 100-result RSS feed. Results merge into
        # all_stories before deduplication and classification.
        print(f'[{client["label"]}] Direct Mentions')
        direct_mentions = client_config.get('direct_mentions', [])
        if len(direct_mentions) >= 10:
            term_groups = [direct_mentions[:4], direct_mentions[4:]]
        else:
            term_groups = [direct_mentions]
        for term_group in term_groups:
            query = build_query(term_group, context=ctx)
            if query:
                stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms)
                for s in stories:
                    s['fetch_type'] = 'direct_mentions'
                all_stories.extend(stories)

        # Fetch industry watch — no context; terms are SL-specific or named competitors
        print(f'[{client["label"]}] Industry')
        industry_watch = client_config.get('industry_watch', [])
        query = build_query(industry_watch)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms)
            for s in stories:
                s['fetch_type'] = 'industry_watch'
            all_stories.extend(stories)

        # Fetch market watch — no context
        print(f'[{client["label"]}] Market Watch')
        market_watch = client_config.get('market_watch', [])
        query = build_query(market_watch)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES * 2, SL_SIGNALS, cutoff_ms)
            for s in stories:
                s['fetch_type'] = 'market_watch'
            all_stories.extend(stories)

        # Fetch risk watch — no context
        print(f'[{client["label"]}] Risk Watch')
        risk_watch = client_config.get('risk_watch', [])
        query = build_query(risk_watch)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms)
            for s in stories:
                s['fetch_type'] = 'risk_watch'
            all_stories.extend(stories)
        
        print()

    print(f'Total stories before processing: {len(all_stories)}')

    # ── Classify stories ──────────────────────────────────────────────────────
    print('Classifying stories...')
    for story in all_stories:
        client_key = story['client']
        client_config = keywords.get(client_key, {})
        fetch_type = story.get('fetch_type', 'direct_mentions')
        category, relevance, matched = classify_story(story, client_config, outlets_config, fetch_type_hint=fetch_type)
        story['category'] = category
        story['relevance_score'] = relevance
        story['matched_terms'] = matched
        story['source_rank'] = source_rank(story.get('domain', ''), outlets_config)

    # ── Merge manual clippings (pre-classified, injected after auto-classify) ─
    manual_data = load_json('manual_articles.json', {'articles': []})
    manual_articles = manual_data.get('articles', [])
    for art in manual_articles:
        art['is_manual']             = True
        art['is_low_relevance']      = False
        art['is_primary_in_cluster'] = True
        art['cluster_id']            = art.get('id', f'manual_{art.get("ts",0)}')
        art['relevance_score']       = art.get('relevance_score', 1.0)
        art['matched_terms']         = art.get('matched_terms', ['manual'])
        art['source_rank']           = source_rank(
            art.get('domain', extract_domain(art.get('url', ''))), outlets_config
        )
        if 'snippet' not in art:
            art['snippet'] = ''
    if manual_articles:
        print(f'Manual clippings loaded: {len(manual_articles)}')
    all_stories.extend(manual_articles)

    # ── Remove low relevance stories (keep in JSON but hide from main view) ────
    for story in all_stories:
        story['is_low_relevance'] = story['category'] == 'low_relevance'

    # ── Cluster duplicates ────────────────────────────────────────────────────
    print('Grouping duplicate stories...')
    clusters = cluster_stories(all_stories)

    clustered_stories = []
    for cluster in clusters:
        primary = cluster['primary']
        primary['_cluster_info'] = cluster
        primary['cluster_id']    = cluster['cluster_id']
        primary['is_primary_in_cluster'] = True
        clustered_stories.append(primary)

    # Sort: manual clips always surface first within their relevance tier
    clustered_stories.sort(key=lambda s: (
        -int(s.get('is_manual', False)),
        -s.get('relevance_score', 0),
        -s.get('ts', 0)
    ))

    print(f'Total stories after clustering: {len(clustered_stories)}')

    # ── Generate HTML ────────────────────────────────────────────────────────
    print('Building HTML...')
    page = build_html(clustered_stories, CLIENTS, generated_at,
                      keywords=keywords, manual_data=manual_data)

    # ── Validation ────────────────────────────────────────────────────────────
    is_safe, messages = validate_no_private_contacts(page)
    for msg in messages:
        print(f'  {msg}')
    if not is_safe:
        print('  ✗ Privacy check FAILED')
        sys.exit(1)

    # ── Save output ────────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(page)

    # ── Save archive ────────────────────────────────────────────────────────────
    print('Saving archive...')
    save_archive(clustered_stories, clusters)

    print(f'Done — {OUTPUT_FILE} written ({len(page):,} bytes)')
    print(f'Done — data/latest.json and data/archive/ updated')
    print()


if __name__ == '__main__':
    main()
