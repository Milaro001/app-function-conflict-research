#!/usr/bin/env python3
"""Bounded MediaCrawler adapter with persistent sessions and an evidence ledger.

The platform clients come from the pinned upstream project. Browser sessions,
bounded page traversal and the audit ledger are this project's adapter layer.
No cookies, raw authentication responses or request headers are logged/exported.
"""
import argparse
import asyncio
import hashlib
import hmac
import html
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
CFG = json.loads((SKILL / 'runtime.json').read_text(encoding='utf-8'))
RUNTIME = Path(CFG['runtime'])
# setup.py records Node.js (Zhihu signing); it is often installed but not on PATH on Windows.
if CFG.get('node') and Path(CFG['node']).is_file() and str(Path(CFG['node']).parent) not in os.environ.get('PATH',''):
    os.environ['PATH']=str(Path(CFG['node']).parent)+os.pathsep+os.environ.get('PATH','')
OUTPUT = Path(CFG['output'])


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2),encoding='utf-8')
    temp.replace(path)


def safe_error(exc):
    # Upstream retry wrappers hide the real cause; classify the last attempt instead.
    inner = getattr(getattr(exc, 'last_attempt', None), 'exception', lambda: None)()
    if inner is not None and inner is not exc:return safe_error(inner)
    # Exception bodies in upstream sometimes include server response content.
    if isinstance(exc, CollectionStop):
        return str(exc)
    text = str(exc).lower()
    if any(x in text for x in ('captcha', 'verifytype', '验证')):
        return 'verification_required'
    if any(x in text for x in ('403', '401', '412', '429', 'blocked', 'security restriction', '访问频繁')):
        return 'access_denied'
    if any(x in text for x in ('not login', '未登录', '账号未登录', '-101')):
        return 'needs_user_auth'
    if any(x in type(exc).__name__.lower() for x in ('timeout', 'connect', 'network', 'ssl')):
        return 'network_error'
    return 'request_failed'


def identifier(value):
    return str(value) if value not in (None, '', 0, '0') else None


def timestamp(value):
    try:
        value = float(value)
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, AttributeError):
            return None


def plain_html(value):
    value = re.sub(r'<br\s*/?>', '\n', value or '', flags=re.I)
    value = re.sub(r'<img\b[^>]*\balt=["\']([^"\']*)["\'][^>]*>', r'\1', value, flags=re.I)
    return html.unescape(re.sub('<[^>]*>', '', value)).strip()


def weibo_cards(cards):
    """The search API can nest actual posts inside card_group containers."""
    result=[]
    for card in cards or []:
        if card.get('mblog'):result.append(card['mblog'])
        result.extend(weibo_cards(card.get('card_group')))
    return result


class Ledger:
    def __init__(self, platform, app, mode, run_id=None, profile_name='default'):
        self.platform, self.app = platform, app
        self.run_id = run_id or (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + platform + '-' + uuid.uuid4().hex[:6])
        self.path = OUTPUT / 'runs' / self.run_id
        self.path.mkdir(parents=True, exist_ok=False)
        RUNTIME.mkdir(parents=True, exist_ok=True)
        os.chmod(RUNTIME, 0o700)
        keyfile = RUNTIME / 'author-hash.key'
        if not keyfile.exists():
            fd = os.open(keyfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(os.urandom(32))
        self.key = keyfile.read_bytes()
        self.db = sqlite3.connect(RUNTIME / 'evidence.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (platform TEXT, kind TEXT, id TEXT, post_id TEXT, payload TEXT, PRIMARY KEY(platform,kind,id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS observations (run_id TEXT, platform TEXT, kind TEXT, id TEXT, PRIMARY KEY(run_id,platform,kind,id))')
        self.seq = 0
        self.manifest = dict(run_id=self.run_id, platform=platform, app=app, mode=mode,
            started_at=now(), status='starting', upstream_revision=CFG['revision'], process_id=os.getpid(),
            adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            auth_checks=[], threads=[], posts=[], errors=[], search_pages=[],
            profile_name=profile_name, browser_profile=str(RUNTIME / 'profiles' / platform / profile_name),
            context_scope='post text, main comments and reply links; images/video not interpreted',
            sampling_purpose='technical pilot, not a representative opinion sample')
        self.flush()

    def flush(self):
        write_json(self.path / 'manifest.json', self.manifest)
        write_json(OUTPUT / ('latest-' + self.platform + '.json'), {'run_id': self.run_id, 'path': str(self.path), 'status': self.manifest['status']})

    def event(self, kind, **data):
        self.seq += 1
        event = dict(seq=self.seq, at=now(), kind=kind, **data)
        with (self.path / 'pages.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
        return event

    def add_post(self, post):
        # A sampled post may already be recorded by the detail pass; keep one entry per ID.
        if not any(x['id']==post['id'] for x in self.manifest['posts']):self.manifest['posts'].append(post)

    def author(self, value):
        return hmac.new(self.key, (self.platform + ':' + str(value)).encode(), hashlib.sha256).hexdigest()[:24] if value else None

    def save(self, record):
        exists = self.db.execute('SELECT 1 FROM records WHERE platform=? AND kind=? AND id=?', (self.platform, record['kind'], record['id'])).fetchone()
        self.db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)',
            (self.platform, record['kind'], record['id'], record['post_id'], json.dumps(record, ensure_ascii=False)))
        self.db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?)',
            (self.run_id, self.platform, record['kind'], record['id']))
        self.db.commit()
        return not bool(exists)

    def export(self):
        rows = self.db.execute('SELECT r.payload FROM records r JOIN observations o ON r.platform=o.platform AND r.kind=o.kind AND r.id=o.id WHERE o.run_id=?', (self.run_id,)).fetchall()
        records = [json.loads(x[0]) for x in rows]
        comments = [x for x in records if x['kind'] == 'comment']
        keys = {x['id'] for x in comments}
        missing_roots = [x['id'] for x in comments if x.get('level') == 2 and x.get('root_id') not in keys]
        missing_targets = [x['id'] for x in comments if x.get('reply_to_id') and x['reply_to_id'] not in keys]
        with (self.path / 'records.jsonl').open('w',encoding='utf-8') as f:
            for item in records:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        counts = dict(records=len(records), posts=sum(x['kind']=='post' for x in records),
            main_comments=sum(x.get('level')==1 for x in comments), replies=sum(x.get('level')==2 for x in comments),
            nonempty_comments=sum(bool(x.get('body','').strip()) for x in comments),
            unique_comment_ids=len(keys), missing_roots=missing_roots, missing_reply_targets=missing_targets)
        self.manifest['counts'] = counts
        self.flush()
        return counts


