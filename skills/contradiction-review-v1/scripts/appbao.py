#!/usr/bin/env python3
"""Collect public Tencent AppBao (应用宝) reviews for one Android App listing.

Uses the same public JSON endpoint the sj.qq.com review tab calls; no login,
cookies or browser. Output is the folder format sources.py imports (comments.json
+ validation.json). Reviews belong to the Android listing; the author's device
and version are still not verified by the source.
"""
import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API = 'https://yybadaccess.3g.qq.com/v2/dc_pcyyb_official'
SORTS = {'time': 'commentListByTime', 'hot': 'commentListByHot'}
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'


def now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, data=None, timeout=25):
    headers = {'User-Agent': UA, 'Referer': 'https://sj.qq.com/', 'Origin': 'https://sj.qq.com'}
    if data is not None:
        data = json.dumps(data).encode();headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def resolve(app):
    """Candidate listings from the public search page: [{appid, pkgname, appname}]."""
    page = fetch('https://sj.qq.com/search?q=' + urllib.parse.quote(app))
    found = {}
    for m in re.finditer(r'appid=(\d+)&amp;pkgname=([\w.]+)&amp;appname=([^&"]+)', page):
        appid, pkg, name = m.group(1), m.group(2), urllib.parse.unquote(html.unescape(m.group(3)))
        found.setdefault(pkg, dict(appid=appid, pkgname=pkg, appname=name))
    return list(found.values())


def choose(app, candidates):
    exact = [c for c in candidates if c['appname'] == app]
    if len(exact) == 1:return exact[0]
    if not exact and len(candidates) == 1:return candidates[0]
    raise SystemExit(json.dumps({'error': 'ambiguous_or_missing_listing', 'app': app,
        'candidates': candidates[:10], 'hint': 'pass --pkg and --appid explicitly'}, ensure_ascii=False))


def page(pkg, appid, start, sort, guid, size=10):
    req = {'AppID': str(appid), 'TagType': '0', 'SortType': SORTS[sort], 'PhoneGUID': guid, 'UserID': '',
           'StartPage': start, 'PageSize': size, 'BeginTime': 0, 'EndTime': 0, 'Version': 1}
    body = {'head': {'cmd': 'dc_pcyyb_official', 'authInfo': {'businessId': 'AuthName'},
                     'deviceInfo': {'platformType': 1, 'platform': 4}, 'userInfo': {'guid': guid},
                     'expSceneIds': '', 'hostAppInfo': {'scene': 'review'}},
            'body': {'bid': 'yybhome', 'offset': 0, 'size': size, 'preview': False,
                     'listS': {'region': {'repStr': ['CN']}, 'pkgname': {'repStr': [pkg]}, 'req_json': {'repStr': [json.dumps(req)]}},
                     'layout': 'YYB_HOME_GAME_REVIEW_COMMENT_LIST', 'listI': {}}}
    data = json.loads(fetch(API, body))
    if data.get('ret') != 0:raise RuntimeError('platform_response_error')
    components = (data.get('data') or {}).get('components') or []
    return [x for c in components for x in ((c.get('data') or {}).get('itemData') or []) if x.get('comment')]


def row(app, listing, item, sort, start):
    c = item['comment']
    created = c.get('createTime')
    return dict(app_name=app, listing_name=listing['appname'], app_id=listing['pkgname'], appbao_appid=listing['appid'],
        review_id=str(c['commentID']), body=c.get('content') or '',
        date=datetime.fromtimestamp(int(created), timezone.utc).isoformat() if created else None,
        rating=(c.get('mulDimensionScore') or {}).get('total'), version=None,
        reply_count_declared=c.get('replyNum') if c.get('replyNum') != '' else None,
        praise=c.get('praiseNum') or 0, retrieved_at=now(), sort=sort, page=start,
        source_url='https://sj.qq.com/appdetail/' + listing['pkgname'] + '/review',
        # Nicknames are masked by the source; keep only a one-way grouping hash.
        author_hash=hashlib.sha256(('appbao:' + str((item.get('user') or {}).get('nickName'))).encode()).hexdigest()[:16])


