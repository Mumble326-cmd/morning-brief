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
import time
import socket
import calendar
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    import feedparser
except ImportError:       # Only fetch_outlet_feed needs it; the offline replay
    feedparser = None     # harness (--replay) must run without network extras.

from config import (
    CLIENTS, SL_SIGNALS, WINDOW_DAYS, MAX_STORIES, OUTPUT_FILE, DIRECT_FEEDS,
    GLOBAL_EXCLUDE, SERIES_PATTERNS, CATEGORY_CAPS,
)
from utils import (
    load_json, save_json, normalize_text, extract_domain, source_rank,
    source_name_rank, effective_source_rank,
    classify_story, cluster_stories, choose_primary_story, term_matches,
    strip_headline_boilerplate, compound_score, rollup_series,
    apply_category_caps,
    save_archive, validate_no_private_contacts,
    load_previous_story_keys, load_trend_counts, prune_old_archives,
    SL_TZ,
)

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

# ── Direct outlet feeds ────────────────────────────────────────────────────────

# Some outlets (EconomyNext) 403 the default bot UA
BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

def fetch_outlet_feed(feed, cutoff_ms):
    """
    Fetch a direct outlet feed via feedparser. Returns raw items (no client yet).

    feedparser is used here (instead of the hand-rolled ElementTree parse) because
    it tolerates the malformed XML, mismatched encodings, RSS 1.0/2.0/Atom variants,
    and timezone-naive dates that have caused these outlet feeds to fail silently.
    """
    sys.stdout.write(f'  [{feed["source"]}] fetching...\n')
    sys.stdout.flush()
    if feedparser is None:
        sys.stdout.write('    x feedparser not installed — skipping outlet feed\n')
        sys.stdout.flush()
        return []
    try:
        # Fetch the bytes ourselves with an explicit timeout — feedparser.parse()
        # does its own fetch with NO timeout and will hang forever on a stalled
        # feed. We keep feedparser only for its robust parsing of the bytes.
        req = urllib.request.Request(feed['url'], headers={
            'User-Agent': BROWSER_UA,
            'Accept': 'application/rss+xml, application/xml;q=0.9, */*;q=0.8',
        })
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
        d = feedparser.parse(raw)
        # bozo flags a parse problem; only fatal if it also yielded no entries.
        if d.bozo and not d.entries:
            raise ValueError(str(d.bozo_exception))
    except Exception as e:
        sys.stdout.write(f'    x {e}\n'); sys.stdout.flush()
        return []

    items = []
    for entry in d.entries:
        link     = (entry.get('link') or '').strip()
        headline = html_lib.unescape((entry.get('title') or '').strip())
        if not link or not headline:
            continue
        snippet = clean_html(entry.get('summary') or entry.get('description') or '')
        # WordPress feeds append "The post X appeared first on Y."
        snippet = re.sub(r'The post .{0,200} appeared first on .*$', '', snippet).strip()[:320]

        # Prefer the raw RFC-822 string; fall back to feedparser's parsed
        # struct_time (already UTC) for feeds whose date strings we can't parse.
        date_label, epoch_ms = parse_timestamp(
            entry.get('published') or entry.get('updated') or ''
        )
        if epoch_ms == 0:
            tp = entry.get('published_parsed') or entry.get('updated_parsed')
            if tp:
                dt = datetime.fromtimestamp(calendar.timegm(tp), tz=timezone.utc).astimezone(SL_TZ)
                date_label = dt.strftime('%d %b %Y · %H:%M SL')
                epoch_ms   = int(dt.timestamp() * 1000)

        if epoch_ms > 0 and epoch_ms < cutoff_ms:
            continue
        items.append({
            'headline': headline,
            'url':      link,
            'source':   feed['source'],
            'domain':   extract_domain(link),
            'date':     date_label,
            'ts':       epoch_ms,
            'snippet':  snippet,
        })
    return items

# ── Google News redirect resolution ──────────────────────────────────────────

_GOOGLE_URL_CACHE = {}
_RESOLVE_DEADLINE = {'t': None}   # overall time budget for a single run

def resolve_google_url(redirect_url):
    """
    Resolve a Google News RSS redirect (news.google.com/rss/articles/CBMi...)
    to the real publisher URL by following the redirect once (5s timeout, no
    retry). Resolved URLs are cached for the run so the same redirect is never
    fetched twice. On any failure the original redirect URL is returned and a
    warning logged — a story is never dropped over an unresolvable link.
    """
    if not redirect_url or 'news.google.com' not in redirect_url:
        return redirect_url
    if redirect_url in _GOOGLE_URL_CACHE:
        return _GOOGLE_URL_CACHE[redirect_url]
    # Stop resolving once the per-run budget is spent; keep originals thereafter.
    if _RESOLVE_DEADLINE['t'] and time.monotonic() > _RESOLVE_DEADLINE['t']:
        return redirect_url

    resolved = redirect_url
    try:
        req = urllib.request.Request(redirect_url, headers={'User-Agent': BROWSER_UA})
        with urllib.request.urlopen(req, timeout=5) as resp:
            final = resp.geturl()
            if final and 'news.google.com' not in final:
                resolved = final
            else:
                # Newer Google News uses a JS/meta redirect rather than an HTTP
                # 3xx — scrape the publisher URL out of the interstitial body.
                body = resp.read(60000).decode('utf-8', errors='replace')
                for pat in (
                    r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"',
                    r'data-n-au="([^"]+)"',
                    r'rel="canonical"\s+href="([^"]+)"',
                ):
                    m = re.search(pat, body)
                    if m and 'news.google.com' not in m.group(1):
                        resolved = html_lib.unescape(m.group(1))
                        break
    except Exception as e:
        sys.stdout.write(f'    ! url resolve failed ({e})\n'); sys.stdout.flush()

    _GOOGLE_URL_CACHE[redirect_url] = resolved
    return resolved

