#!/usr/bin/env python3
"""Collect public Apple App Store (China storefront) reviews via the iTunes RSS feed.

No login or browser. The feed exposes at most 10 pages x 50 newest reviews per
App and sort order. Every review carries its App version, so records are labelled
client=ios with a source-stated version. iOS evidence is kept separate from the
default Android scope; it is never relabelled as Android.
"""
import sys
import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'


def now():
    return datetime.now(timezone.utc).isoformat()


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=25) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def resolve(app, country='cn'):
    data = get('https://itunes.apple.com/search?' + urllib.parse.urlencode(dict(term=app, country=country, entity='software', limit=8)))
    return [dict(track_id=str(r['trackId']), name=r['trackName'], bundle_id=r.get('bundleId'), version=r.get('version'),
                 rating_count=r.get('userRatingCount'), seller=r.get('sellerName')) for r in data.get('results', [])]


def choose(app, candidates):
    named = [c for c in candidates if c['name'] == app or c['name'].startswith(app + '—') or c['name'].startswith(app + ' ') or c['name'].startswith(app + '-')]
    pick = named or candidates[:1]
    if len(named) > 1:pick = sorted(named, key=lambda c: -(c['rating_count'] or 0))
    if not pick:raise SystemExit(json.dumps({'error': 'no_listing', 'app': app}, ensure_ascii=False))
    return pick[0]


def collect(args):
    listing = dict(track_id=args.track_id, name=args.app) if args.track_id else choose(args.app, resolve(args.app, args.country))
    rows = {};pages = [];stop = 'feed_page_limit'
    for sort in args.sort:
        for n in range(1, args.max_pages + 1):
            time.sleep(args.delay)
            url = f"https://itunes.apple.com/{args.country}/rss/customerreviews/page={n}/id={listing['track_id']}/sortby={sort}/json"
            try:feed = get(url).get('feed', {})
            except Exception as exc:
                pages.append(dict(sort=sort, page=n, error=type(exc).__name__));stop = 'request_failed';break
            entries = feed.get('entry') or []
            entries = entries if isinstance(entries, list) else [entries]
            entries = [e for e in entries if 'content' in e and 'im:rating' in e]
            fresh = 0
            for e in entries:
                rid = e['id']['label']
                if rid in rows:continue
                fresh += 1
                published = e.get('updated', {}).get('label')
                try:published = datetime.fromisoformat(published).astimezone(timezone.utc).isoformat()
                except (TypeError, ValueError):published = None
                rows[rid] = dict(platform='appstore', kind='comment', id=rid, post_id=listing['track_id'], level=1, root_id=rid,
                    parent_id=None, reply_to_id=None, parent_relation='top_level', app=args.app,
                    title=e.get('title', {}).get('label'), body=e['content']['label'], rating=int(e['im:rating']['label']),
                    version=e.get('im:version', {}).get('label'), client='ios', client_basis='source_stated_store',
                    published_at=published, retrieved_at=now(), sort=sort,
                    source_url=f"https://apps.apple.com/{args.country}/app/id{listing['track_id']}?see-all=reviews",
                    author_hash=hashlib.sha256(('appstore:' + e.get('author', {}).get('name', {}).get('label', '')).encode()).hexdigest()[:16],
                    context_status='store_review_no_replies')
            pages.append(dict(sort=sort, page=n, returned=len(entries), new=fresh))
            if not entries:stop = 'source_end_confirmed';break
    out = Path(args.output) if args.output else Path(json.loads((Path(__file__).resolve().parents[1] / 'runtime.json').read_text(encoding='utf-8'))['output']) / 'appstore' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + listing['track_id'])
    out.mkdir(parents=True, exist_ok=True)
    records = sorted(rows.values(), key=lambda r: r['published_at'] or '', reverse=True)
    with (out / 'records.jsonl').open('w',encoding='utf-8') as f:
        for r in records:f.write(json.dumps(r, ensure_ascii=False) + '\n')
    meta = dict(app=args.app, listing=listing, completed_at=now(), country=args.country, records=len(records), pages=pages, stop_reason=stop,
        limitations=['RSS exposes at most 500 newest reviews per sort order; older reviews are not reachable here.',
                     'iOS reviews: excluded from an Android-only scope unless the scope includes ios or all.'])
    (out / 'manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    # Only default-location runs become the App's latest pointer; explicit --output stays standalone.
    if not args.output:(out.parent / ('latest-' + hashlib.sha256(args.app.encode()).hexdigest()[:12] + '.json')).write_text(json.dumps(dict(app=args.app, path=str(out)), ensure_ascii=False) + '\n',encoding='utf-8')
    print(json.dumps(dict(output=str(out), listing=listing, records=len(records), stop_reason=stop,
        newest=records[0]['published_at'] if records else None, oldest=records[-1]['published_at'] if records else None), ensure_ascii=False, indent=2))


def latest_dir(output_root, app):
    f = Path(output_root) / 'appstore' / ('latest-' + hashlib.sha256(app.encode()).hexdigest()[:12] + '.json')
    if not f.exists():return None
    path = Path(json.loads(f.read_text(encoding='utf-8'))['path'])
    return path if (path / 'records.jsonl').exists() else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    r = sub.add_parser('resolve');r.add_argument('--app', required=True);r.add_argument('--country', default='cn')
    c = sub.add_parser('collect');c.add_argument('--app', required=True);c.add_argument('--track-id')
    c.add_argument('--country', default='cn');c.add_argument('--max-pages', type=int, default=10)
    c.add_argument('--sort', nargs='+', default=['mostrecent', 'mosthelpful'], choices=['mostrecent', 'mosthelpful'])
    c.add_argument('--delay', type=float, default=0.8);c.add_argument('--output')
    a = p.parse_args()
    if a.command == 'resolve':print(json.dumps(resolve(a.app, a.country), ensure_ascii=False, indent=2));return
    if not 1 <= a.max_pages <= 10 or a.delay < 0.3:p.error('bounds: max-pages 1..10 (feed limit), delay>=0.3s')
    collect(a)


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
