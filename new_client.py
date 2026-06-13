#!/usr/bin/env python3
"""
new_client.py — scaffold a new Morning Brief client.

Adding a client to the pipeline is intentionally a TWO-STEP paste job, no code
changes required:

  1. Paste the printed block into keywords.json
  2. Paste the printed entry into the CLIENTS list in config.py

This script prints both, pre-filled with sensible empty defaults.

Usage:
    py -3 new_client.py "Cinnamon Hotels" "Hospitality"
    py -3 new_client.py "Cinnamon Hotels" "Hospitality" --key cinnamon
    py -3 new_client.py "Cinnamon Hotels" "Hospitality" --context "Sri Lanka"

The --context flag sets query_context: for short/ambiguous brand names it is
ANDed with the OR-group at fetch time (e.g. ("BYD") "Sri Lanka") so the RSS feed
isn't flooded with global results. Long, already-SL-specific names can omit it.
"""

import json
import re
import sys

# What each keywords.json field is for (printed as a guide, since JSON itself
# can't carry comments).
FIELD_HELP = [
    ("label",           "Display name shown in the brief."),
    ("sector",          "Industry grouping; also the section chip."),
    ("query_context",   'ANDed with brand terms for short/ambiguous names, e.g. "Sri Lanka". Leave "" if the names are already unambiguous.'),
    ("direct_mentions", "Exact brand / subsidiary / product names. A hit here = Mention (the client itself is in the news)."),
    ("industry_watch",  "Sector, regulator and named-competitor terms. A hit here = Industry context."),
    ("market_watch",    "Stock-market / bourse terms. Usually empty unless the client is listed and you track its ticker."),
    ("risk_watch",      "Negative / crisis terms (recall, fraud, ban, investigation). Checked BEFORE mentions so bad news is never buried."),
    ("exclude",         "False-positive killers (sports, cricket, school...). Matching ANY of these demotes the story to low_relevance."),
    ("priority_sources","Preferred outlets for this client (display/ranking hint)."),
]

DEFAULT_PRIORITY_SOURCES = [
    "Daily FT", "Daily Mirror", "The Island", "EconomyNext", "Newswire",
]


def make_key(name):
    """Derive a short lowercase key from the client name."""
    first = re.sub(r'[^a-z0-9]', '', name.split()[0].lower()) if name.split() else ''
    return first or re.sub(r'[^a-z0-9]', '', name.lower())[:8] or 'client'


def make_client_template(name, sector, key=None, context='Sri Lanka'):
    """
    Return (key, keywords_block_dict, clients_entry_dict) for a new client.

    keywords_block_dict is shaped exactly like one top-level entry in
    keywords.json; clients_entry_dict is the {key,label,sector} row for
    config.py's CLIENTS list.
    """
    key = key or make_key(name)
    keywords_block = {
        key: {
            "label":            name,
            "sector":           sector,
            "query_context":    context,
            "direct_mentions":  [name],
            "industry_watch":   [],
            "market_watch":     [],
            "risk_watch":       [],
            "exclude":          [],
            "priority_sources": list(DEFAULT_PRIORITY_SOURCES),
        }
    }
    clients_entry = {"key": key, "label": name, "sector": sector}
    return key, keywords_block, clients_entry


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    flags = {a.split('=', 1)[0][2:]: (a.split('=', 1)[1] if '=' in a else True)
             for a in argv if a.startswith('--')}

    # Support both `--key cinnamon` and `--key=cinnamon`.
    out = []
    i = 0
    raw = list(argv)
    while i < len(raw):
        tok = raw[i]
        if tok.startswith('--') and '=' not in tok and i + 1 < len(raw) and not raw[i + 1].startswith('--'):
            flags[tok[2:]] = raw[i + 1]
            i += 2
            continue
        if not tok.startswith('--'):
            out.append(tok)
        i += 1
    positional = out

    if len(positional) < 2:
        print(__doc__)
        print('ERROR: need a client name and a sector.\n'
              '  py -3 new_client.py "Cinnamon Hotels" "Hospitality"')
        return 1

    name, sector = positional[0], positional[1]
    key = flags.get('key')
    context = flags.get('context', 'Sri Lanka')

    key, kw_block, clients_entry = make_client_template(name, sector, key=key, context=context)

    print('=' * 70)
    print(f'New client scaffold: {name}  (key="{key}", sector="{sector}")')
    print('=' * 70)

    print('\nField guide:')
    for field, desc in FIELD_HELP:
        print(f'  - {field:<16} {desc}')

    print('\n' + '-' * 70)
    print('STEP 1 - paste into keywords.json (inside the top-level object):')
    print('-' * 70)
    # Dump just the client's value and re-indent continuation lines by two
    # spaces so it drops straight into the existing top-level object.
    val = json.dumps(kw_block[key], indent=2, ensure_ascii=False)
    val_indented = val.replace('\n', '\n  ')
    print(f'  "{key}": {val_indented},')

    print('\n' + '-' * 70)
    print('STEP 2 - paste into the CLIENTS list in config.py:')
    print('-' * 70)
    print(f"    {{'key': {key!r}, 'label': {name!r}, 'sector': {sector!r}}},")

    print('\nDone. No other code changes are needed - run `py -3 brief.py` to verify.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