def match_feed_items_to_clients(items, keywords):
    """
    Assign direct-feed items to every client whose direct_mentions (or
    risk_watch) terms appear in the headline/snippet. These are domestic
    outlets, so the SL-signal gate is skipped.
    """
    matched = []
    for item in items:
        text = item['headline'] + ' ' + item['snippet']
        for client_key, cfg in keywords.items():
            fetch_type = None
            # term_matches enforces word boundaries for short terms so a feed
            # item doesn't get tagged BYD because it contains "ABYDOS", etc.
            if any(term_matches(t, text) for t in cfg.get('direct_mentions', [])):
                fetch_type = 'direct_mentions'
            elif any(term_matches(t, text) for t in cfg.get('risk_watch', [])):
                fetch_type = 'risk_watch'
            if fetch_type:
                story = dict(item)
                story['client'] = client_key
                story['fetch_type'] = fetch_type
                matched.append(story)
    return matched

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
.exec{background:var(--cream);border-bottom:1px solid var(--rule);padding:14px 36px 16px;}
.exec-label{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--gold);margin-bottom:9px;}
.exec-list{list-style:none;display:flex;flex-direction:column;gap:7px;}
.exec-item{display:flex;gap:10px;align-items:baseline;}
.exec-num{font-family:"Playfair Display",serif;font-style:italic;color:var(--gold);
  font-size:14px;width:13px;flex-shrink:0;text-align:right;}
.exec-client{font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.08em;
  text-transform:uppercase;background:var(--accent);color:var(--paper);
  padding:2px 6px;border-radius:2px;flex-shrink:0;}
.exec-hl{font-family:"Playfair Display",serif;font-size:14.5px;font-weight:600;
  color:var(--ink);text-decoration:none;line-height:1.3;}
.exec-hl:hover{text-decoration:underline;text-underline-offset:3px;}
.exec-meta{font-family:"IBM Plex Mono",monospace;font-size:8.5px;color:var(--faint);
  flex-shrink:0;white-space:nowrap;}
.pages{padding:20px 0 60px;}
.section{padding:20px 0;}
.sec-head{display:flex;align-items:baseline;gap:14px;margin-bottom:12px;}
.sec-trend{display:inline-flex;align-items:center;gap:6px;align-self:center;
  font-family:"IBM Plex Mono",monospace;font-size:9px;color:var(--faint);
  letter-spacing:.05em;white-space:nowrap;}
.sec-trend .spark{color:var(--category-market);display:block;}
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
.tag-new{background:var(--accent);color:var(--gold);}
.pub-chips{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:6px;}
.pub-chips-label{font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);}
.pub-chip{font-family:"IBM Plex Mono",monospace;font-size:8.5px;letter-spacing:.04em;
  text-decoration:none;color:var(--muted);background:var(--cream);
  border:1px solid var(--rule-soft);padding:2px 7px;border-radius:2px;transition:all .12s;}
.pub-chip:hover{border-color:var(--accent);color:var(--ink);}
.cov-first{font-size:7px;letter-spacing:.06em;background:var(--gold);color:var(--accent);
  padding:1px 4px;border-radius:2px;vertical-align:middle;font-weight:700;margin-left:2px;}
.cov-date{font-size:7.5px;color:var(--faint);margin-left:1px;}
.no-stories{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);
  padding:12px 0;letter-spacing:.04em;}
.no-new{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--faint);
  padding:10px 0;letter-spacing:.04em;font-style:italic;}
.exec-new{color:var(--gold);font-weight:600;}
.prev-details{margin-top:10px;border-top:1px dashed var(--rule);}
.prev-details summary{font-family:"IBM Plex Mono",monospace;font-size:9.5px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--muted);cursor:pointer;
  padding:9px 0;user-select:none;}
.prev-details summary:hover{color:var(--ink);}
.prev-details[open] summary{border-bottom:1px solid var(--rule-soft);}
.prev-body .story:first-child{border-top:none;}
.series-block{margin-top:10px;padding:8px 0 2px;border-top:1px dashed var(--rule);}
.series-label{font-family:"IBM Plex Mono",monospace;font-size:8.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:5px;}
.series-line{display:flex;align-items:baseline;gap:7px;padding:3px 0;
  font-size:12px;flex-wrap:wrap;}
.series-dot{color:var(--faint);font-size:10px;flex-shrink:0;}
.series-hl{color:var(--muted);text-decoration:none;}
.series-hl:hover{color:var(--ink);text-decoration:underline;text-underline-offset:2px;}
.series-meta{font-family:"IBM Plex Mono",monospace;font-size:8.5px;color:var(--faint);
  white-space:nowrap;}
.foot{padding:16px 36px;border-top:1px solid var(--rule);font-family:"IBM Plex Mono",monospace;
  font-size:9px;letter-spacing:.06em;color:var(--faint);line-height:1.7;}
@media(max-width:600px){
  h1{font-size:30px;}
  .pages,.masthead,.controls,.foot,.exec{padding-left:18px;padding-right:18px;}
  .ctrl-search{width:110px;}
  .exec-meta{display:none;}
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
let state = { win:'30d', client:'all', category:'all', q:'' };

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
  // The staleness problem is handled structurally (new cards up top,
  // "Previously reported" collapsed), so the window filter defaults to 30d
  // and simply narrows what's eligible anywhere on the page.
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
      // Manual clips bypass the date-window filter — they're curated and must
      // stay visible on every window (e.g. the MIFL debenture is >30 days old).
      const isManual = s.dataset.manual === 'true';
      const show = (isManual || ts >= cutoff) && secVis && catVis && (!q || text.includes(q));
      s.style.display = show ? '' : 'none';
      if (show) { secCount++; total++; }
    });
    // Recurring-update rollup lines: category filter only (they're one-line
    // data points, not story cards — the window/search filters skip them).
    sec.querySelectorAll('.series-line').forEach(l => {
      const catVis = state.category==='all' || state.category===(l.dataset.cat||'industry');
      l.style.display = catVis ? '' : 'none';
    });
    // A section stays visible even with zero matching stories — its explicit
    // "No new coverage" line IS the signal. Only the client filter hides it.
    sec.style.display = secVis ? '' : 'none';
    // Collapse bookkeeping: hide the details block when filters empty it.
    const det = sec.querySelector('.prev-details');
    if (det) {
      let prevVis = 0;
      det.querySelectorAll('.story').forEach(s => { if (s.style.display !== 'none') prevVis++; });
      det.style.display = prevVis > 0 ? '' : 'none';
      const pc = det.querySelector('.prev-count');
      if (pc) pc.textContent = prevVis;
    }
    const cnt = sec.querySelector('.sec-count');
    if (cnt) cnt.textContent = secCount + (secCount===1?' story':' stories');
  });
  const rc = document.getElementById('result-count');
  if (rc) rc.textContent = total + (total===1?' story':' stories');
}