def normalize_comment(platform, post_id, raw, ledger, root=None):
    if platform == 'bili':
        cid = identifier(raw.get('rpid_str') or raw.get('rpid'))
        native_root = identifier(raw.get('root_str') or raw.get('root'))
        parent = identifier(raw.get('parent_str') or raw.get('parent'))
        body = (raw.get('content') or {}).get('message', '')
        author = (raw.get('member') or {}).get('mid')
        created, declared = raw.get('ctime'), raw.get('rcount')
    elif platform == 'douyin':
        cid = identifier(raw.get('cid'))
        native_root = identifier(raw.get('reply_id'))
        parent = identifier(raw.get('reply_to_reply_id')) or native_root
        body, author = raw.get('text') or '', (raw.get('user') or {}).get('uid')
        created, declared = raw.get('create_time'), raw.get('reply_comment_total')
    elif platform == 'wb':
        cid = identifier(raw.get('idstr') or raw.get('id'))
        native_root = identifier(raw.get('rootid'))
        parent = identifier(raw.get('reply_id'))
        body, author = plain_html(raw.get('text')), (raw.get('user') or {}).get('id')
        created, declared = raw.get('created_at'), raw.get('total_number')
    elif platform == 'zhihu':
        cid = identifier(raw.get('comment_id'))
        native_root = None
        parent = identifier(raw.get('parent_comment_id'))
        body, author = raw.get('content') or '', raw.get('creator_hash')
        created, declared = raw.get('publish_time'), raw.get('sub_comment_count')
    else:
        cid = identifier(raw.get('id'))
        native_root = None
        parent = identifier((raw.get('target_comment') or {}).get('id'))
        body, author = raw.get('content') or '', (raw.get('user_info') or {}).get('user_id')
        created, declared = raw.get('create_time'), raw.get('sub_comment_count')
    if not cid:
        raise ValueError('missing comment id')
    # Weibo can put a top-level comment's own ID in rootid.
    # A container pointing to itself does not turn it into a child reply.
    if native_root==cid:native_root=None
    level = 2 if root or native_root else 1
    root_id = identifier(root) or native_root or cid
    if parent == cid:
        parent = None
    return dict(platform=platform, kind='comment', id=cid, post_id=str(post_id),
        level=level, root_id=root_id, parent_id=parent or (root_id if level==2 else None),
        reply_to_id=parent, parent_relation='explicit' if parent else 'root_container' if level==2 else 'top_level',
        body=body, published_at=timestamp(created), author_hash=ledger.author(author),
        declared_replies=declared, has_media=bool(raw.get('pictures') or (raw.get('content') or {}).get('pictures') if isinstance(raw.get('content'),dict) else raw.get('pictures')),
        source_url={'bili':'https://www.bilibili.com/video/av','wb':'https://m.weibo.cn/detail/','xhs':'https://www.xiaohongshu.com/explore/','douyin':'https://www.douyin.com/video/',
            'zhihu':'https://www.zhihu.com/answer/'}[platform] + str(post_id),
        retrieved_at=now())


def normalize_post(platform, pid, info):
    if platform=='zhihu':
        # A search hit already carries the full answer/article text.
        body=info.get('content_text') or info.get('desc') or ''
        if not body and not info.get('title'):raise ValueError('Zhihu post context missing')
        return dict(platform=platform,kind='post',id=str(pid),post_id=str(pid),title=info.get('title') or body[:100],body=body,
            content_type=info.get('content_type'),published_at=timestamp(info.get('created_time')),
            declared_comments=info.get('comment_count'),source_url=info.get('content_url') or 'https://www.zhihu.com/answer/'+str(pid),
            media_context_status='images_video_not_interpreted',retrieved_at=now())
    if platform=='douyin':
        body=info.get('desc') or ''
        if not body:raise ValueError('Douyin post context missing')
        return dict(platform=platform,kind='post',id=str(pid),post_id=str(pid),title=body[:100],body=body,
            published_at=timestamp(info.get('create_time')),declared_comments=(info.get('statistics') or {}).get('comment_count'),
            source_url='https://www.douyin.com/video/'+str(pid),media_context_status='video_not_interpreted',retrieved_at=now())
    if platform=='bili':
        view=info.get('View') or info
        if not view.get('title'):raise ValueError('Bilibili post context missing title')
        return dict(platform=platform,kind='post',id=str(pid),post_id=str(pid),title=view['title'],
            body=view.get('desc') or '',published_at=timestamp(view.get('pubdate')),
            declared_comments=(view.get('stat') or {}).get('reply'),
            source_url='https://www.bilibili.com/video/'+str(view.get('bvid') or 'av'+str(pid)),
            media_context_status='video_not_interpreted',retrieved_at=now())
    if platform=='wb':
        data=info.get('mblog') or info
        body=plain_html(data.get('text'))
        if not body:raise ValueError('Weibo post text missing')
        return dict(platform=platform,kind='post',id=str(pid),post_id=str(pid),title=body[:100],body=body,
            published_at=timestamp(data.get('created_at')),declared_comments=data.get('comments_count'),
            source_url='https://m.weibo.cn/detail/'+str(pid),
            text_completeness='truncated' if data.get('isLongText') else 'returned_text_unverified',
            media_context_status='images_video_not_interpreted',retrieved_at=now())
    if not info.get('note_id') and not info.get('title') and not info.get('desc'):
        raise ValueError('XHS post context missing')
    return dict(platform=platform,kind='post',id=str(pid),post_id=str(pid),title=info.get('title') or '',
        body=info.get('desc') or '',published_at=timestamp(info.get('time')),
        declared_comments=(info.get('interact_info') or {}).get('comment_count'),
        source_url='https://www.xiaohongshu.com/explore/'+str(pid),
        media_context_status='images_video_not_interpreted' if info.get('image_list') or info.get('video') else 'text_only',retrieved_at=now())


PLATFORM_MIN_DELAY = {'xhs': 3.5, 'douyin': 3.0}


