#!/usr/bin/env python3
"""Import public web evidence the Agent found with host search/fetch tools.

Use when a social adapter is blocked or a site has no adapter (complaint boards,
forums, Q&A, news comments). Each line of the input JSONL is one quoted original
the Agent actually read on a public page:
  {"site": "黑猫投诉", "url": "https://...", "title": "...", "body": "<exact original text>",
   "published_at": "2026-09-01T00:00:00+08:00" | null, "kind": "post"|"comment", "parent_url": optional}
This validates and normalises; it never fetches pages or invents missing fields.
"""
import sys
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def now():
    return datetime.now(timezone.utc).isoformat()


def iso(value):
    if not value:return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:return None
    return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None


def convert(rows, app):
    out = {};errors = []
    for n, row in enumerate(rows, 1):
        url = row.get('url') or '';parsed = urlparse(url)
        body = (row.get('body') or '').strip()
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
            errors.append(dict(line=n, reason='needs_public_http_url'));continue
        if not body:errors.append(dict(line=n, reason='empty_body'));continue
        kind = row.get('kind') if row.get('kind') in ('post', 'comment') else 'comment'
        rid = hashlib.sha256((url + '\n' + body).encode()).hexdigest()[:20]
        parent = hashlib.sha256(row['parent_url'].encode()).hexdigest()[:20] if row.get('parent_url') else None
        out[rid] = dict(platform='web', kind=kind, id=rid, post_id=parent or rid, site=row.get('site') or parsed.netloc,
            level=None if kind == 'post' else 1, root_id=parent or rid, parent_id=parent, reply_to_id=None,
            parent_relation='page_container' if parent else 'top_level', app=app, title=row.get('title'), body=body,
            # A display date without timezone stays unknown rather than guessed.
            published_at=iso(row.get('published_at')), published_at_display=row.get('published_at_display'),
            retrieved_at=row.get('retrieved_at') or now(), source_url=url, client=row.get('client') or 'unknown',
            context_status='public_page_excerpt', acquisition='agent_public_web_read')
    return list(out.values()), errors


def latest_file(output_root, app):
    f = Path(output_root) / 'web' / ('latest-' + hashlib.sha256(app.encode()).hexdigest()[:12] + '.json')
    if not f.exists():return None
    path = Path(json.loads(f.read_text(encoding='utf-8'))['path'])
    return path if path.exists() else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path);p.add_argument('--app', required=True);p.add_argument('--output', type=Path)
    a = p.parse_args()
    rows = [json.loads(x) for x in a.input.read_text(encoding='utf-8').splitlines() if x.strip()]
    records, errors = convert(rows, a.app)
    root = Path(json.loads((Path(__file__).resolve().parents[1] / 'runtime.json').read_text(encoding='utf-8'))['output']) / 'web'
    out = a.output or root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-web.jsonl')
    out.parent.mkdir(parents=True, exist_ok=True)
    # Merge with the previous import for this App so repeated imports accumulate.
    previous = latest_file(root.parent, a.app)
    merged = {}
    if previous and previous != out:
        for line in previous.read_text(encoding='utf-8').splitlines():
            if line.strip():r = json.loads(line);merged[r['id']] = r
    merged.update({r['id']: r for r in records})
    out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in merged.values()),encoding='utf-8')
    root.mkdir(parents=True, exist_ok=True)
    (root / ('latest-' + hashlib.sha256(a.app.encode()).hexdigest()[:12] + '.json')).write_text(json.dumps(dict(app=a.app, path=str(out)), ensure_ascii=False) + '\n',encoding='utf-8')
    print(json.dumps(dict(output=str(out), imported=len(records), total=len(merged), rejected=errors), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
