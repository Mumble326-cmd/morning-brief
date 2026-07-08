#!/usr/bin/env python3
"""
replay_checks.py — offline assertion suite for the Morning Brief.

Replays an archived morning (default: the newest archive) through the FULL
production pipeline via `python brief.py --replay`, then asserts the product
guarantees of the 2026-07-07 relevance overhaul against the regenerated
replay_output/index.html + replay_output/latest.json:

  1. no low_relevance story card in the rendered page
  2. no capped filler card in the rendered page, and no client section
     exceeds the per-category caps (config.CATEGORY_CAPS)
  3. sports junk (e.g. the LOLC cricket story) never renders under a client
  4. recurring time-series posts (daily CBSL rate etc.) are rolled up to at
     most one line, repeats suppressed — and digit-signature rollup never
     demotes a Mention (only explicit SERIES_PATTERNS may)
  5. the executive summary strip is present and populated
  6. every client has a section containing either new coverage or an
     explicit "No new coverage" line; on a first run (no earlier archive)
     every story is NEW and no "since the previous brief" wording appears
  7. outlet boilerplate is stripped from rendered headlines
  8. replay never touches the committed index.html / data/latest.json /
     data/alerts.json (outputs go to replay_output/)

Also unit-checks the Google News query construction offline: every query
built from keywords.json stays within brief.QUERY_ENCODED_BUDGET and no
term is lost when a keyword list is split across multiple fetches.

Exits 0 when everything holds, 1 otherwise.

Run:  python3 replay_checks.py [YYYY-MM-DD]
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from config import CLIENTS, CATEGORY_CAPS
import brief

FAILURES = []

def check(ok, label, detail=''):
    mark = 'ok' if ok else 'FAIL'
    print(f'  [{mark:4}] {label}' + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        FAILURES.append(label)

def file_hash(path):
    p = Path(path)
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None

def rendered_dom(html):
    """The visible document — everything before the embedded JSON blobs."""
    return html.split('<script id="story-data"', 1)[0]

def client_sections(dom):
    """Split the DOM into {client_key: section_html}."""
    sections = {}
    marks = [(m.group(1), m.start())
             for m in re.finditer(r'<div class="section" id="sec-(\w+)"', dom)]
    for i, (key, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(dom)
        sections[key] = dom[start:end]
    return sections

def check_query_splitting(keywords):
    """Offline unit checks for build_queries (no network needed)."""
    budget = brief.QUERY_ENCODED_BUDGET
    for ckey, cfg in keywords.items():
        ctx = cfg.get('query_context', '')
        for mode in ('direct_mentions', 'industry_watch', 'market_watch', 'risk_watch'):
            terms = cfg.get(mode, [])
            if not terms:
                continue
            queries = brief.build_queries(
                terms, context=ctx if mode == 'direct_mentions' else None)
            over = [q for q in queries if brief._encoded_query_len(q) > budget]
            check(not over,
                  f'{ckey}/{mode}: {len(queries)} quer(ies) within the '
                  f'{budget}-char encoded budget',
                  f'{len(over)} over budget')
            joined = ' '.join(queries)
            missing = [t for t in terms if f'"{t}"' not in joined]
            check(not missing, f'{ckey}/{mode}: no term lost by splitting',
                  f'missing {missing}')
    # The tuned HNB industry list is the one that outgrew a single query.
    hnb_industry = brief.build_queries(
        keywords.get('hnb', {}).get('industry_watch', []))
    check(len(hnb_industry) >= 2,
          'HNB industry_watch splits into multiple fetches',
          f'got {len(hnb_industry)} query')

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    dates = sorted(p.stem for p in Path('data/archive').glob('*.json'))
    if not dates:
        print('✗ no archives available to replay'); sys.exit(1)
    if date is None:
        date = dates[-1]
    has_prev_archive = any(d < date for d in dates)

    tracked = ['index.html', 'data/latest.json', 'data/alerts.json']
    before = {p: file_hash(p) for p in tracked}

    print(f'Replaying {date} through brief.py --replay ...')
    r = subprocess.run([sys.executable, 'brief.py', '--replay', date],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        print('✗ replay run failed'); sys.exit(1)

    html = Path('replay_output/index.html').read_text(encoding='utf-8')
    data = json.loads(Path('replay_output/latest.json').read_text(encoding='utf-8'))
    stories = data.get('stories', [])
    dom = rendered_dom(html)
    sections = client_sections(dom)

    print(f'\nChecks against the regenerated brief ({len(stories)} stories in JSON):')

    # 8 ── replay must not touch the committed artifacts
    for p in tracked:
        check(file_hash(p) == before[p],
              f'replay left {p} untouched (outputs in replay_output/)')

    # 1 ── low_relevance never renders (but stays in JSON for audit)
    check('data-cat="low_relevance"' not in dom,
          'no low_relevance card in the rendered page')
    n_lowrel = sum(1 for s in stories if s.get('category') == 'low_relevance')
    if n_lowrel:
        print(f'  [ok  ] {n_lowrel} low_relevance stories retained in latest.json for audit')
    else:
        print('  [skip] no low_relevance stories this day — nothing to audit')

    # 2 ── caps respected in the DOM; capped stories flagged in JSON only
    for c in CLIENTS:
        sec = sections.get(c['key'], '')
        for cat, cap in CATEGORY_CAPS.items():
            n = len(re.findall(rf'<div class="story"[^>]*data-cat="{cat}"', sec))
            check(n <= cap,
                  f'{c["label"]}: {cat} cards within cap',
                  f'{n} rendered > cap {cap}')
    for s in stories:
        if s.get('is_capped'):
            check(f'>{s["headline"]} <' not in dom.replace('&amp;', '&'),
                  f'capped story stays out of the page: {s["headline"][:60]}')

    # 3 ── sports junk never sits in a client section
    check('Bowlers star in LOLC' not in sections.get('mas', ''),
          'LOLC cricket story not rendered under MAS')
    check('Bowlers star in LOLC' not in dom,
          'LOLC cricket story not rendered anywhere')

    # 4 ── recurring time-series posts rolled up to at most one line
    repeats = [s for s in stories if s.get('is_series_repeat')]
    leaders = [s for s in stories if s.get('is_series_leader')]
    rate_posts = [s for s in stories
                  if re.search(r'\bcbsl rates?\b', s.get('headline', ''), re.I)]
    if rate_posts:
        n_rate_dom = len(re.findall(r'\bCBSL rates?\b', dom, re.I))
        check(n_rate_dom <= 1,
              'daily CBSL rate posts appear at most once on the page',
              f'{n_rate_dom} occurrences')
        check(len(rate_posts) == 1 or len(repeats) >= 1,
              'repeated rate posts are flagged is_series_repeat in JSON')
    for s in repeats:
        check(s['headline'] not in dom.replace('&amp;', '&'),
              f'series repeat suppressed: {s["headline"][:60]}')
    for s in leaders:
        check('class="series-line"' in dom,
              'series leaders render as one-line recurring updates')
        break
    # Digit-signature grouping must never demote a Mention — only the
    # explicit SERIES_PATTERNS regexes may roll up a client's own coverage.
    bad_mentions = [s for s in stories
                    if s.get('category') == 'mention'
                    and str(s.get('series_key', '')).startswith('sig:')]
    check(not bad_mentions,
          'no Mention demoted by digit-signature series grouping',
          '; '.join(s['headline'][:50] for s in bad_mentions))

    # 5 ── executive summary present and populated
    n_exec = len(re.findall(r'<li class="exec-item">', dom))
    check('Executive Summary' in dom, 'executive summary strip present')
    check(n_exec >= 3, 'executive summary populated (>= 3 items)',
          f'only {n_exec} items')

    # 6 ── every client gets a section: new cards or explicit no-news line
    for c in CLIENTS:
        sec = sections.get(c['key'], '')
        check(bool(sec), f'{c["label"]}: section present')
        if not sec:
            continue
        fresh = sec.split('<div class="fresh-block">', 1)
        fresh = fresh[1] if len(fresh) > 1 else ''
        for stop in ('<div class="series-block">', '<details'):
            fresh = fresh.split(stop, 1)[0]
        has_new_cards = '<div class="story"' in fresh
        has_no_new_line = 'class="no-new"' in fresh
        check(has_new_cards != has_no_new_line,
              f'{c["label"]}: fresh block has new cards XOR explicit no-new line',
              f'cards={has_new_cards} no_new={has_no_new_line}')
    if not has_prev_archive:
        # First-run semantics: no baseline → everything is new, nothing may
        # claim "no new coverage since the previous brief" or sit collapsed.
        check(all(s.get('is_new') for s in stories),
              'first run: every story marked new')
        check('since the previous brief' not in dom,
              'first run: no "since the previous brief" wording')
        check('<details' not in dom,
              'first run: nothing collapsed into "Previously reported"')
        if date == '2026-06-11':
            card_headlines = ' '.join(
                re.findall(r'<a class="story-hl"[^>]*>(.*?)</a>', dom, re.S))
            check('HNB Finance records exceptional' in card_headlines,
                  'HNB Finance FY results renders as a real card (not a series line)')

    # 7 ── headline boilerplate stripped
    check('Print Edition' not in dom,
          'no "Print Edition" boilerplate in rendered page')
    check('| Daily Mirror' not in dom,
          'no "| Daily Mirror" boilerplate in rendered page')

    # ── Google News query construction stays within the encoded budget ──────
    print('\nOffline query-splitting checks (no network):')
    keywords = json.loads(Path('keywords.json').read_text(encoding='utf-8'))
    check_query_splitting(keywords)

    print()
    if FAILURES:
        print(f'✗ {len(FAILURES)} check(s) FAILED')
        sys.exit(1)
    print('✓ all checks passed')
    sys.exit(0)


if __name__ == '__main__':
    main()