class Collector:
    def __init__(self, args, ledger):
        self.args, self.ledger = args, ledger
        self.platform = args.platform
        self.client = self.context = self.page = None
        self.observed = set()
        # Search on some platforms rate-limits sooner than others; keep a per-platform floor.
        self.floor = max(getattr(args,'delay',1.5), PLATFORM_MIN_DELAY.get(self.platform, 0))
        self.pace = self.floor; self.request_count = 0

    async def call(self, kind, func, **meta):
        # Pace = configured floor plus jitter, widened after slow or failed responses and
        # eased back after a run of fast successes. Never below the configured delay.
        await asyncio.sleep(self.pace + __import__('random').uniform(0, 0.6))
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(func(), timeout=45)
            elapsed = time.monotonic() - started
            self.pace = min(self.pace * 1.5, 12) if elapsed > 8 else max(self.floor, self.pace * 0.9)
            self.request_count += 1
            return result
        except Exception as exc:
            self.pace = min(self.pace * 2, 12)
            reason = safe_error(exc)
            self.ledger.event('request_error', operation=kind, reason=reason, exception=type(exc).__name__, **meta)
            self.ledger.manifest['errors'].append(dict(operation=kind, reason=reason, **meta))
            self.ledger.flush()
            raise CollectionStop(reason) from None

    async def setup_client(self):
        if self.platform=='douyin':return
        from tools import utils
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(self.context, urls=[self.home])
        headers={'User-Agent': await self.page.evaluate('navigator.userAgent'), 'Cookie':cookie_str,
            'Referer':self.home+'/', 'Origin':self.home, 'Accept':'application/json, text/plain, */*'}
        if self.platform=='bili':
            from media_platform.bilibili.client import BilibiliClient
            self.client=BilibiliClient(timeout=25, headers=headers, playwright_page=self.page, cookie_dict=cookie_dict)
        elif self.platform=='wb':
            from media_platform.weibo.client import WeiboClient
            # Keep upstream endpoint methods, but do not use its retry/decode-
            # error navigation loop or log raw responses/cookies.
            class AuditedWeiboClient(WeiboClient):
                async def request(self, method, url, **kwargs):
                    import httpx
                    async with httpx.AsyncClient(follow_redirects=False) as transport:
                        response=await transport.request(method,url,timeout=self.timeout,**kwargs)
                    if response.status_code in (401,403,412,429):
                        raise CollectionStop('access_denied')
                    if response.is_redirect:raise CollectionStop('needs_user_auth')
                    response.raise_for_status()
                    try:data=response.json()
                    except ValueError:raise CollectionStop('non_json_response') from None
                    if data.get('ok')!=1:raise CollectionStop('platform_response_error')
                    return data.get('data') or {}
            self.client=AuditedWeiboClient(timeout=25,headers=headers,playwright_page=self.page,cookie_dict=cookie_dict)
        elif self.platform=='zhihu':
            from media_platform.zhihu import help as zhihu_help
            from media_platform.zhihu.client import ZhiHuClient
            import execjs
            # Upstream loads the signer from a cwd-relative path; load it from the pinned vendor tree.
            if not zhihu_help.ZHIHU_SGIN_JS:
                zhihu_help.ZHIHU_SGIN_JS=execjs.compile((Path(CFG['mediacrawler'])/'libs/zhihu.js').read_text(encoding='utf-8-sig'))
            self.client=ZhiHuClient(timeout=25,headers={'accept':'*/*','accept-language':'zh-CN,zh;q=0.9','cookie':cookie_str,
                'referer':'https://www.zhihu.com/search?type=content','user-agent':headers['User-Agent'],'x-api-version':'3.0.91',
                'x-app-za':'OS=Web','x-requested-with':'fetch','x-zse-93':'101_3_3.0'},playwright_page=self.page,cookie_dict=cookie_dict)
        else:
            from media_platform.xhs.client import XiaoHongShuClient
            # The upstream client serializes POST bodies as JSON strings; its
            # official factory supplies this header, so the adapter must too.
            headers['Content-Type']='application/json;charset=UTF-8'
            self.client=XiaoHongShuClient(timeout=25, headers=headers, playwright_page=self.page, cookie_dict=cookie_dict)

    async def auth_status(self):
        try:
            # Building the client reads the live page; during a login redirect that can fail transiently.
            await self.setup_client()
            if self.platform=='douyin':
                return await self.capture.auth_status()
            if self.platform=='bili':
                result=await asyncio.wait_for(self.client.get('/x/web-interface/nav', enable_params_sign=False),30)
                self.ledger.manifest['auth_evidence']={'isLogin':result.get('isLogin')}
                return 'authenticated' if result.get('isLogin') is True else 'unauthenticated'
            if self.platform=='zhihu':
                if not self.client.cookie_dict.get('d_c0'):return 'unauthenticated'
                try:result=await asyncio.wait_for(self.client.get_current_user_info(),45)
                except Exception as exc:
                    text=str(exc)
                    return 'unauthenticated' if any(x in text for x in ('登录','login','100','401')) else safe_error(exc)
                self.ledger.manifest['auth_evidence']={'has_uid':bool(result.get('uid'))}
                return 'authenticated' if result.get('uid') else 'unauthenticated'
            if self.platform=='wb':
                result=await asyncio.wait_for(self.client.get('/api/config'),30)
                logged=result.get('login')
                self.ledger.manifest['auth_evidence']={'login':logged is True or logged==1}
                return 'authenticated' if logged is True or logged==1 else 'unauthenticated'
            result=await asyncio.wait_for(self.client.query_self(),30)
            if not isinstance(result,dict):return 'unknown_response'
            data=result.get('data') or {}
            ok=(data.get('result') or {}).get('success')
            basic=data.get('basic_info') or {}
            guest=basic.get('guest',basic.get('is_guest'))
            cookies=await self.context.cookies([self.home])
            has_session=any(x['name']=='web_session' and bool(x['value']) for x in cookies)
            me=self.page.locator("a[href*='/user/profile/']").filter(has=self.page.locator('span',has_text=re.compile('^我$')))
            try:ui_me=await me.first.is_visible(timeout=1500)
            except Exception:ui_me=False
            self.ledger.manifest['auth_evidence']={'response_keys':list(result),'data_keys':list(data),
                'basic_info_keys':list(basic),'operation_success':ok,'guest':guest,'ui_me_visible':ui_me,
                'has_user_id':bool(basic.get('user_id')),'has_session_cookie':has_session}
            if guest is True:return 'unauthenticated'
            if guest is False and basic.get('user_id') and has_session:return 'authenticated'
            if ok is True and ui_me and has_session:return 'authenticated'
            # The profile endpoint only returns red_id/nickname for a signed-in account; the page's
            # "我" link may not have rendered yet in a background window.
            if ok is True and has_session and (basic.get('red_id') or basic.get('nickname')):return 'authenticated'
            return 'unauthenticated' if ok is False or result.get('success') is False else 'unknown_response'
        except Exception as exc:
            return safe_error(exc)

    async def session(self, playwright, round_name):
        profile=Path(self.ledger.manifest['browser_profile'])
        was_present=profile.exists() and any(profile.iterdir())
        profile.mkdir(parents=True,exist_ok=True);os.chmod(profile,0o700)
        self.home={'bili':'https://www.bilibili.com','xhs':'https://www.xiaohongshu.com','wb':'https://m.weibo.cn','douyin':'https://www.douyin.com','zhihu':'https://www.zhihu.com'}[self.platform]
        self.context=await playwright.chromium.launch_persistent_context(str(profile),
            executable_path=CFG['browser_executable'],headless=not self.args.interactive,
            args=['--mute-audio'],
            viewport={'width':1280,'height':900},accept_downloads=False)
        # Set before navigation: covers newly created audio/video elements too.
        # Chromium's mute switch also covers audio beyond HTML media elements.
        await self.context.add_init_script("""(() => {
          const mute = () => document.querySelectorAll('video,audio').forEach(e => {
            e.defaultMuted = true; e.muted = true; e.volume = 0;
          });
          new MutationObserver(mute).observe(document, {subtree:true, childList:true});
          document.addEventListener('play', mute, true); mute();
        })();""")
        self.page=self.context.pages[0] if self.context.pages else await self.context.new_page()
        if self.platform=='douyin':
            from douyin_capture import BrowserCapture
            self.capture=BrowserCapture(self)
            self.page.on('response',self.capture.receive)
        if self.args.manual_start and round_name=='initial':
            # After an access restriction, the user restores normal access manually.
            # Do not navigate or probe the denied origin until explicit user readiness.
            await self.page.goto('about:blank')
            ready=RUNTIME/('manual-ready-'+self.ledger.run_id)
            self.ledger.manifest.update(status='waiting_for_manual_access',manual_ready_file=str(ready))
            self.ledger.flush()
            print(json.dumps({'event':'manual_access_needed','platform':self.platform,'run_path':str(self.ledger.path)},ensure_ascii=False),flush=True)
            deadline=time.monotonic()+self.args.wait
            while not ready.exists() and time.monotonic()<deadline:
                await asyncio.sleep(2)
            if not ready.exists():raise CollectionStop('needs_manual_access')
            ready.unlink()
            if not self.page.url.startswith(self.home):raise CollectionStop('manual_navigation_not_confirmed')
        try:
            response=None if self.args.manual_start and round_name=='initial' else await self.page.goto(self.home,wait_until='commit',timeout=45000)
            if response and response.status in (401,403,412,429):
                self.ledger.event('navigation_denied',http_status=response.status)
                raise CollectionStop('access_denied')
            await asyncio.sleep(3)
        except CollectionStop:
            raise
        except Exception as exc:
            reason=safe_error(exc)
            self.ledger.event('navigation_error',reason=reason,exception=type(exc).__name__)
            raise CollectionStop(reason) from None
        status=await self.auth_status()
        if self.platform=='douyin' and status=='unknown_response':
            # Wait for the existing page/self-profile response to render. This
            # observes the page only; it sends no repeated authentication calls.
            deadline=time.monotonic()+15
            while status=='unknown_response' and time.monotonic()<deadline:
                await asyncio.sleep(1)
                status=await self.auth_status()
        self.ledger.manifest['auth_checks'].append(dict(round=round_name,at=now(),status=status,profile_reused=was_present))
        self.ledger.manifest['status']='ready' if status=='authenticated' else status
        self.ledger.flush()
        print(json.dumps({'event':'auth_status','platform':self.platform,'round':round_name,'status':status,'run_path':str(self.ledger.path)},ensure_ascii=False),flush=True)
        return status

    async def wait_auth(self):
        if not self.args.interactive:return False
        initial=await self.auth_status()
        if initial=='authenticated':return True
        # A browser window is visible; the user performs login and any verification.
        self.ledger.manifest['status']='waiting_for_user_login'
        self.ledger.flush()
        print(json.dumps({'event':'needs_user_login','platform':self.platform,'wait_seconds':self.args.wait},ensure_ascii=False),flush=True)
        deadline=time.monotonic()+self.args.wait
        while time.monotonic()<deadline:
            await asyncio.sleep(8)
            status=await self.auth_status()
            if status=='authenticated':
                self.ledger.manifest['auth_checks'].append(dict(round='after_login_wait',at=now(),status=status))
                self.ledger.flush()
                return True
            # The user is mid-login in a visible window: redirects, QR pages and CAPTCHAs
            # make probes fail transiently. Keep waiting; only an explicit denial stops.
            self.ledger.event('auth_probe',status=status)
            if status=='access_denied':raise CollectionStop(status)
        return False

    def save_comment(self, post_id, raw, root=None):
        record=normalize_comment(self.platform,post_id,raw,self.ledger,root)
        if record['id'] not in self.observed and len(self.observed)>=self.args.max_records:
            raise CollectionStop('record_limit_reached')
        self.observed.add(record['id'])
        return record,self.ledger.save(record)

    async def search(self):
        if self.platform=='douyin':return await self.capture.search()
        from media_platform.xhs.help import get_search_id
        search_id=get_search_id()
        candidates=[];seen=set()
        for pn in range(1,self.args.search_pages+1):
            if self.platform=='bili':
                res=await self.call('search',lambda:self.client.search_video_by_keyword(self.args.keyword,page=pn),page=pn)
                items=res.get('result') or []
                ids=[identifier(x.get('aid') or x.get('id')) for x in items]
            elif self.platform=='zhihu':
                found=await self.call('search',lambda:self.client.get_note_by_keyword(self.args.keyword,page=pn),page=pn)
                items=[x.model_dump() for x in found];res={'items':items,'has_more':bool(items)}
                ids=[identifier(x.get('content_id')) for x in items]
            elif self.platform=='wb':
                res=await self.call('search',lambda:self.client.get_note_by_keyword(self.args.keyword,page=pn),page=pn)
                items=weibo_cards(res.get('cards'))
                ids=[identifier(x.get('idstr') or x.get('id')) for x in items]
            else:
                res=await self.call('search',lambda:self.client.get_note_by_keyword(self.args.keyword,search_id=search_id,page=pn),page=pn)
                items=[x for x in (res.get('items') or []) if x.get('model_type')=='note' or x.get('note_card')]
                ids=[identifier(x.get('id')) for x in items]
            fresh=[x for x in ids if x and x not in seen];seen.update(x for x in ids if x)
            e=self.ledger.event('search_page',page=pn,keyword=self.args.keyword,returned_ids=ids,new_ids=fresh,source_has_more=res.get('has_more'),declared_total=res.get('numResults') or res.get('total'),response_keys=list(res),raw_items_count=len(res.get('items') or res.get('result') or []))
            self.ledger.manifest['search_pages'].append(e)
            self.ledger.flush()
            candidates.extend(items)
            if not items:break
        # Prefer titles clearly about the requested App; all selected samples remain technical samples.
        def relevant(x):
            card=x.get('note_card') or x
            title=plain_html(card.get('display_title') or card.get('title') or card.get('text') or '')
            names={self.args.app,re.sub(r'(?i)\s*(app|客户端|软件)$','',self.args.app)}
            return any(n and n in title for n in names)
        def comment_count(x):
            try:return int(x.get('comments_count') or 0)
            except (TypeError,ValueError):return 0
        # This is a technical pagination sample, not an issue-priority rank.
        return sorted(candidates,key=lambda x:(not relevant(x),-comment_count(x) if self.platform=='wb' else 0))

    async def collect_post(self,item,info=None):
        # info: an already fetched detail response, so callers do not request it twice.
        if self.platform=='douyin':return await self.capture.collect_post(item)
        if self.platform=='wb':
            return await self.collect_weibo_post(item,info)
        if self.platform=='zhihu':
            return await self.collect_zhihu_post(item)
        if self.platform=='bili':
            pid=str(item.get('aid') or item.get('id'))
            info=info or await self.call('post_detail',lambda:self.client.get_video_info(aid=int(pid)),post_id=pid)
            post=normalize_post(self.platform,pid,info)
            token=None
        else:
            pid=str(item['id']);token=item.get('xsec_token') or (item.get('note_card') or {}).get('xsec_token') or ''
            info=info or await self.call('post_detail',lambda:self.client.get_note_by_id(pid,item.get('xsec_source') or 'pc_search',token),post_id=pid)
            post=normalize_post(self.platform,pid,info)
        self.ledger.save(post);self.ledger.add_post(post)
        self.ledger.flush()
        if post.get('declared_comments') in (0,'0'):
            # A declared zero is not a verified end page; record it and save the request.
            self.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=0,declared_total=0,stop_reason='declared_zero_comments_not_probed'))
            self.ledger.export();return
        cursor=0 if self.platform=='bili' else '';seen=set();main_stop='page_limit_reached'
        for pn in range(1,self.args.main_pages+1):
            if self.platform=='bili':
                res=await self.call('main_comments',lambda:self.client.get_video_comments(pid,next=cursor),post_id=pid,page=pn)
                roots=list(res.get('replies') or [])
                if pn==1:
                    from media_platform.bilibili.client import _extract_pinned_comments
                    roots=_extract_pinned_comments((res.get('top'),res.get('top_replies')))+roots
                control=res.get('cursor') or {};end=control.get('is_end') is True;next_cursor=control.get('next')
            else:
                res=await self.call('main_comments',lambda:self.client.get_note_comments(pid,token,cursor),post_id=pid,page=pn)
                roots=res.get('comments') or []
                end=res.get('has_more') is False;next_cursor=res.get('cursor')
            ids=[];new=[]
            for raw in roots:
                rec,_=self.save_comment(pid,raw);cid=rec['id'];ids.append(cid)
                if cid in seen:continue
                seen.add(cid);new.append(cid)
                await self.replies(pid,token,raw,cid)
            self.ledger.event('main_page',post_id=pid,page=pn,cursor=cursor,next_cursor=next_cursor,returned_ids=ids,new_ids=new,source_end=end)
            if end:main_stop='source_end_confirmed';break
            if next_cursor is None or next_cursor==cursor:main_stop='no_cursor_progress_unconfirmed';break
            if not new:main_stop='no_new_ids_unconfirmed';break
            cursor=next_cursor
        self.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=len(seen),declared_total=post.get('declared_comments'),stop_reason=main_stop))
        self.ledger.export()

    async def collect_weibo_post(self,item,info=None):
        pid=str(item.get('idstr') or item['id'])
        info=info or await self.call('post_detail',lambda:self.client.get_note_info_by_id(pid),post_id=pid)
        post=normalize_post('wb',pid,info)
        self.ledger.save(post);self.ledger.add_post(post);self.ledger.flush()
        if post.get('declared_comments') in (0,'0'):
            # A declared zero is not an API failure and not a verified end page.
            self.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=0,
                declared_total=0,stop_reason='declared_zero_comments_not_probed'))
            self.ledger.export();return
        cursor=0;cursor_type=0;seen=set();stop='page_limit_reached'
        for pn in range(1,self.args.main_pages+1):
            res=await self.call('main_comments',lambda:self.client.get_note_comments(pid,cursor,cursor_type),post_id=pid,page=pn)
            roots=res.get('data') or [];ids=[];fresh=[]
            next_cursor=res.get('max_id');next_type=res.get('max_id_type',0)
            for raw in roots:
                rec,_=self.save_comment(pid,raw);cid=rec['id'];ids.append(cid)
                if cid in seen:continue
                seen.add(cid);fresh.append(cid)
                children=raw.get('comments');children=children if isinstance(children,list) else []
                child_ids=set()
                for child in children:
                    sub,_=self.save_comment(pid,child,cid);child_ids.add(sub['id'])
                declared=raw.get('total_number')
                if children or declared:
                    # Pinned upstream exposes embedded replies only. Never
                    # label this as a fully paginated reply conversation.
                    self.ledger.manifest['threads'].append(dict(kind='reply',post_id=pid,root_id=cid,
                        declared_total=declared,unique_ids=len(child_ids),stop_reason='embedded_preview_only',
                        declared_count_gap=None if declared is None else str(declared)!=str(len(child_ids))))
            end=next_cursor in (0,'0')
            self.ledger.event('main_page',post_id=pid,page=pn,cursor=cursor,next_cursor=next_cursor,
                returned_ids=ids,new_ids=fresh,source_end=end)
            if end:stop='source_end_confirmed';break
            if next_cursor is None or (str(next_cursor)==str(cursor) and next_type==cursor_type):stop='no_cursor_progress_unconfirmed';break
            if not fresh:stop='no_new_ids_unconfirmed';break
            cursor=int(next_cursor);cursor_type=next_type
        self.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=len(seen),
            declared_total=post.get('declared_comments'),stop_reason=stop))
        self.ledger.export()

    async def collect_zhihu_post(self,item):
        from model.m_zhihu import ZhihuContent
        pid=str(item['content_id']);content=ZhihuContent(**item)
        post=normalize_post('zhihu',pid,item)
        self.ledger.save(post);self.ledger.add_post(post);self.ledger.flush()
        if not item.get('comment_count'):
            self.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=0,declared_total=0,stop_reason='declared_zero_comments_not_probed'))
            self.ledger.export();return
        offset='';seen=set();stop='page_limit_reached'
        for pn in range(1,self.args.main_pages+1):
            res=await self.call('main_comments',lambda:self.client.get_root_comments(pid,content.content_type,offset,10),post_id=pid,page=pn)
            paging=(res or {}).get('paging') or {};end=paging.get('is_end') is True
            roots=[x.model_dump() for x in self.client._extractor.extract_comments(content,(res or {}).get('data'))]
            next_offset=self.client._extractor.extract_offset(paging);ids=[];fresh=[]
            for raw in roots:
                rec,_=self.save_comment(pid,raw);cid=rec['id'];ids.append(cid)
                if cid in seen:continue
                seen.add(cid);fresh.append(cid)
                declared=raw.get('sub_comment_count') or 0
                if declared and declared>=(getattr(self.args,'reply_min',0) or 0):await self.zhihu_replies(pid,content,raw,cid)
                elif declared:self.ledger.manifest['threads'].append(dict(kind='reply',post_id=pid,root_id=cid,declared_total=declared,unique_ids=0,
                    stop_reason='preview_kept_below_reply_threshold',declared_count_gap=True))
            self.ledger.event('main_page',post_id=pid,page=pn,cursor=offset,next_cursor=next_offset,returned_ids=ids,new_ids=fresh,source_end=end)
            if end:stop='source_end_confirmed';break
            if not next_offset or next_offset==offset:stop='no_cursor_progress_unconfirmed';break
            if not fresh:stop='no_new_ids_unconfirmed';break
            offset=next_offset
        self.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=len(seen),declared_total=post.get('declared_comments'),stop_reason=stop))
        self.ledger.export()

    async def zhihu_replies(self,pid,content,root,cid):
        declared=root.get('sub_comment_count');offset='';seen=set();stop='page_limit_reached'
        for pn in range(1,self.args.reply_pages+1):
            res=await self.call('reply_comments',lambda:self.client.get_child_comments(cid,offset,10),post_id=pid,root_id=cid,page=pn)
            paging=(res or {}).get('paging') or {};end=paging.get('is_end') is True
            children=[x.model_dump() for x in self.client._extractor.extract_comments(content,(res or {}).get('data'))]
            next_offset=self.client._extractor.extract_offset(paging);ids=[];new=[]
            for raw in children:
                rec,_=self.save_comment(pid,raw,cid);ids.append(rec['id'])
                if rec['id'] not in seen:new.append(rec['id']);seen.add(rec['id'])
            self.ledger.event('reply_page',post_id=pid,root_id=cid,page=pn,cursor=offset,next_cursor=next_offset,returned_ids=ids,new_ids=new,source_end=end)
            if end:stop='source_end_confirmed';break
            if not next_offset or next_offset==offset:stop='no_cursor_progress_unconfirmed';break
            if not new:stop='no_new_ids_unconfirmed';break
            offset=next_offset
        self.ledger.manifest['threads'].append(dict(kind='reply',post_id=pid,root_id=cid,declared_total=declared,unique_ids=len(seen),stop_reason=stop,
            declared_count_gap=declared is not None and declared!=len(seen)))
        self.ledger.flush()

    async def replies(self,pid,token,root,cid):
        from media_platform.bilibili.field import CommentOrderType
        declared=root.get('rcount') if self.platform=='bili' else root.get('sub_comment_count')
        try:declared=int(declared)
        except (TypeError,ValueError):declared=None
        preview=root.get('replies') if self.platform=='bili' else root.get('sub_comments')
        seen=set()
        for raw in preview or []:
            rec,_=self.save_comment(pid,raw,cid);seen.add(rec['id'])
        if declared==0 and not seen:return
        min_replies=getattr(self.args,'reply_min',0) or 0
        if self.platform=='xhs' and root.get('sub_comment_has_more') is False:
            stop='source_end_confirmed'
        elif not declared and not seen:
            return
        elif declared is not None and len(seen)>=declared:
            # The embedded preview already holds every declared reply.
            stop='source_end_confirmed'
        elif declared is not None and declared<min_replies:
            # Low-reply threads keep the embedded preview; recorded so it is never called complete.
            stop='preview_kept_below_reply_threshold'
        else:
            cursor=1 if self.platform=='bili' else root.get('sub_comment_cursor') or ''
            stop='page_limit_reached'
            for pn in range(1,self.args.reply_pages+1):
                if self.platform=='bili':
                    res=await self.call('reply_comments',lambda:self.client.get_video_level_two_comments(pid,int(cid),cursor,10,CommentOrderType.DEFAULT),post_id=pid,root_id=cid,page=pn)
                    children=res.get('replies') or []
                    page=res.get('page') or {};total=page.get('count')
                    end=isinstance(total,int) and cursor*10>=total
                    next_cursor=cursor+1
                else:
                    res=await self.call('reply_comments',lambda:self.client.get_note_sub_comments(pid,cid,token,num=10,cursor=cursor),post_id=pid,root_id=cid,page=pn)
                    children=res.get('comments') or [];end=res.get('has_more') is False;next_cursor=res.get('cursor')
                ids=[];new=[]
                for raw in children:
                    rec,_=self.save_comment(pid,raw,cid);ids.append(rec['id'])
                    if rec['id'] not in seen:new.append(rec['id']);seen.add(rec['id'])
                self.ledger.event('reply_page',post_id=pid,root_id=cid,page=pn,cursor=cursor,next_cursor=next_cursor,returned_ids=ids,new_ids=new,source_end=end)
                if end:stop='source_end_confirmed';break
                if next_cursor is None or next_cursor==cursor:stop='no_cursor_progress_unconfirmed';break
                if not new:stop='no_new_ids_unconfirmed';break
                cursor=next_cursor
        gap=(declared is not None and declared!=len(seen))
        self.ledger.manifest['threads'].append(dict(kind='reply',post_id=pid,root_id=cid,declared_total=declared,unique_ids=len(seen),stop_reason=stop,declared_count_gap=gap))
        self.ledger.flush()


