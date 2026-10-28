#!/usr/bin/env python3
"""One-step environment setup for this skill on Windows, macOS and Linux.

Run with any Python 3.8+ (standard library only):  python scripts/setup.py
It is safe to run again; finished steps are reused. It never logs in, never collects,
and never changes the system Python, the user's daily browser or global settings.

Steps
  1. Python 3.11+  - reuse one on this computer, else download a private 3.12 with uv
  2. .venv         - private environment inside the skill folder
  3. Dependencies  - core set (requirements-core.txt); --full adds the whole upstream stack
  4. Browser       - reuse Edge/Chrome, else download Playwright Chromium
  5. Node.js       - needed only for Zhihu request signing; reported if missing
  6. runtime.json  - local paths via configure_runtime.py, then a doctor check
  7. Report        - .setup/setup-report.json and .setup/安装报告.md; .setup/ready.json when usable

Mainland China networks: --mirror china uses Tsinghua PyPI and npmmirror for Python and
Chromium downloads. Without the flag a failed download is retried once with that mirror.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SETUP = SKILL / '.setup'
WINDOWS = os.name == 'nt'
MIRRORS = {
    'pypi': 'https://pypi.tuna.tsinghua.edu.cn/simple',
    'python': 'https://registry.npmmirror.com/-/binary/python-build-standalone',
    'playwright': 'https://registry.npmmirror.com/-/binary/playwright',
}

steps = []


def now():
    return datetime.now(timezone.utc).isoformat()


def log(step, status, detail='', fix=None):
    steps.append(dict(step=step, status=status, detail=detail, fix=fix))
    mark = {'ok': 'OK ', 'skip': '-- ', 'warn': '!! ', 'fail': 'XX '}[status]
    text = f'[{mark}] {step}: {detail}' + (f'\n       -> {fix}' if fix else '')
    try:print(text, flush=True)
    except UnicodeEncodeError:print(text.encode('ascii', 'backslashreplace').decode(), flush=True)


def run(cmd, env=None, timeout=1800):
    """Run a command; children use UTF-8 so Chinese paths and output survive GBK consoles."""
    full = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', **(env or {}))
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding='utf-8', errors='replace',
                           env=full, timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f'{type(exc).__name__}: {exc}'


def version_of(python):
    code, out = run([python, '-c', 'import sys;print("%d.%d"%sys.version_info[:2])'], timeout=60)
    if code:return None
    try:return tuple(int(x) for x in out.strip().splitlines()[-1].split('.'))
    except ValueError:return None


def venv_python(root):
    return root / ('Scripts/python.exe' if WINDOWS else 'bin/python')


def find_uv():
    for c in [shutil.which('uv'), SETUP / 'bin' / ('uv.exe' if WINDOWS else 'uv'),
              Path.home() / '.local/bin' / ('uv.exe' if WINDOWS else 'uv'), Path.home() / '.cargo/bin' / ('uv.exe' if WINDOWS else 'uv')]:
        if c and Path(c).is_file():return Path(c)
    return None


UV_INDEXES = ('https://pypi.org/simple/uv/', 'https://pypi.tuna.tsinghua.edu.cn/simple/uv/', 'https://mirrors.aliyun.com/pypi/simple/uv/')


def uv_wheel_tags():
    machine = platform.machine().lower()
    arm = machine in ('arm64', 'aarch64')
    if WINDOWS:return ['win_arm64'] if arm else ['win_amd64']
    if sys.platform == 'darwin':return ['macosx_11_0_arm64'] if arm else ['macosx_10_12_x86_64']
    return ['manylinux_2_17_aarch64', 'manylinux2014_aarch64'] if arm else ['manylinux_2_17_x86_64', 'manylinux2014_x86_64']


def install_uv(mirror='default'):
    """Fetch uv from a PyPI wheel (the wheel carries the uv binary).

    PyPI mirrors are reachable on networks where GitHub release downloads stall, and this
    avoids running a downloaded shell/PowerShell script. Every read has a timeout and the
    wheel is checked against the index's sha256 before use.
    """
    import re, io, urllib.parse, urllib.request, zipfile
    target = SETUP / 'bin';target.mkdir(parents=True, exist_ok=True)
    indexes = UV_INDEXES[1:] + UV_INDEXES[:1] if mirror == 'china' else UV_INDEXES
    tags = uv_wheel_tags();exe = 'uv.exe' if WINDOWS else 'uv'
    for index in indexes:
        try:
            page = urllib.request.urlopen(urllib.request.Request(index, headers={'User-Agent': 'setup.py'}), timeout=20).read().decode('utf-8', 'replace')
            links = []
            for href in re.findall(r'href="([^"]+)"', page):
                name = urllib.parse.unquote(href.split('#')[0].rsplit('/', 1)[-1])
                m = re.match(r'uv-(\d+)\.(\d+)\.(\d+)-py3-none-(.+)\.whl$', name)
                if m and any(t in m.group(4) for t in tags):links.append((tuple(int(x) for x in m.group(1, 2, 3)), href))
            if not links:continue
            version, href = max(links)
            url = urllib.parse.urljoin(index, href.split('#')[0])
            digest = (re.search(r'sha256=([0-9a-f]{64})', href) or [None, None])[1]
            data = io.BytesIO()
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'setup.py'}), timeout=30) as r:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:break
                    data.write(chunk)
            raw = data.getvalue()
            if digest and hashlib.sha256(raw).hexdigest() != digest:continue
            with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
                member = next(n for n in wheel.namelist() if n.endswith('/scripts/' + exe))
                (target / exe).write_bytes(wheel.read(member))
            if not WINDOWS:os.chmod(target / exe, 0o755)
            code, _ = run([target / exe, '--version'], timeout=60)
            if code == 0:return target / exe
        except Exception:
            continue
    return None


def candidate_pythons():
    seen = []
    def add(p):
        if p and Path(p).is_file() and str(p) not in seen:seen.append(str(p))
    add(sys.executable)
    for name in ('python3.13', 'python3.12', 'python3.11', 'python3', 'python'):add(shutil.which(name))
    if WINDOWS and shutil.which('py'):
        for v in ('3.13', '3.12', '3.11'):
            code, out = run(['py', f'-{v}', '-c', 'import sys;print(sys.executable)'], timeout=60)
            if code == 0:add(out.strip().splitlines()[-1])
        local = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Python'
        for d in sorted(local.glob('Python31[1-9]*'), reverse=True) if local.exists() else []:add(d / 'python.exe')
    return seen


def step_python(args):
    if args.python:
        v = version_of(args.python)
        if v and v >= (3, 11):log('Python', 'ok', f'{args.python} ({v[0]}.{v[1]}, given)');return Path(args.python)
        log('Python', 'fail', f'{args.python} is not Python 3.11+', 'omit --python to let setup find or download one');return None
    for c in candidate_pythons():
        # Windows Store "python" stubs fail this probe and are skipped.
        v = version_of(c)
        if v and v >= (3, 11):log('Python', 'ok', f'{c} ({v[0]}.{v[1]})');return Path(c)
    uv = find_uv() or install_uv(args.mirror)
    if not uv:
        log('Python', 'fail', 'no Python 3.11+ found and uv could not be downloaded',
            'install Python 3.12 from https://www.python.org/downloads/ (Windows: tick "Add python.exe to PATH"), then rerun');return None
    for attempt, env in enumerate(({}, {'UV_PYTHON_INSTALL_MIRROR': MIRRORS['python']})):
        if args.mirror == 'china' and attempt == 0:continue
        # The default source is GitHub; cap it so a stalled download falls back to the mirror.
        code, out = run([uv, 'python', 'install', '3.12'], env=dict(env, UV_HTTP_TIMEOUT='60'), timeout=240 if attempt == 0 else 1200)
        if code == 0:
            code, out = run([uv, 'python', 'find', '3.12'], timeout=60)
            if code == 0:
                path = Path(out.strip().splitlines()[-1])
                log('Python', 'ok', f'downloaded private Python 3.12 via uv: {path}');return path
    log('Python', 'fail', 'uv could not download Python 3.12', 'check the network or install Python 3.12 manually, then rerun')
    return None


def step_venv(python):
    root = SKILL / '.venv';vp = venv_python(root)
    if vp.is_file() and (version_of(vp) or (0,)) >= (3, 11):
        log('Virtual environment', 'skip', f'reusing {root}');return vp
    if root.exists():shutil.rmtree(root, ignore_errors=True)
    uv = find_uv()
    code, out = run([uv, 'venv', '--python', python, root] if uv else [python, '-m', 'venv', root], timeout=600)
    if code or not vp.is_file():
        log('Virtual environment', 'fail', out.strip()[-400:], 'on Debian/Ubuntu install python3-venv, then rerun');return None
    log('Virtual environment', 'ok', str(root));return vp


def requirements_hash(files):
    return hashlib.sha256(b''.join(f.read_bytes() for f in files)).hexdigest()[:16]


def step_packages(vp, args):
    files = [SKILL / 'requirements-core.txt'] + ([SKILL / 'requirements-lock.txt'] if args.full else [])
    stamp = SETUP / 'packages.json';digest = requirements_hash(files) + str(vp)
    if stamp.exists() and json.loads(stamp.read_text(encoding='utf-8')).get('digest') == digest:
        code, _ = run([vp, '-c', 'import playwright,httpx,pydantic,xhshow,execjs,PIL,humps,parsel'], timeout=120)
        if code == 0:log('Dependencies', 'skip', 'already installed');return True
    uv = find_uv();reqs = []
    for f in files:reqs += ['-r', f]
    attempts = [None, MIRRORS['pypi']] if args.mirror != 'china' else [MIRRORS['pypi']]
    out = ''
    for index in attempts:
        extra = ['--index-url', index] if index else []
        cmd = [uv, 'pip', 'install', '--python', vp, *reqs, *extra] if uv else [vp, '-m', 'pip', 'install', '--disable-pip-version-check', *reqs, *extra]
        code, out = run(cmd, env={'UV_HTTP_TIMEOUT': '60'}, timeout=900 if index is None else 2400)
        if code == 0:
            SETUP.mkdir(exist_ok=True);stamp.write_text(json.dumps(dict(digest=digest, at=now(), index=index or 'default')), encoding='utf-8')
            log('Dependencies', 'ok', ('full upstream stack' if args.full else 'core set') + (f' via {index}' if index else ''));return True
    log('Dependencies', 'fail', out.strip()[-600:], 'rerun with --mirror china, or check proxy settings');return False


def find_browser(vp):
    code, out = run([vp, '-c', 'import sys;sys.path.insert(0,r"%s");import configure_runtime as c;b=c.detect_browser();print(b or "")' % (SKILL / 'scripts')], timeout=120)
    path = out.strip().splitlines()[-1] if code == 0 and out.strip() else ''
    return Path(path) if path and Path(path).is_file() else None


def step_browser(vp, args):
    if args.browser:
        b = Path(args.browser)
        if b.is_file():log('Browser', 'ok', f'{b} (given)');return b
        log('Browser', 'fail', f'{b} does not exist');return None
    b = find_browser(vp)
    if b:log('Browser', 'ok', str(b));return b
    for attempt, env in enumerate(({}, {'PLAYWRIGHT_DOWNLOAD_HOST': MIRRORS['playwright']})):
        if args.mirror == 'china' and attempt == 0:continue
        code, out = run([vp, '-m', 'playwright', 'install', 'chromium'], env=env, timeout=420 if attempt == 0 else 1800)
        if code == 0:
            b = find_browser(vp)
            if b:log('Browser', 'ok', f'downloaded Playwright Chromium: {b}');return b
    log('Browser', 'warn', 'no Edge/Chrome and Chromium download failed',
        'install Microsoft Edge or Google Chrome, then rerun; reports still work without a browser')
    return None


def find_node():
    for c in [shutil.which('node'), *( [Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'nodejs/node.exe',
              Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/nodejs/node.exe'] if WINDOWS else
              [Path('/opt/homebrew/bin/node'), Path('/usr/local/bin/node'), Path.home() / '.local/bin/node'])]:
        if c and Path(c).is_file():return Path(c)
    return None


def step_node(args):
    node = find_node()
    if not node and args.install_node:
        cmd = (['winget', 'install', '-e', '--id', 'OpenJS.NodeJS.LTS', '--accept-package-agreements', '--accept-source-agreements']
               if WINDOWS and shutil.which('winget') else ['brew', 'install', 'node'] if shutil.which('brew') else None)
        if cmd:run(cmd, timeout=1800);node = find_node()
    if node:
        code, out = run([node, '--version'], timeout=60)
        log('Node.js', 'ok', f'{node} {out.strip()}');return node
    fix = ('winget install -e --id OpenJS.NodeJS.LTS  (or download from https://nodejs.org)' if WINDOWS
           else 'brew install node  (or download from https://nodejs.org)')
    log('Node.js', 'warn', 'not found; only Zhihu collection needs it', fix + ', then rerun setup')
    return None


def step_configure(vp, browser, node, args):
    current = json.loads((SKILL / 'runtime.json').read_text(encoding='utf-8'))
    workspace = Path(args.workspace).expanduser() if args.workspace else (
        Path(current['workspace']) if current.get('workspace') not in (None, '', '.') and Path(current['workspace']).is_absolute()
        else Path.home() / 'app-research-workspace-v1.0')
    workspace.mkdir(parents=True, exist_ok=True)
    cmd = [vp, SKILL / 'scripts/configure_runtime.py', '--workspace', workspace, '--python', vp]
    if browser:cmd += ['--browser', browser]
    code, out = run(cmd, timeout=300)
    if code:log('Runtime paths', 'fail', out.strip()[-400:]);return None
    cfg = json.loads((SKILL / 'runtime.json').read_text(encoding='utf-8'))
    cfg['node'] = str(node) if node else None
    (SKILL / 'runtime.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    log('Runtime paths', 'ok', f'workspace {workspace}');return cfg


def step_doctor(vp):
    code, out = run([vp, SKILL / 'scripts/collect.py', 'doctor'], timeout=300)
    try:doctor = json.loads(out[out.index('{'):out.rindex('}') + 1])
    except ValueError:
        log('Doctor', 'fail', out.strip()[-400:]);return None
    missing = [k for k, v in doctor.get('packages', {}).items() if not v]
    if missing:log('Doctor', 'fail', 'missing packages: ' + ', '.join(missing), 'rerun setup')
    else:log('Doctor', 'ok', 'collector imports and paths check out')
    return doctor


def write_report(state):
    SETUP.mkdir(exist_ok=True)
    report = dict(checked_at=now(), host=dict(system=platform.system(), release=platform.release(), machine=platform.machine()),
        skill=str(SKILL), **state, steps=steps)
    (SETUP / 'setup-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    names = {'ok': '已就绪', 'skip': '已就绪（复用）', 'warn': '需注意', 'fail': '失败'}
    lines = ['# 安装报告', '', f"检查时间：{report['checked_at']}　系统：{report['host']['system']} {report['host']['release']}", '',
             '| 步骤 | 结果 | 说明 | 怎么补 |', '|---|---|---|---|']
    for s in steps:
        lines.append(f"| {s['step']} | {names[s['status']]} | {(s['detail'] or '').replace('|', '/')[:160]} | {(s['fix'] or '').replace('|', '/')} |")
    cap = state['capabilities']
    lines += ['', '## 现在能做什么', '',
              f"- 生成与预览报告网页：{'可以' if cap['reports'] else '不可以'}",
              f"- 免登录采集（应用宝、App Store、公开网页导入）：{'可以' if cap['store_collection'] else '不可以'}",
              f"- 社媒采集（小红书、微博、B站、抖音，需本人登录一次）：{'可以' if cap['social_collection'] else '不可以'}",
              f"- 知乎采集（另需Node.js）：{'可以' if cap['zhihu'] else '不可以'}", '',
              '能力可用只表示环境就绪；各平台登录与采集仍需实际运行后才算验证。']
    (SETUP / '安装报告.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def check_ready():
    """Fast offline check used by Agents before collection: is the last setup still valid?"""
    f = SETUP / 'ready.json'
    if not f.exists():return dict(ready=False, reason='setup_not_run')
    data = json.loads(f.read_text(encoding='utf-8'))
    vp = Path(data.get('python', ''))
    if not vp.is_file():return dict(ready=False, reason='python_missing')
    if data.get('requirements') != requirements_hash([SKILL / 'requirements-core.txt']):return dict(ready=False, reason='requirements_changed')
    if data.get('browser') and not Path(data['browser']).is_file():return dict(ready=False, reason='browser_missing')
    return dict(ready=True, **data)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--workspace', help='research folder for runtime data and outputs (default: ~/app-research-workspace-v1.0)')
    p.add_argument('--python', help='use this Python 3.11+ instead of searching')
    p.add_argument('--browser', help='use this Chrome/Edge/Chromium executable')
    p.add_argument('--full', action='store_true', help='also install the full upstream MediaCrawler requirements (large)')
    p.add_argument('--mirror', choices=['default', 'china'], default='default')
    p.add_argument('--install-node', action='store_true', help='install Node.js LTS with winget (Windows) or brew (macOS) if missing')
    p.add_argument('--check', action='store_true', help='only report whether a previous setup is still valid (offline, instant)')
    a = p.parse_args()
    if a.check:
        print(json.dumps(check_ready(), ensure_ascii=False, indent=2));return 0
    started = time.monotonic()
    py = step_python(a)
    vp = step_venv(py) if py else None
    packages = step_packages(vp, a) if vp else False
    browser = step_browser(vp, a) if packages else None
    node = step_node(a)
    cfg = step_configure(vp, browser, node, a) if packages else None
    doctor = step_doctor(vp) if cfg else None
    doctor_ok = bool(doctor) and all(doctor.get('packages', {}).values())
    caps = dict(reports=bool(py), store_collection=bool(packages and doctor_ok), social_collection=bool(doctor_ok and browser),
                zhihu=bool(doctor_ok and browser and node))
    state = dict(seconds=round(time.monotonic() - started), python=str(vp) if vp else None, browser=str(browser) if browser else None,
                 node=str(node) if node else None, workspace=cfg.get('workspace') if cfg else None, capabilities=caps)
    write_report(state)
    if caps['store_collection']:
        (SETUP / 'ready.json').write_text(json.dumps(dict(state, requirements=requirements_hash([SKILL / 'requirements-core.txt']),
            at=now()), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    elif (SETUP / 'ready.json').exists():(SETUP / 'ready.json').unlink()
    print(json.dumps(dict(summary='ready' if caps['social_collection'] else 'partial' if caps['reports'] else 'failed',
        capabilities=caps, report=str(SETUP / '安装报告.md'), seconds=state['seconds']), ensure_ascii=False, indent=2))
    return 0 if caps['social_collection'] else 2 if caps['reports'] else 1


if __name__ == '__main__':
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, 'reconfigure'):_s.reconfigure(errors='backslashreplace')
    sys.exit(main())