document.addEventListener('DOMContentLoaded', () => {
  syncBtns('win'); syncBtns('client'); syncBtns('category');
});

function printCoverage() {
  const cl = state.client, cat = state.category;
  const labelMap = {};
  CLIENTS.forEach(c => { labelMap[c.key] = c.label; });
  const today = new Date().toLocaleDateString('en-GB',{weekday:'long',day:'2-digit',month:'long',year:'numeric'});
  let filterLabel = '';
  if (cl !== 'all') filterLabel += ' · ' + (labelMap[cl] || cl);
  if (cat !== 'all') filterLabel += ' · ' + cat.replace(/_/g,' ');

  // Group by client
  const byClient = {};
  STORIES.forEach(s => {
    if (s.category === 'low_relevance') return;
    if (s.is_series_repeat || s.is_capped) return;
    if (cl !== 'all' && s.client !== cl) return;
    if (cat !== 'all' && s.category !== cat) return;
    if (!byClient[s.client]) byClient[s.client] = [];
    byClient[s.client].push(s);
  });

  let body = '';
  CLIENTS.forEach(c => {
    const ss = byClient[c.key];
    if (!ss || !ss.length) return;
    body += `<div class="cl"><div class="cl-name">${c.label}</div>`;
    ss.forEach(s => {
      const also = s.also_covered_by || [];
      let alsoHtml = '';
      if (also.length) {
        alsoHtml = '<div class="also-head">Also covered by:</div>' +
          also.map(x => `<div class="also-row"><span class="also-src">${x.source||''}</span> <span class="also-url">${x.url||''}</span></div>`).join('');
      }
      body += `<div class="story">
        <div class="hl"><a href="${s.url||''}">${s.headline||''}</a></div>
        <div class="meta">${s.source||''} &nbsp;·&nbsp; ${s.date||''} &nbsp;·&nbsp; <span class="cat">${(s.category||'').replace(/_/g,' ')}</span></div>
        <div class="url">${s.url||''}</div>
        ${alsoHtml}
      </div>`;
    });
    body += '</div>';
  });

  const html = `<!DOCTYPE html><html><head><meta charset="UTF-8">
  <title>Morning Brief Coverage — ${today}</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:Georgia,serif;font-size:10.5pt;color:#111;max-width:750px;margin:0 auto;padding:28px 24px;}
    h1{font-size:20pt;margin-bottom:3px;}
    .dateline{font-size:9pt;color:#666;font-family:monospace;margin-bottom:22px;letter-spacing:.04em;}
    .cl{margin-bottom:22px;page-break-inside:avoid;}
    .cl-name{font-size:14pt;font-weight:bold;border-bottom:2px solid #000;padding-bottom:3px;margin-bottom:10px;}
    .story{margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #ddd;page-break-inside:avoid;}
    .hl{font-size:11pt;font-weight:bold;margin-bottom:3px;}
    .hl a{color:#000;text-decoration:none;}
    .meta{font-size:8.5pt;color:#555;font-family:monospace;margin-bottom:2px;}
    .cat{text-transform:uppercase;font-size:7.5pt;letter-spacing:.05em;}
    .url{font-size:7.5pt;color:#0645AD;word-break:break-all;margin-bottom:4px;}
    .also-head{font-size:8pt;font-family:monospace;color:#555;margin-top:5px;text-transform:uppercase;letter-spacing:.06em;}
    .also-row{font-size:8pt;margin:2px 0 2px 10px;font-family:monospace;}
    .also-src{font-weight:bold;color:#333;}
    .also-url{color:#0645AD;word-break:break-all;}
    @media print{
      body{max-width:none;padding:0 18px;}
      a[href]::after{content:" (" attr(href) ")";font-size:7pt;color:#666;}
      .hl a::after{display:none;}
      .url::before{content:"";}
    }
  </style>
  </head><body>
  <h1>Morning Brief — Coverage Report</h1>
  <div class="dateline">${today}${filterLabel}</div>
  ${body}
  </body></html>`;

  const w = window.open('','_blank');
  if (!w) { alert('Allow pop-ups to generate the PDF.'); return; }
  w.document.write(html);
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 600);
}
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
  const NOW_MS = Date.now();
  list.innerHTML = arts.map((a, i) => {
    const also = a.also_covered_by || [];
    const alsoLabel = also.length ? `<span style="color:var(--gold)">+${also.length} outlet${also.length>1?'s':''}</span>` : '';
    const daysOld = a.ts ? (NOW_MS - a.ts) / 86400000 : 0;
    const staleLabel = daysOld > 30
      ? `<span style="color:var(--category-risk);font-weight:600;">STALE ${Math.round(daysOld)}d — consider removing</span>` : '';
    return `<div class="clip-item" style="${daysOld>30?'border-left-color:var(--category-risk);opacity:.8;':''}">
      <div style="display:flex;align-items:flex-start;gap:6px;">
        <div style="display:flex;flex-direction:column;gap:3px;flex-shrink:0;padding-top:2px;">
          <button class="clip-item-rm" onclick="moveClip(${i},-1)" ${i===0?'disabled':''} title="Move up">↑</button>
          <button class="clip-item-rm" onclick="moveClip(${i},1)" ${i===arts.length-1?'disabled':''} title="Move down">↓</button>
        </div>
        <div style="flex:1;min-width:0;">
          <div class="clip-item-hl">${htmlesc(a.headline)}</div>
          <div class="clip-item-meta">
            <span>${htmlesc(a.source||'')}</span>
            <span>${htmlesc(a.date||'')}</span>
            <span>${htmlesc(a.client_label||a.client||'')}</span>
            <span>${htmlesc((a.category||'').replace(/_/g,' '))}</span>
            ${alsoLabel}${staleLabel}
          </div>
          ${a.reason ? `<div class="clip-item-reason">${htmlesc(a.reason)}</div>` : ''}
          <button class="clip-item-rm" onclick="removeClip(${i})">remove</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

function removeClip(i) {
  CLIPS.articles.splice(i, 1);
  renderClips();
  setKsStatus('Clipping removed — download to apply', 'warn');
}

function moveClip(i, dir) {
  const arts = CLIPS.articles || [];
  const j = i + dir;
  if (j < 0 || j >= arts.length) return;
  [arts[i], arts[j]] = [arts[j], arts[i]];
  renderClips();
  setKsStatus('Reordered — download to apply', '');
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

const OUTLET_DOMAIN_MAP = {
  'ft.lk':'Daily FT','dailymirror.lk':'Daily Mirror','island.lk':'The Island',
  'themorning.lk':'The Morning','adaderana.lk':'Ada Derana',
  'bizenglish.adaderana.lk':'Ada Derana Biz','lankabusinessnews.com':'Lanka Business News',
  'economynext.com':'EconomyNext','lankabusinessonline.com':'LBO',
  'colombogazette.com':'Colombo Gazette','dailynews.lk':'Daily News',
  'sundaytimes.lk':'Sunday Times','newswire.lk':'Newswire',
  'businesscafe.lk':'Business Cafe','srilankachronicle.com':'Sri Lanka Chronicle',
  'ceylontoday.lk':'Ceylon Today','sundayobserver.lk':'Sunday Observer',
};
function outletNameFromUrl(u) {
  try {
    const h = new URL(u).hostname.replace(/^www\./,'');
    return OUTLET_DOMAIN_MAP[h] || h;
  } catch(e) { return u; }
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
  // Derive ts from the article's publication date; fall back to now if unparseable
  const dateVal = g('clip-date');
  let ts = now.getTime();
  if (dateVal) { const pd = new Date(dateVal); if (!isNaN(pd.getTime())) ts = pd.getTime(); }
  // Parse additional coverage URLs (one per line)
  const coverageRaw = document.getElementById('clip-coverage-urls').value.trim();
  const alsoCovered = coverageRaw.split(/\n+/).map(u => u.trim()).filter(u => u.startsWith('http')).map(u => ({
    url: u,
    source: outletNameFromUrl(u),
    date: dateVal || '',
    ts: ts,
  }));
  if (!CLIPS.articles) CLIPS.articles = [];
  CLIPS.articles.push({
    id: 'manual_' + now.getTime(),
    url, headline,
    source:   g('clip-source')  || 'Unknown',
    date:     dateVal || now.toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'}),
    ts,
    snippet:  g('clip-snippet'),
    client,   client_label: clientLabel,
    category, reason: g('clip-reason'),
    domain,   added_at: now.toISOString().slice(0,10),
    also_covered_by: alsoCovered,
  });
  ['clip-url','clip-headline','clip-source','clip-snippet','clip-reason','clip-coverage-urls'].forEach(id =>
    { document.getElementById(id).value = ''; }
  );
  document.getElementById('clip-date').value = '';
  document.getElementById('clip-fetch-status').textContent = '';
  renderClips();
  setKsStatus('Clipping added' + (alsoCovered.length ? ` with ${alsoCovered.length} coverage URL(s)` : '') + ' — download manual_articles.json to apply', 'ok');
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

def sparkline_svg(values, width=84, height=20):
    """Inline SVG sparkline for a list of daily story counts."""
    if not values:
        return ''
    vmax = max(max(values), 1)
    if len(values) == 1:
        values = values * 2  # flat line for a single data point
    step = width / (len(values) - 1)
    pts = ' '.join(
        f'{i * step:.1f},{height - 2 - (v / vmax) * (height - 4):.1f}'
        for i, v in enumerate(values)
    )
    return (
        f'<svg class="spark" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<polyline points="{pts}" fill="none" stroke="currentColor" '
        f'stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )

def pick_executive_stories(stories, limit=6, per_client_cap=2):
    """
    Top stories for the Executive Summary strip.
    New-since-yesterday stories always outrank older ones (this strip answers
    "what happened since the last brief?"); within each tier the compound
    score decides. A two-pass selection ensures client variety before repeats.
    """
    candidates = sorted(
        [s for s in stories
         if s.get('category') != 'low_relevance'
         and not s.get('is_series_leader')
         and not s.get('is_series_repeat')
         and not s.get('is_capped')],
        key=lambda s: (not s.get('is_new'), -s.get('score', 0.0)),
    )

    # Pass 1: one per client for variety — NEW stories only, so a client with
    # nothing new doesn't push today's second-best headline out of the strip
    # (its section already says "No new coverage" explicitly).
    picked, per_client = [], {}
    for s in candidates:
        if not s.get('is_new'):
            continue
        if per_client.get(s['client'], 0) < 1:
            picked.append(s)
            per_client[s['client']] = 1
        if len(picked) >= limit:
            return picked

    # Pass 2: fill remaining slots up to per_client_cap
    picked_set = {id(s) for s in picked}
    for s in candidates:
        if id(s) in picked_set:
            continue
        if per_client.get(s['client'], 0) < per_client_cap:
            picked.append(s)
            per_client[s['client']] = per_client.get(s['client'], 0) + 1
            if len(picked) >= limit:
                break

    return picked

def render_story_card(story, cluster_info=None):
    """Render a single story card HTML."""
    headline_html = h(story.get('headline', ''))
    url = story.get('url', '#')
    source = h(story.get('source', 'Unknown'))
    date = h(story.get('date', ''))
    # Google News snippets are often just the headline re-stated with the
    # outlet name appended — rendering that under the headline is pure noise.
    raw_snippet = story.get('snippet', '') or ''
    if normalize_text(raw_snippet).startswith(normalize_text(story.get('headline', ''))):
        raw_snippet = ''
    snippet = h(raw_snippet)
    category = story.get('category', 'mention')
    is_manual = story.get('is_manual', False)
    reason = h(story.get('reason', ''))

    search_text = html_lib.escape(
        (story.get('headline', '') + ' ' + story.get('snippet', '') + ' ' + story.get('source', '')).lower()
    )

    tag_classes = {
        'mention':       'tag-mention',
        'industry':      'tag-industry',
        'market_watch':  'tag-market',
        'risk_watch':    'tag-risk',
        'low_relevance': 'tag-lowrel',
    }
    cat_class   = tag_classes.get(category, 'tag-mention')
    cat_display = category.replace('_', ' ').title()

    also_covered_html = ''
    # Build full coverage list: primary + all secondaries, sorted by publish date
    all_cov = [{'source': story.get('source', 'Unknown'), 'url': url,
                'ts': story.get('ts', 0), 'date': story.get('date', '')}]
    if cluster_info:
        for s in cluster_info.get('also_covered_by', []):
            all_cov.append({'source': s.get('source') or s.get('domain') or 'Source',
                            'url': s.get('url', '#'), 'ts': s.get('ts', 0),
                            'date': s.get('date', '')})
    if len(all_cov) > 1:
        all_cov_sorted = sorted(all_cov, key=lambda x: x.get('ts') or 0)
        first_ts = all_cov_sorted[0].get('ts') or 0
        seen_sources, chips = set(), ''
        for cov in all_cov_sorted:
            name = cov['source']
            if name in seen_sources:
                continue
            seen_sources.add(name)
            is_first = first_ts and cov.get('ts') == first_ts
            # Extract short date: "20 Jun" from "20 Jun 2026 · 14:30 SL"
            dm = re.match(r'(\d{1,2}\s+\w{3})', cov.get('date', ''))
            short_date = dm.group(1) if dm else ''
            first_badge = ' <span class="cov-first">1st</span>' if is_first else ''
            date_badge = f' <span class="cov-date">{h(short_date)}</span>' if short_date else ''
            chips += (
                f'<a class="pub-chip" href="{h(cov.get("url","#"))}" '
                f'target="_blank" rel="noopener">{h(name)}{first_badge}{date_badge}</a>'
            )
        also_covered_html = (
            f'<div class="pub-chips"><span class="pub-chips-label">Coverage</span>{chips}</div>'
        )

    new_tag       = '<span class="story-tag tag-new">&#9733; New</span>' if story.get('is_new') else ''
    manual_tag    = '<span class="story-tag tag-manual">&#9986; Manual Clip</span>' if is_manual else ''
    reason_html   = (
        f'<div class="story-manual-reason">{reason}</div>'
        if (is_manual and reason) else ''
    )

    manual_attr = ' data-manual="true"' if is_manual else ''
    new_attr    = ' data-new="1"' if story.get('is_new') else ''

    return (
        f'<div class="story" data-ts="{story["ts"]}" data-text="{search_text}" data-cat="{category}"{manual_attr}{new_attr}>'
        f'<a class="story-hl" href="{h(url)}" target="_blank" rel="noopener">'
        f'{headline_html} <span class="ext">&#8599;</span></a>'
        + (f'<p class="story-snippet">{snippet}</p>' if snippet else '') +
        f'<div class="story-meta">'
        f'<span class="src">{source}</span>'
        f'<span class="sep">/</span><span>{date}</span>'
        f'</div>'
        f'<div class="story-tags"><span class="story-tag {cat_class}">{cat_display}</span>{new_tag}{manual_tag}</div>'
        f'{reason_html}'
        f'{also_covered_html}</div>'
    )

def render_series_line(story):
    """One-line row for the newest post of a recurring time-series (the
    earlier repeats are suppressed — see rollup_series)."""
    n = story.get('series_size', 1)
    note = ''
    if n > 1:
        note = f' &middot; {n - 1} earlier update{"s" if n > 2 else ""} rolled up'
    dm = re.match(r'(\d{1,2}\s+\w{3})', story.get('date', ''))
    short_date = dm.group(1) if dm else ''
    date_html = f' &middot; {h(short_date)}' if short_date else ''
    return (
        f'<div class="series-line" data-cat="{h(story.get("category", ""))}">'
        f'<span class="series-dot">&#8635;</span>'
        f'<a class="series-hl" href="{h(story.get("url", "#"))}" target="_blank" rel="noopener">'
        f'{h(story.get("headline", ""))}</a>'
        f'<span class="series-meta">{h(story.get("source", ""))}{date_html}{note}</span>'
        f'</div>'
    )

def build_html(clustered_stories, clients_config, generated_at, keywords=None,
               manual_data=None, exec_stories=None, trend_counts=None,
               prev_date=None):
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

    # Executive Summary strip — today's top stories across all clients
    exec_html = ''
    if exec_stories:
        label_map = {c['key']: c['label'] for c in clients_config}
        items = ''
        for i, s in enumerate(exec_stories, 1):
            cat_display = (s.get('category', '') or '').replace('_', ' ').title()
            new_star = '<span class="exec-new">&#9733; new</span> ' if s.get('is_new') else ''
            items += (
                f'<li class="exec-item">'
                f'<span class="exec-num">{i}</span>'
                f'<span class="exec-client">{h(label_map.get(s["client"], s["client"]))}</span>'
                f'<a class="exec-hl" href="{h(s.get("url", "#"))}" target="_blank" rel="noopener">'
                f'{h(s.get("headline", ""))}</a>'
                f'<span class="exec-meta">{new_star}{h(s.get("source", ""))} &middot; {h(cat_display)}</span>'
                f'</li>'
            )
        exec_html = (
            f'<div class="exec"><div class="exec-label">Executive Summary &mdash; top stories today</div>'
            f'<ol class="exec-list">{items}</ol></div>\n'
        )

    # Per-client trend series: archived days + today, excluding low relevance
    trend_counts = trend_counts or {}
    trend_dates  = sorted(trend_counts.keys())
    today_counts = {}
    for s in clustered_stories:
        if s.get('category') != 'low_relevance':
            today_counts[s['client']] = today_counts.get(s['client'], 0) + 1
    total_today = sum(today_counts.values())

    # Build sections — morning-brief-first: every client always gets a section.
    # The default view is NEW-since-last-run cards (or an explicit "no new
    # coverage" line); older stories collapse into "Previously reported";
    # recurring time-series posts render as single rollup lines. Anything
    # low_relevance, capped, or a series repeat never reaches the DOM (it
    # stays in data/latest.json for audit).
    prev_label = f' ({h(prev_date)})' if prev_date else ''
    sections = ''
    for client in clients_config:
        client_key = client['key']
        client_stories = [s for s in clustered_stories if s['client'] == client_key]

        visible = [s for s in client_stories
                   if s.get('category') != 'low_relevance'
                   and not s.get('is_series_repeat')
                   and not s.get('is_capped')]
        leaders = [s for s in visible if s.get('is_series_leader')]
        cards   = [s for s in visible if not s.get('is_series_leader')]
        # Fresh = strictly new-since-last-run. Manual clips are curated
        # history, not this morning's news — their score floor (60) pins
        # them to the top of "Previously reported" instead.
        fresh   = sorted([s for s in cards if s.get('is_new')],
                         key=lambda s: -s.get('score', 0.0))
        fresh_ids = {id(s) for s in fresh}
        older   = sorted([s for s in cards if id(s) not in fresh_ids],
                         key=lambda s: -s.get('score', 0.0))

        if fresh:
            fresh_html = ''.join(
                render_story_card(s, s.get('_cluster_info')) for s in fresh)
        else:
            fresh_html = (
                f'<p class="no-new">No new coverage since the previous brief{prev_label}.</p>'
            )

        prev_html = ''
        if older:
            older_cards = ''.join(
                render_story_card(s, s.get('_cluster_info')) for s in older)
            prev_html = (
                f'<details class="prev-details">'
                f'<summary>Previously reported &middot; '
                f'<span class="prev-count">{len(older)}</span> '
                f'{"story" if len(older) == 1 else "stories"}</summary>'
                f'<div class="prev-body">{older_cards}</div></details>'
            )

        series_html = ''
        if leaders:
            rows = ''.join(render_series_line(s)
                           for s in sorted(leaders, key=lambda x: -x.get('ts', 0)))
            series_html = (
                f'<div class="series-block">'
                f'<div class="series-label">Recurring updates</div>{rows}</div>'
            )

        stories_html = (
            f'<div class="fresh-block">{fresh_html}</div>{series_html}{prev_html}'
        )

        n_today = today_counts.get(client_key, 0)
        sov     = round(100 * n_today / total_today) if total_today else 0
        series  = [trend_counts[d].get(client_key, 0) for d in trend_dates] + [n_today]
        trend_html = (
            f'<span class="sec-trend" title="Stories per day, last {len(series)} day(s) &middot; '
            f'share of voice across clients today">{sparkline_svg(series)}'
            f'<span>{sov}&#37; SOV</span></span>'
        )

        sections += (
            f'<div class="section" id="sec-{client_key}" data-client="{h(client_key)}">'
            f'<div class="sec-head">'
            f'<span class="sec-name">{h(client["label"])}</span>'
            f'<span class="sec-tag">{h(client.get("sector", ""))}</span>'
            f'<span class="sec-rule"></span>'
            f'{trend_html}'
            f'<span class="sec-count"></span>'
            f'</div>'
            f'<div>{stories_html}</div>'
            f'</div>'
        )
    
    # Flatten clustered stories for JSON embedding
    flat_stories = []
    for cs in clustered_stories:
        flat_story = {k: v for k, v in cs.items() if k != '_cluster_info'}
        ci = cs.get('_cluster_info')
        flat_story['also_covered_by'] = [
            {'source': x.get('source'), 'url': x.get('url'), 'date': x.get('date'), 'ts': x.get('ts', 0)}
            for x in (ci.get('also_covered_by', []) if ci else [])
        ]
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
        '          <div class="clip-row"><span class="clip-label">Coverage URLs</span>'
        '<textarea class="clip-textarea" id="clip-coverage-urls" style="min-height:64px;" '
        'placeholder="Paste other outlet URLs that covered this story — one per line. These appear as linked chips on the card."></textarea></div>\n'
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

        f'{exec_html}'
        '<div class="controls">\n'
        '  <div class="ctrl-group"><span class="ctrl-label">Window</span>\n'
        '  <button class="ctrl-btn" data-win="1d" onclick="setWin(\'1d\')">1d</button>\n'
        '  <button class="ctrl-btn" data-win="7d" onclick="setWin(\'7d\')">7d</button>\n'
        '  <button class="ctrl-btn" data-win="14d" onclick="setWin(\'14d\')">14d</button>\n'
        '  <button class="ctrl-btn active" data-win="30d" onclick="setWin(\'30d\')">30d</button></div>\n'
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
        '  <button class="ctrl-btn" style="margin-left:6px;" '
        'onclick="printCoverage()" title="Print or save all coverage as PDF">&#x2399; Coverage PDF</button>'
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
    # Global safety net: no socket operation anywhere (urllib, feedparser
    # internals, redirect resolution) may block longer than this.
    socket.setdefaulttimeout(30)
    print('Morning Brief — Starting\n')

    generated_at = datetime.now(timezone.utc)
    cutoff_dt    = generated_at - timedelta(days=WINDOW_DAYS)
    cutoff_ms    = int(cutoff_dt.timestamp() * 1000)

    # Load configurations
    keywords = load_json('keywords.json', {})
    outlets_config = load_json('outlets.json', {})

    # ── Validate CLIENTS ↔ keywords.json consistency ──────────────────────────
    # Adding a client should be a two-step paste (keywords.json block + CLIENTS
    # entry). Warn loudly if the two drift apart so a half-added client is caught
    # at startup instead of silently fetching nothing.
    client_keys = {c['key'] for c in CLIENTS}
    kw_keys     = set(keywords.keys())
    for k in sorted(kw_keys - client_keys):
        print(f'  ⚠ keywords.json defines "{k}" but config.py CLIENTS has no such key — it will be ignored')
    for k in sorted(client_keys - kw_keys):
        print(f'  ⚠ CLIENTS lists "{k}" but keywords.json has no block for it — that client will fetch nothing')
    if client_keys == kw_keys:
        print(f'Config OK — {len(client_keys)} clients aligned between config.py and keywords.json')
    print()

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

    # ── Fetch direct outlet feeds (bypasses Google News indexing gaps) ────────
    print('Direct outlet feeds')
    for feed in DIRECT_FEEDS:
        items   = fetch_outlet_feed(feed, cutoff_ms)
        matched = match_feed_items_to_clients(items, keywords)
        sys.stdout.write(f'    ✓ {len(items)} items · {len(matched)} matched to clients\n')
        sys.stdout.flush()
        all_stories.extend(matched)
    print()

    print(f'Total stories before processing: {len(all_stories)}')

    run_pipeline(all_stories, generated_at, keywords, outlets_config)


def run_pipeline(all_stories, generated_at, keywords, outlets_config, replay=False):
    """
    Everything downstream of fetching: classify → cluster → resolve URLs →
    NEW-marking → series rollup → compound scoring → category caps → alerts →
    executive summary → render → archive. Shared verbatim by the live run
    (main) and the offline replay harness (replay_main), so a replayed brief
    exercises the exact production path.
    """
    # ── Classify stories (headlines de-boilerplated first) ────────────────────
    print('Classifying stories...')
    for story in all_stories:
        story['headline'] = strip_headline_boilerplate(story.get('headline', ''))
        story['snippet']  = strip_headline_boilerplate(story.get('snippet', ''))
        client_key = story['client']
        client_config = keywords.get(client_key, {})
        fetch_type = story.get('fetch_type', 'direct_mentions')
        category, relevance, matched = classify_story(
            story, client_config, outlets_config, fetch_type_hint=fetch_type,
            global_exclude=GLOBAL_EXCLUDE)
        story['category'] = category
        story['relevance_score'] = relevance
        story['matched_terms'] = matched
        # Use name-based rank for Google News stories (domain is news.google.com
        # before URL resolution, so domain-only lookup always returns rank 4).
        story['source_rank'] = effective_source_rank(story, outlets_config)

    # ── Merge manual clippings (pre-classified, injected after auto-classify) ─
    manual_data = load_json('manual_articles.json', {'articles': []})
    manual_articles = manual_data.get('articles', [])
    for art in manual_articles:
        art['is_manual']             = True
        art['is_low_relevance']      = False
        art['is_primary_in_cluster'] = True
        art['cluster_id']            = art.get('id', f'manual_{art.get("ts",0)}')
        art['category']              = art.get('category') or 'mention'
        art['relevance_score']       = art.get('relevance_score', 1.0)
        art['matched_terms']         = art.get('matched_terms', ['manual'])
        art['source_rank']           = effective_source_rank(art, outlets_config)
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
    clusters = cluster_stories(all_stories, outlets_config)

    # Merge coverage URLs manually specified on a manual clip into its cluster.
    # These links were pasted by the user when adding the clip and represent
    # outlets the auto-fetcher may not have seen.
    for cluster in clusters:
        primary = cluster['primary']
        if primary.get('is_manual') and primary.get('also_covered_by'):
            existing = {x.get('url') for x in cluster.get('also_covered_by', [])}
            for cov in primary['also_covered_by']:
                if cov.get('url') and cov['url'] not in existing:
                    cluster['also_covered_by'].append({
                        'source':  cov.get('source', extract_domain(cov.get('url', ''))),
                        'url':     cov.get('url', ''),
                        'domain':  extract_domain(cov.get('url', '')),
                        'headline': '',
                        'date':    cov.get('date', ''),
                        'ts':      cov.get('ts', 0),
                    })
                    existing.add(cov['url'])

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

    # ── Resolve Google News redirect URLs to real publisher URLs ──────────────
    # Stored links are opaque news.google.com/rss/articles/CBMi... redirects that
    # break if Google changes its format. Resolve the displayed set (primaries +
    # "also covered by" chips) within a 90s overall budget; cluster_id carries
    # new-since-yesterday continuity so changing URLs here won't reset NEW badges.
    if replay:
        print('Replay mode — skipping Google News link resolution (offline)')
    else:
        print('Resolving Google News links...')
        _RESOLVE_DEADLINE['t'] = time.monotonic() + 90
        n_resolved = 0
        for s in clustered_stories:
            if s.get('domain') == 'news.google.com':
                real = resolve_google_url(s.get('url', ''))
                if real != s.get('url'):
                    s['url']    = real
                    s['domain'] = extract_domain(real)
                    s['source_rank'] = source_rank(s['domain'], outlets_config)
                    n_resolved += 1
            ci = s.get('_cluster_info')
            if ci:
                for chip in ci.get('also_covered_by', []):
                    if chip.get('domain') == 'news.google.com':
                        real = resolve_google_url(chip.get('url', ''))
                        if real != chip.get('url'):
                            chip['url']    = real
                            chip['domain'] = extract_domain(real)
        print(f'Resolved {n_resolved} Google News links to publisher URLs')

    # ── Mark new-since-yesterday stories ──────────────────────────────────────
    today_iso = generated_at.astimezone(SL_TZ).date().isoformat()
    prev_urls, prev_cids, prev_date = load_previous_story_keys(today_iso)
    for s in clustered_stories:
        s['is_new'] = bool(prev_date) and \
            s.get('url') not in prev_urls and \
            s.get('cluster_id') not in prev_cids
    n_new = sum(1 for s in clustered_stories if s['is_new'])
    if prev_date:
        print(f'New since {prev_date}: {n_new} stories')

    # ── Series rollup, compound scores, category caps ─────────────────────────
    # Recurring data-point posts (daily CBSL rate etc.) collapse to their
    # newest item; every story gets a compound ordering score; filler-prone
    # categories are capped per client with the best-scored cards surviving.
    now_ms = int(generated_at.timestamp() * 1000)
    n_suppressed = rollup_series(clustered_stories, SERIES_PATTERNS)
    if n_suppressed:
        print(f'Series rollup: {n_suppressed} recurring repeat(s) suppressed')
    for s in clustered_stories:
        s['score'] = compound_score(s, now_ms)
    n_capped = apply_category_caps(clustered_stories, CATEGORY_CAPS, now_ms)
    if n_capped:
        print(f'Category caps: {n_capped} filler card(s) capped')

    # Final order everywhere (page JSON, sections, coverage PDF): manual clips
    # first, then compound score, then recency.
    clustered_stories.sort(key=lambda s: (
        -int(s.get('is_manual', False)),
        -s.get('score', 0.0),
        -s.get('ts', 0),
    ))

    # ── Risk alerts: new risk_watch stories → data/alerts.json ────────────────
    # The GitHub Action opens an issue when alert_count > 0.
    label_map = {c['key']: c['label'] for c in CLIENTS}
    new_risk = [s for s in clustered_stories
                if s.get('category') == 'risk_watch' and s.get('is_new')
                and not s.get('is_series_repeat')]
    alerts = [{
        'client':       s['client'],
        'client_label': label_map.get(s['client'], s['client']),
        'headline':     s.get('headline', ''),
        'url':          s.get('url', ''),
        'source':       s.get('source', ''),
        'date':         s.get('date', ''),
    } for s in new_risk]
    issue_lines = [f'New risk_watch stories detected by the Morning Brief (vs {prev_date}):', '']
    issue_lines += [
        f'- **[{a["client_label"]}]** [{a["headline"]}]({a["url"]}) — {a["source"]} ({a["date"]})'
        for a in alerts
    ]
    save_json('data/alerts.json', {
        'generated_at': generated_at.isoformat(),
        'compared_to':  prev_date,
        'alert_count':  len(alerts),
        'alerts':       alerts,
        'issue_body':   '\n'.join(issue_lines) if alerts else '',
    })
    if new_risk:
        print(f'⚠ {len(new_risk)} new risk story(ies) → data/alerts.json')

    # ── Executive summary + trend data ────────────────────────────────────────
    exec_stories = pick_executive_stories(clustered_stories)
    trend_counts = load_trend_counts([c['key'] for c in CLIENTS], today_iso)

    # ── Generate HTML ────────────────────────────────────────────────────────
    print('Building HTML...')
    page = build_html(clustered_stories, CLIENTS, generated_at,
                      keywords=keywords, manual_data=manual_data,
                      exec_stories=exec_stories, trend_counts=trend_counts,
                      prev_date=prev_date)

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
    save_archive(clustered_stories, clusters,
                 generated_at=generated_at, write_dated=not replay)
    if not replay:
        pruned = prune_old_archives(keep_days=90)
        if pruned:
            print(f'Pruned {pruned} archive file(s) older than 90 days')

    print(f'Done — {OUTPUT_FILE} written ({len(page):,} bytes)')
    if replay:
        print('Done — data/latest.json updated (replay: dated archives untouched)')
    else:
        print(f'Done — data/latest.json and data/archive/ updated')
    print()


# ── Offline replay harness ────────────────────────────────────────────────────
# `python brief.py --replay [YYYY-MM-DD]` regenerates a past morning's brief
# entirely from data/archive/*.json — no network. Raw stories are rebuilt from
# the archived runs and pushed through the identical run_pipeline() the live
# GitHub Action uses, so classification/scoring/rollup/render changes can be
# verified end to end offline (see replay_checks.py for the assertion suite).

# Base fields carried back from an archived story into the raw pool. All
# derived fields (category, scores, cluster ids, is_new, flags) are dropped —
# the pipeline re-derives them.
REPLAY_BASE_KEYS = ('client', 'headline', 'url', 'source', 'domain',
                    'date', 'ts', 'snippet', 'fetch_type')

def load_replay_pool(replay_date, archive_dir='data/archive'):
    """
    Rebuild the raw story pool for replay_date from that date's archive. A
    live run fetches a full 30-day window every morning, so the day's archive
    IS that morning's fetch result — pooling in older archives would inject
    stories the live fetch never returned and corrupt the NEW-since-yesterday
    comparison. Archived stories become raw again (derived fields dropped —
    the pipeline re-derives them), deduped per (client, url) and gated to the
    same fetch window as a live run. Returns (stories, generated_at).
    """
    day_data = load_json(str(Path(archive_dir) / f'{replay_date}.json'), {})
    if not day_data.get('generated_at'):
        raise SystemExit(f'✗ No usable archive for {replay_date} in {archive_dir}/')
    generated_at = datetime.fromisoformat(day_data['generated_at'])
    cutoff_ms = int((generated_at - timedelta(days=WINDOW_DAYS)).timestamp() * 1000)

    pool, seen = [], set()
    for s in day_data.get('stories', []):
        if s.get('is_manual'):
            continue   # manual clips re-merge from manual_articles.json
        raw = {k: s[k] for k in REPLAY_BASE_KEYS if s.get(k) is not None}
        raw.setdefault('fetch_type', 'direct_mentions')
        raw.setdefault('snippet', '')
        ts = raw.get('ts') or 0
        if ts and ts < cutoff_ms:
            continue
        key = (raw.get('client'), raw.get('url') or 'hl:' + (raw.get('headline') or ''))
        if key in seen:
            continue
        seen.add(key)
        pool.append(raw)
    return pool, generated_at

def replay_main(replay_date=None):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('Morning Brief — offline replay\n')

    dates = sorted(p.stem for p in Path('data/archive').glob('*.json'))
    if not dates:
        raise SystemExit('✗ data/archive/ has no archives to replay')
    if replay_date is None:
        replay_date = dates[-1]
    if replay_date not in dates:
        raise SystemExit(f'✗ No archive for {replay_date} '
                         f'(available: {dates[0]} … {dates[-1]})')

    keywords = load_json('keywords.json', {})
    outlets_config = load_json('outlets.json', {})

    pool, generated_at = load_replay_pool(replay_date)
    print(f'Replaying {replay_date} — {len(pool)} raw stories '
          f'reconstructed from its archived run\n')

    run_pipeline(pool, generated_at, keywords, outlets_config, replay=True)


if __name__ == '__main__':
    if '--replay' in sys.argv:
        idx = sys.argv.index('--replay')
        date_arg = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None
        replay_main(date_arg)
    else:
        main()
