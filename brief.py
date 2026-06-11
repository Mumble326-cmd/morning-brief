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

def build_query(terms):
    """Build Google News query from keyword terms."""
    if not terms:
        return ''
    return ' OR '.join(f'"{t}"' for t in terms)

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

JS = r"""
const STORIES = JSON.parse(document.getElementById('story-data').textContent);
const CLIENTS = JSON.parse(document.getElementById('client-data').textContent);
const GENERATED = parseInt(document.getElementById('gen-ts').textContent);
const MS = { '1d':86400000,'7d':604800000,'14d':1209600000,'30d':2592000000 };
let state = { win:'7d', client:'all', category:'all', q:'' };

function setWin(v)      { state.win=v;       syncBtns('win'); }
function setClient(v)   { state.client=v;    syncBtns('client'); }
function setCategory(v) { state.category=v;  syncBtns('category'); }
function setQ(v)        { state.q=v.toLowerCase().trim(); render(); }

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
      const show = ts >= cutoff && secVis && catVis && (!q || text.includes(q));
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

def render_story_card(story, cluster_info=None):
    """Render a single story card HTML."""
    headline_html = h(story.get('headline', ''))
    url = story.get('url', '#')
    source = h(story.get('source', 'Unknown'))
    date = h(story.get('date', ''))
    snippet = h(story.get('snippet', ''))
    category = story.get('category', 'mention')
    relevance = story.get('relevance_score', 1.0)
    
    # Build search text for filtering
    search_text = html_lib.escape(
        (story.get('headline', '') + ' ' + story.get('snippet', '') + ' ' + story.get('source', '')).lower()
    )
    
    # Category tag
    cat_class = f'tag-{category}'
    cat_display = category.replace('_', ' ').title()
    
    # Also covered
    also_covered_html = ''
    if cluster_info and cluster_info.get('also_covered_by'):
        sources = ', '.join(h(s.get('source', 'Source')) for s in cluster_info['also_covered_by'])
        also_covered_html = f'<div class="also-covered"><strong>Also covered by:</strong> {sources}</div>'
    
    return (
        f'<div class="story" data-ts="{story["ts"]}" data-text="{search_text}" data-cat="{category}">'
        f'<a class="story-hl" href="{h(url)}" target="_blank" rel="noopener">'
        f'{headline_html} <span class="ext">&#8599;</span></a>'
        f'<p class="story-snippet">{snippet}</p>'
        f'<div class="story-meta">'
        f'<span class="src">{source}</span>'
        f'<span class="sep">/</span><span>{date}</span>'
        f'</div>'
        f'<div class="story-tags"><span class="story-tag {cat_class}">{cat_display}</span></div>'
        f'{also_covered_html}</div>'
    )

def build_html(clustered_stories, clients_config, generated_at):
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
    
    story_json  = json.dumps(flat_stories, ensure_ascii=False)
    
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
        '  <div class="ctrl-group"><span class="ctrl-label">Category</span>\n'
        f'  {category_btns}</div>\n'
        '  <div class="ctrl-divider"></div>\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Search</span>\n'
        '  <input class="ctrl-search" type="text" placeholder="filter stories…" oninput="setQ(this.value)"></div>\n'
        '  <div class="ctrl-right"><span class="result-count" id="result-count"></span></div>\n'
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
        f'<script id="story-data" type="application/json">{story_json}</script>\n'
        f'<script id="client-data" type="application/json">{client_js}</script>\n'
        f'<script id="gen-ts" type="application/json">{gen_ts}</script>\n'
        f'<script>{JS}</script>\n'
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
        
        # Fetch direct mentions
        print(f'[{client["label"]}] Direct Mentions')
        direct_mentions = client_config.get('direct_mentions', [])
        query = build_query(direct_mentions)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms)
            all_stories.extend(stories)
        
        # Fetch industry watch
        print(f'[{client["label"]}] Industry')
        industry_watch = client_config.get('industry_watch', [])
        query = build_query(industry_watch)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms)
            all_stories.extend(stories)
        
        # Fetch market watch
        print(f'[{client["label"]}] Market Watch')
        market_watch = client_config.get('market_watch', [])
        query = build_query(market_watch)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES * 2, SL_SIGNALS, cutoff_ms)
            all_stories.extend(stories)
        
        # Fetch risk watch
        print(f'[{client["label"]}] Risk Watch')
        risk_watch = client_config.get('risk_watch', [])
        query = build_query(risk_watch)
        if query:
            stories = fetch_news(query, client_key, WINDOW_DAYS, MAX_STORIES, SL_SIGNALS, cutoff_ms)
            all_stories.extend(stories)
        
        print()

    print(f'Total stories before processing: {len(all_stories)}')

    # ── Classify stories ──────────────────────────────────────────────────────
    print('Classifying stories...')
    for story in all_stories:
        client_key = story['client']
        client_config = keywords.get(client_key, {})
        category, relevance, matched = classify_story(story, client_config, outlets_config)
        story['category'] = category
        story['relevance_score'] = relevance
        story['matched_terms'] = matched
        story['source_rank'] = source_rank(story.get('domain', ''), outlets_config)

    # ── Remove low relevance stories (keep in JSON but hide from main view) ────
    for story in all_stories:
        story['is_low_relevance'] = story['category'] == 'low_relevance'

    # ── Cluster duplicates ────────────────────────────────────────────────────
    print('Grouping duplicate stories...')
    clusters = cluster_stories(all_stories)
    
    clustered_stories = []
    for cluster in clusters:
        primary = cluster['primary']
        
        # Enhance primary with cluster info
        primary['_cluster_info'] = cluster
        primary['cluster_id'] = cluster['cluster_id']
        primary['is_primary_in_cluster'] = True
        
        clustered_stories.append(primary)

    # Sort by relevance and date
    clustered_stories.sort(key=lambda s: (-s.get('relevance_score', 0), -s.get('ts', 0)))

    print(f'Total stories after clustering: {len(clustered_stories)}')
    
    # ── Generate HTML ────────────────────────────────────────────────────────
    print('Building HTML...')
    page = build_html(clustered_stories, CLIENTS, generated_at)

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