class CollectionStop(Exception):
    pass


async def run(args):
    # The browser-response adapter imports these same classes and stop signals.
    sys.modules.setdefault('collect',sys.modules[__name__])
    from profile_lock import acquire_profile_lock
    from playwright.async_api import async_playwright
    import vendor_loader;vendor_loader.prepare(CFG['mediacrawler'])
    import config
    config.PLATFORM=args.platform;config.ENABLE_IP_PROXY=False;config.ENABLE_CDP_MODE=False
    config.ENABLE_GET_SUB_COMMENTS=True;config.SAVE_LOGIN_STATE=True
    from tools import utils
    utils.logger.disabled=True
    ledger=Ledger(args.platform,args.app,args.command,profile_name=args.profile)
    ledger.manifest.update(browser_mode='interactive' if args.interactive else 'background',audio_muted=True)
    ledger.flush()
    lockpath=RUNTIME/('profile-'+args.platform+'-'+args.profile+'.lock')
    lockpath.touch(mode=0o600,exist_ok=True)
    with lockpath.open('r+',encoding='utf-8') as lock:
        try:acquire_profile_lock(lock)
        except BlockingIOError:raise SystemExit('This platform profile already has a running task')
        c=Collector(args,ledger)
        try:
            async with async_playwright() as p:
                status=await c.session(p,'initial')
                # Background runs stop on any blocked state; a visible login window lets the user resolve it.
                if status=='access_denied' or (not args.interactive and status in ('network_error','verification_required','platform_response_error')):
                    raise CollectionStop(status)
                if status!='authenticated':
                    if not args.interactive:
                        raise CollectionStop('needs_interactive_login' if status=='unauthenticated' else 'auth_state_unconfirmed')
                    if not args.wait or not await c.wait_auth():raise CollectionStop(status if args.wait==0 else 'needs_user_auth')
                if args.command=='context':
                    source=Path(args.source_run).resolve()
                    if source.parent!=(OUTPUT/'runs').resolve():raise ValueError('source run must be inside the evidence runs directory')
                    original=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
                    if original['platform']!=args.platform or original.get('browser_profile')!=ledger.manifest['browser_profile']:
                        raise ValueError('context refresh requires the same platform and account profile')
                    ledger.manifest['source_run']=original['run_id']
                    posts=[json.loads(x) for x in (source/'records.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
                    for old in posts:
                        if old['kind']!='post':continue
                        if args.platform!='bili':raise ValueError('context refresh currently supports Bilibili only')
                        info=await c.call('refresh_post_context',lambda: c.client.get_video_info(aid=int(old['id'])),post_id=old['id'])
                        post=normalize_post(args.platform,old['id'],info)
                        ledger.save(post);ledger.manifest['posts'].append(post);ledger.flush()
                    ledger.manifest['status']='context_refreshed'
                elif args.command=='pilot':
                    # Reopen only for an explicit persistence test. Routine
                    # batches share this one background context throughout.
                    if args.verify_reuse:
                        await c.context.close();c.context=None
                        status=await c.session(p,'reopen_same_profile')
                        if status!='authenticated':raise CollectionStop('session_reuse_failed')
                    ledger.manifest['status']='collecting';ledger.flush()
                    items=await c.search()
                    if not items:raise CollectionStop('search_empty_unconfirmed')
                    selected=set()
                    for item in items:
                        pid=str(item.get('aweme_id') or item.get('aid') or item.get('content_id') or item.get('id'))
                        if pid in selected:continue
                        selected.add(pid)
                        await c.collect_post(item)
                        if len(selected)>=args.max_posts:break
                    ledger.manifest['status']='pilot_finished'
                else:
                    ledger.manifest['status']='authenticated'
                    if args.keep_open:
                        ledger.manifest['status']='browser_ready'
                        ledger.flush()
                        print(json.dumps({'event':'browser_ready','platform':args.platform,'profile':args.profile,
                            'site':c.home,'run_path':str(ledger.path)},ensure_ascii=False),flush=True)
                        deadline=time.monotonic()+args.keep_open
                        while time.monotonic()<deadline and not c.page.is_closed():
                            await asyncio.sleep(2)
                        ledger.manifest['status']='authenticated'
        except CollectionStop as exc:
            ledger.manifest['status']=str(exc)
        except asyncio.CancelledError:
            ledger.manifest['status']='user_interrupted'
            raise
        except Exception as exc:
            ledger.manifest['status']=safe_error(exc)
            ledger.manifest['errors'].append(dict(operation='runtime',reason=safe_error(exc),exception=type(exc).__name__))
        finally:
            if c.context:
                try:await c.context.close()
                except Exception:pass
            ledger.manifest['finished_at']=now()
            counts=ledger.export();ledger.db.close()
            print(json.dumps({'run_path':str(ledger.path),'status':ledger.manifest['status'],'counts':counts},ensure_ascii=False),flush=True)


def gate():
    """Per-platform technical readiness for scaling up collection.

    Blockers stop expansion on that platform only. Source limits that cannot be fixed by
    collecting again (e.g. Weibo returns embedded reply previews only) are warnings. One
    platform failing never blocks another, and an adapter marked pending is reported as such.
    """
    results={}
    all_runs=[]
    for f in (OUTPUT/'runs').glob('*/manifest.json') if (OUTPUT/'runs').exists() else []:
        try:all_runs.append((f,json.loads(f.read_text(encoding='utf-8'))))
        except (ValueError,OSError):continue
    scope=CFG.get('source_scope',{})
    pending=set(scope.get('local_adapter_pending',[]))
    platforms=list(dict.fromkeys(scope.get('core_social',['bili','xhs'])+scope.get('enabled_support_social',[])))
    for platform in platforms:
        if platform in pending:
            results[platform]={'status':'adapter_pending','passed':False,'blockers':['adapter_not_implemented'],'warnings':[]};continue
        batches=[(f,m) for f,m in all_runs if m.get('platform')==platform and m.get('mode') in ('pilot','recent_sample')
            and m.get('finished_at') and m.get('status') in ('pilot_finished','recent_sample_finished')]
        if not batches:
            tried=[m.get('status') for _,m in all_runs if m.get('platform')==platform]
            results[platform]={'status':'not_run','passed':False,'blockers':['no_finished_collection_batch'],'warnings':[],'last_statuses':tried[-3:]};continue
        f,m=max(batches,key=lambda x:x[1]['started_at'])
        pages=[json.loads(x) for x in (f.parent/'pages.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()] if (f.parent/'pages.jsonl').exists() else []
        blockers=[];warnings=[]
        reused=[a for _,a in all_runs if a.get('platform')==platform and a.get('browser_profile')==m.get('browser_profile')
            and any(x.get('profile_reused') and x.get('status')=='authenticated' for x in a.get('auth_checks',[]))]
        if not reused:blockers.append('saved_login_not_reused_in_a_new_process')
        threads=m.get('threads',[])
        if not any(t['kind']=='main' and t['stop_reason']=='source_end_confirmed' for t in threads):blockers.append('no_comment_thread_reached_source_end')
        counts=m.get('counts',{})
        if not counts.get('posts'):blockers.append('no_post_text_collected')
        fatal=[e for e in m.get('errors',[]) if e.get('operation')!='post_comments_skipped']
        if fatal:blockers.append('run_errors')
        main_pages={}
        for e in pages:
            if e['kind']=='main_page' and e.get('new_ids'):main_pages.setdefault(e.get('post_id'),set()).add(e.get('page'))
        if not any(len(x)>=2 for x in main_pages.values()):warnings.append('main_comment_pagination_not_exercised')
        replies=[t for t in threads if t['kind']=='reply']
        if any(t['stop_reason']=='embedded_preview_only' for t in replies):warnings.append('replies_preview_only_source_limit')
        if any(t['stop_reason']=='preview_kept_below_reply_threshold' for t in replies):warnings.append('small_reply_threads_kept_as_preview')
        if counts.get('missing_roots') or counts.get('missing_reply_targets'):warnings.append('some_reply_parents_missing')
        if any(e.get('operation')=='post_comments_skipped' for e in m.get('errors',[])):warnings.append('some_posts_comments_unavailable')
        results[platform]={'status':'ready' if not blockers else 'blocked','passed':not blockers,'blockers':blockers,'warnings':warnings,
            # Kept for older readers of this file.
            'reasons':blockers,'run_path':str(f.parent),'mode':m.get('mode'),'counts':counts}
    ready=[p for p,r in results.items() if r['passed']]
    report={'ready_platforms':ready,'can_expand_any':bool(ready),
        'can_expand':bool(results) and all(r['passed'] for r in results.values()),
        'platforms':results,'checked_at':now(),
        'scope':'technical readiness only, judged per platform; does not grant platform or software permissions or meet sample targets'}
    write_json(OUTPUT/'expansion-gate.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


def main():
    # A local installation always uses its isolated environment, regardless of caller cwd/Python.
    desired=Path(CFG['python'])
    if Path(sys.prefix).resolve()!=desired.parent.parent.resolve() and desired.exists():
        os.execv(str(desired),[str(desired),str(Path(__file__).resolve()),*sys.argv[1:]])
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('gate')
    for cmd in ('auth','pilot','context'):
        q=sub.add_parser(cmd);q.add_argument('--platform',choices=['xhs','bili','wb','douyin','zhihu'],required=True)
        q.add_argument('--app',required=cmd!='auth',default='账号登录检查' if cmd=='auth' else None);q.add_argument('--keyword')
        q.add_argument('--wait',type=int,default=900);q.add_argument('--delay',type=float,default=1.5)
        q.add_argument('--reply-min',type=int,default=0,help='only page replies for threads declaring at least N replies; smaller threads keep the preview')
        q.add_argument('--search-pages',type=int,default=2);q.add_argument('--max-posts',type=int,default=2)
        q.add_argument('--main-pages',type=int,default=4);q.add_argument('--reply-pages',type=int,default=4)
        q.add_argument('--max-records',type=int,default=250)
        q.add_argument('--manual-start',action='store_true',help='open a blank dedicated browser; wait for explicit local readiness before probing')
        q.add_argument('--profile',choices=['default','research'],help='separate local browser profile; never fall back to another account')
        q.add_argument('--keep-open',type=int,default=0,help='keep an authenticated browser visible for this many seconds without extra collection requests')
        q.add_argument('--interactive',action='store_true',help='show the dedicated muted browser only for user login/verification or an explicitly requested foreground check')
        q.add_argument('--verify-reuse',action='store_true',help='explicitly close/reopen once to test session persistence; routine collection does not reopen')
        if cmd=='context':q.add_argument('--source-run',required=True)
    a=p.parse_args()
    if a.command=='doctor':
        print(json.dumps({'python':sys.executable,'mediacrawler_present':Path(CFG['mediacrawler']).exists(),
            'browser_present':Path(CFG['browser_executable']).exists(),
            # The core set in requirements-core.txt, by import name.
            'packages':{x:bool(importlib.util.find_spec(x)) for x in ['playwright','httpx','tenacity','pydantic','xhshow','execjs','PIL','humps','parsel']},
            # Zhihu request signing runs the vendored JS through Node.js.
            'node_for_zhihu':__import__('shutil').which('node'),
            'no_login_sources':['appbao (scripts/appbao.py)','appstore (scripts/appstore.py)','web (scripts/web_import.py)'],
            'revision':CFG['revision'],'profiles':str(RUNTIME/'profiles')},ensure_ascii=False,indent=2));return
    if a.command=='gate':gate();return
    a.profile=a.profile or CFG.get('profiles',{}).get(a.platform,'default')
    a.keyword=a.keyword or (a.app+' 功能')
    if a.manual_start and not a.interactive:p.error('--manual-start requires --interactive')
    if a.keep_open and not a.interactive:p.error('--keep-open requires --interactive')
    if a.delay<1.5 or not 1<=a.max_records<=500 or not 1<=a.search_pages<=3 or not 1<=a.max_posts<=4 or not 1<=a.main_pages<=8 or not 1<=a.reply_pages<=8:
        p.error('pilot limits: delay>=1.5s, max_records 1..500, search_pages 1..3, max_posts 1..4, main/reply_pages 1..8')
    asyncio.run(run(a))


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
