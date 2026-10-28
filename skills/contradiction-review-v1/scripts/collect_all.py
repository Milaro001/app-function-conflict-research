#!/usr/bin/env python3
"""Run every collection source for one App in parallel, then merge the corpus.

One command replaces the step-by-step N3 sequence:
  1. keyword matrix (keywords.py)
  2. in parallel: AppBao + App Store (no login) and each social platform's
     one-session `recent_sample.py collect` (saved login reused, background, muted)
  3. corpus merge (sources.py)
  4. 采集汇总.md / collection-summary.json: counts, time and stop reason per source,
     plus the exact login command for any platform that still needs one

Platforms run as separate processes with separate browser profiles, so one blocked
platform never delays or stops the others. Nothing here logs in or opens a window.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / 'scripts'
SOCIAL = ('xhs', 'wb', 'bili', 'zhihu', 'douyin')
NAMES = {'appbao': '应用宝', 'appstore': 'App Store', 'xhs': '小红书', 'wb': '微博', 'bili': 'B站', 'zhihu': '知乎', 'douyin': '抖音'}


def cfg():
    return json.loads((SKILL / 'runtime.json').read_text(encoding='utf-8'))


def last_json(text):
    """Scripts print a final JSON object; take the last parseable one."""
    for start in [i for i, ch in enumerate(text) if ch == '{'][::-1]:
        try:return json.loads(text[start:text.rindex('}') + 1])
        except ValueError:continue
    return None


def launch(name, cmd, logs):
    log = (logs / f'{name}.log').open('w', encoding='utf-8')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    return dict(name=name, cmd=cmd, log=log, path=logs / f'{name}.log', started=time.monotonic(),
                proc=subprocess.Popen([str(c) for c in cmd], stdout=log, stderr=subprocess.STDOUT, env=env, cwd=str(SKILL)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--app', required=True)
    p.add_argument('--feature', action='append', default=[], help='decision object / feature word, repeatable (improves search and post selection)')
    p.add_argument('--competitor', action='append', default=[])
    p.add_argument('--platforms', nargs='*', default=['appbao', 'appstore', 'xhs', 'wb', 'bili', 'zhihu'],
                   choices=['appbao', 'appstore', *SOCIAL])
    p.add_argument('--since', help='ISO date; default 12 months before now')
    p.add_argument('--posts', type=int, default=30, help='posts per social platform (auto-selected, newest first)')
    p.add_argument('--per-post', type=int, default=80, help='comment+reply cap per post')
    p.add_argument('--reply-min', type=int, default=2, help='page reply threads only when they declare at least N replies')
    p.add_argument('--keywords', type=int, default=8, help='search phrases per platform (4..12)')
    p.add_argument('--pages', type=int, default=2, help='search pages per phrase')
    a = p.parse_args()
    started = time.monotonic();c = cfg()
    py = Path(c['python'])
    if not py.is_file():
        print(json.dumps({'error': 'environment_not_ready', 'fix': 'python scripts/setup.py'}, ensure_ascii=False));return 1
    since = a.since or (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()
    out = Path(c['output']);stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    logs = out / 'collect-all' / stamp;logs.mkdir(parents=True, exist_ok=True)
    plan = logs / 'keywords.json'
    kw = [py, SCRIPTS / 'keywords.py', '--app', a.app, '--per-platform', str(a.keywords), '--output', plan]
    for f in a.feature:kw += ['--feature', f]
    for comp in a.competitor:kw += ['--competitor', comp]
    subprocess.run([str(x) for x in kw], capture_output=True, text=True, encoding='utf-8', check=True)

    skipped = {}
    jobs = []
    if 'appbao' in a.platforms:
        jobs.append(launch('appbao', [py, SCRIPTS / 'appbao.py', 'collect', '--app', a.app, '--since', since], logs))
    if 'appstore' in a.platforms:
        jobs.append(launch('appstore', [py, SCRIPTS / 'appstore.py', 'collect', '--app', a.app], logs))
    for platform in [x for x in a.platforms if x in SOCIAL]:
        if platform == 'douyin':
            skipped[platform] = 'douyin uses the page-action pilot path: scripts/collect.py pilot --platform douyin';continue
        if platform == 'zhihu' and not (c.get('node') or __import__('shutil').which('node')):
            skipped[platform] = 'Node.js missing (Zhihu signing); install it and rerun scripts/setup.py';continue
        jobs.append(launch(platform, [py, SCRIPTS / 'recent_sample.py', 'collect', '--platform', platform, '--app', a.app,
            '--keyword-plan', plan, '--pages', str(a.pages), '--auto-select', str(a.posts), '--since', since, '--comments',
            '--main-pages', '4', '--reply-pages', '2', '--reply-min', str(a.reply_min),
            '--per-post-records', str(a.per_post), '--max-records', '3000'], logs))
    print(json.dumps({'event': 'started', 'sources': [j['name'] for j in jobs], 'skipped': skipped, 'logs': str(logs)}, ensure_ascii=False), flush=True)

    results = {}
    while any(j['proc'].poll() is None for j in jobs):
        time.sleep(2)
        for j in jobs:
            if j['proc'].poll() is not None and j['name'] not in results:
                j['log'].close()
                text = j['path'].read_text(encoding='utf-8', errors='replace')
                results[j['name']] = dict(seconds=round(time.monotonic() - j['started']), exit=j['proc'].returncode, result=last_json(text))
                print(json.dumps({'event': 'finished', 'source': j['name'], 'seconds': results[j['name']]['seconds']}, ensure_ascii=False), flush=True)
    for j in jobs:
        if j['name'] not in results:
            j['log'].close();text = j['path'].read_text(encoding='utf-8', errors='replace')
            results[j['name']] = dict(seconds=round(time.monotonic() - j['started']), exit=j['proc'].returncode, result=last_json(text))

    merge = subprocess.run([str(py), str(SCRIPTS / 'sources.py'), '--app', a.app], capture_output=True, text=True, encoding='utf-8',
                           env=dict(os.environ, PYTHONUTF8='1'))
    corpus = last_json(merge.stdout) or {}
    rows = [];needs_login = []
    for name, r in results.items():
        data = r['result'] or {}
        status = data.get('status') or ('collected' if r['exit'] == 0 and data else 'failed')
        count = data.get('comments') or data.get('records') or (data.get('counts') or {}).get('unique_comment_ids')
        posts = (data.get('counts') or {}).get('posts')
        if status in ('needs_interactive_login', 'unauthenticated', 'needs_user_auth', 'auth_state_unconfirmed', 'unknown_response',
                      'verification_required', 'needs_interactive_verification'):
            needs_login.append(name)
        rows.append(dict(source=name, status=status, posts=posts, comments=count, seconds=r['seconds'], log=str(logs / f'{name}.log')))
    summary = dict(app=a.app, since=since, started_at=stamp, total_seconds=round(time.monotonic() - started), sources=rows,
                   skipped=skipped, needs_login=needs_login,
                   login_commands={n: f'{py} {SCRIPTS / "collect.py"} auth --platform {n} --interactive --wait 900' for n in needs_login},
                   corpus=corpus, keywords=str(plan))
    (logs / 'collection-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [f'# {a.app} 采集汇总', '', f'时间窗：{since} 至今　总用时：{summary["total_seconds"]} 秒（各来源并行）', '',
             '| 来源 | 状态 | 帖子 | 评论/评价 | 用时(秒) |', '|---|---|---:|---:|---:|']
    for r in rows:lines.append(f"| {NAMES.get(r['source'], r['source'])} | {r['status']} | {r['posts'] or ''} | {r['comments'] or 0} | {r['seconds']} |")
    for n, why in skipped.items():lines.append(f'| {NAMES.get(n, n)} | 跳过 |  |  |  |')
    lines += ['', f"合并后语料：{corpus.get('records', 0)} 条记录，可用评论正文 {corpus.get('usable_comment_bodies', 0)} 条，尚未语义筛选。"]
    if needs_login:
        lines += ['', '## 需要用户操作的平台（登录或验证码）', '',
                  '请让用户在方便时运行下列命令，在弹出的专用静音窗口完成登录或滑块验证，之后可后台复用；不要自动重试，以免限制加重：', '']
        lines += [f'- {NAMES.get(n, n)}：`{cmd}`' for n, cmd in summary['login_commands'].items()]
    if skipped:lines += ['', '## 跳过原因', ''] + [f'- {NAMES.get(n, n)}：{why}' for n, why in skipped.items()]
    (logs / '采集汇总.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(dict(summary=str(logs / '采集汇总.md'), total_seconds=summary['total_seconds'],
        sources={r['source']: [r['status'], r['comments']] for r in rows}, needs_login=needs_login,
        corpus_usable_comments=corpus.get('usable_comment_bodies')), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, 'reconfigure'):_s.reconfigure(errors='backslashreplace')
    sys.exit(main())