def collect(args):
    listing = dict(appid=args.appid, pkgname=args.pkg, appname=args.app) if args.pkg and args.appid else choose(args.app, resolve(args.app))
    since = datetime.fromisoformat(args.since.replace('Z', '+00:00')) if args.since else None
    if since and since.tzinfo is None:since = since.replace(tzinfo=timezone.utc)
    guid = str(uuid.uuid4());rows = {};pages = [];errors = []
    plan = [('time', args.max_pages)] + ([('hot', args.hot_pages)] if args.hot_pages else [])
    for sort, limit in plan:
        stop = 'page_limit_reached';empty = 0
        for start in range(1, limit + 1):
            time.sleep(args.delay)
            try:items = page(listing['pkgname'], listing['appid'], start, sort, guid)
            except Exception as exc:
                errors.append(dict(sort=sort, page=start, reason=type(exc).__name__));stop = 'request_failed';break
            fresh = 0;dates = []
            for item in items:
                r = row(args.app, listing, item, sort, start)
                if r['date']:dates.append(r['date'])
                if r['review_id'] not in rows:rows[r['review_id']] = r;fresh += 1
            oldest = min(dates) if dates else None
            pages.append(dict(sort=sort, page=start, returned=len(items), new=fresh, oldest=oldest))
            if not items:
                empty += 1
                if empty >= 2:stop = 'source_end_confirmed';break
                continue
            empty = 0
            if sort == 'time' and since and oldest and datetime.fromisoformat(oldest) < since:stop = 'reached_since_date';break
            if not fresh:stop = 'no_new_ids_unconfirmed';break
            if len(rows) >= args.max_records:stop = 'record_limit_reached';break
        pages.append(dict(sort=sort, stop_reason=stop))
    out = Path(args.output) if args.output else Path(json.loads((Path(__file__).resolve().parents[1] / 'runtime.json').read_text(encoding='utf-8'))['output']) / 'appbao' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + listing['pkgname'])
    out.mkdir(parents=True, exist_ok=True)
    comments = sorted(rows.values(), key=lambda r: r['date'] or '', reverse=True)
    (out / 'comments.json').write_text(json.dumps(comments, ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    stops = {p['sort']: p['stop_reason'] for p in pages if 'stop_reason' in p}
    validation = dict(app=args.app, listing=listing, completed_at=now(), since=args.since, comments=len(comments),
        pagination=f"{sum(1 for p in pages if 'page' in p)} page responses; stops={stops}", stop_reasons=stops,
        pages=pages, errors=errors, client_basis='android_store_listing; author device/version not stated by source',
        replies='reply bodies not collected; reply_count_declared kept')
    (out / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    latest = out.parent / ('latest-' + hashlib.sha256(args.app.encode()).hexdigest()[:12] + '.json')
    # Only default-location runs become the App's latest pointer; explicit --output stays standalone.
    if not args.output:latest.write_text(json.dumps(dict(app=args.app, path=str(out), completed_at=validation['completed_at']), ensure_ascii=False) + '\n',encoding='utf-8')
    print(json.dumps(dict(output=str(out), listing=listing, comments=len(comments), stop_reasons=stops, errors=len(errors),
        newest=comments[0]['date'] if comments else None, oldest=comments[-1]['date'] if comments else None), ensure_ascii=False, indent=2))


def latest_dir(output_root, app):
    """Folder of the most recent collect for this App, or None (used by sources.py)."""
    f = Path(output_root) / 'appbao' / ('latest-' + hashlib.sha256(app.encode()).hexdigest()[:12] + '.json')
    if not f.exists():return None
    path = Path(json.loads(f.read_text(encoding='utf-8'))['path'])
    return path if (path / 'comments.json').exists() else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    r = sub.add_parser('resolve');r.add_argument('--app', required=True)
    c = sub.add_parser('collect');c.add_argument('--app', required=True)
    c.add_argument('--pkg');c.add_argument('--appid')
    c.add_argument('--since', help='stop the newest-first pass once reviews are older than this ISO date')
    c.add_argument('--max-pages', type=int, default=120, help='newest-first pages of 10 reviews')
    c.add_argument('--hot-pages', type=int, default=5, help='additional most-helpful pages (older high-signal reviews)')
    c.add_argument('--max-records', type=int, default=3000)
    c.add_argument('--delay', type=float, default=1.0)
    c.add_argument('--output')
    a = p.parse_args()
    if a.command == 'resolve':
        print(json.dumps(resolve(a.app), ensure_ascii=False, indent=2));return
    if not 1 <= a.max_pages <= 400 or not 0 <= a.hot_pages <= 30 or a.delay < 0.5 or not 1 <= a.max_records <= 5000:
        p.error('bounds: max-pages 1..400, hot-pages 0..30, delay>=0.5s, max-records 1..5000')
    if bool(a.pkg) != bool(a.appid):p.error('--pkg and --appid go together')
    collect(a)


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    sys.exit(main())
