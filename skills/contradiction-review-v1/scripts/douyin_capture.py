"""Capture only responses produced by normal actions in a dedicated Douyin page.

No replayed signatures, fabricated security headers, private-browser cookies or
direct API retries. JSON field mappings follow the pinned MediaCrawler client.
"""
import asyncio
import json
import re
import time
from urllib.parse import urlparse, parse_qs, quote


def decode_payloads(text):
    """Decode ordinary JSON or byte-sized frames returned by search/stream.

    Frame lengths count UTF-8 bytes, not Python characters. A truncated frame
    must not become an empty successful search or a confirmed source end.
    """
    try:
        value=json.loads(text)
        if not isinstance(value,dict):raise ValueError('expected object')
        return [value]
    except json.JSONDecodeError:pass
    data=text.encode('utf-8');pos=0;frames=[];terminated=False
    while pos<len(data):
        while pos<len(data) and data[pos:pos+1] in (b'\r',b'\n',b' ',b'\t'):pos+=1
        if pos==len(data):break
        match=re.match(rb'([0-9a-fA-F]+)\r?\n',data[pos:])
        if not match:raise ValueError('invalid stream boundary')
        size=int(match.group(1),16);pos+=match.end()
        if size==0:terminated=True;break
        if pos+size>len(data):raise ValueError('truncated stream frame')
        value=json.loads(data[pos:pos+size]);pos+=size
        if not isinstance(value,dict):raise ValueError('expected frame object')
        frames.append(value)
    if not frames or not terminated:raise ValueError('incomplete search stream')
    return frames


def search_items(data):
    items=[]
    for row in data.get('data') or []:
        if not isinstance(row,dict):continue
        info=row.get('aweme_info')
        if isinstance(info,dict) and info.get('aweme_id'):items.append(info)
        mix=(row.get('aweme_mix_info') or {}).get('mix_items') or []
        items.extend(x for x in mix if isinstance(x,dict) and x.get('aweme_id'))
    return items


def response_kind(url):
    u=urlparse(url)
    if u.hostname not in ('www.douyin.com','www-hj.douyin.com'):return None
    path=u.path
    if '/web/comment/list/reply/' in path:return 'reply_page'
    if '/web/comment/list/' in path:return 'main_page'
    if '/web/general/search/' in path or '/web/search/item/' in path:return 'search_page'
    if '/web/aweme/detail/' in path:return 'post_detail'
    if '/web/user/profile/self/' in path:return 'self_profile'
    return None


class BrowserCapture:
    def __init__(self,owner):
        self.o=owner;self.tasks=set();self.items={};self.selected=set()
        self.failure=None;self.self_verified=False;self.counter={};self.streams={};self.verification_signal=False
        self.search_event=asyncio.Event()
        self.search_started=False

    def receive(self,response):
        if not response_kind(response.url):return
        task=asyncio.create_task(self.consume(response));self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def settle(self):
        if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)
        if self.failure:
            from collect import CollectionStop
            raise CollectionStop(self.failure)

    async def consume(self,response):
        from collect import normalize_post
        try:
            kind=response_kind(response.url)
            if response.status in (401,403,412,429):
                self.failure='access_denied';return
            if response.status!=200:return
            try:
                data=await response.json();payloads=[data]
            except Exception:
                try:payloads=decode_payloads(await asyncio.wait_for(response.text(),45))
                except (ValueError,asyncio.TimeoutError):
                    self.failure='unrecognized_response_format';return
                data=payloads[-1]
            if not isinstance(data,dict):return
            if any(d.get('status_code') not in (None,0) for d in payloads if isinstance(d,dict)):
                self.failure='platform_response_error';return
            if kind=='self_profile':
                user=data.get('user') or {}
                self.self_verified=bool(user.get('uid') not in (None,'',0,'0') and not user.get('is_guest'))
                return
            if kind=='search_page':
                if not self.search_started:return
                q=parse_qs(urlparse(response.url).query)
                actual_query=(q.get('keyword') or [None])[0]
                if actual_query is not None and actual_query!=self.o.args.keyword:
                    self.o.ledger.event('ignored_search_response',reason='different_query');return
                content=[d for d in payloads if 'data' in d]
                if any((d.get('search_nil_info') or {}).get('search_nil_type')=='verify_check' for d in content):
                    self.verification_signal=True
                    self.search_event.set()
                    self.o.ledger.event('verification_required',operation='search_response');return
                items=[item for d in content for item in search_items(d)];new=[]
                if items:self.verification_signal=False
                data=content[-1] if content else data
                for item in items:
                    pid=str(item['aweme_id'])
                    if pid not in self.items:new.append(pid)
                    self.items[pid]=item
                self.counter[kind]=self.counter.get(kind,0)+1
                e=self.o.ledger.event(kind,page=self.counter[kind],keyword=actual_query,requested_keyword=self.o.args.keyword,
                    source_query_verified=actual_query==self.o.args.keyword,
                    cursor=(q.get('offset') or [None])[0],next_cursor=data.get('cursor'),
                    returned_ids=[str(x['aweme_id']) for x in items],new_ids=new,
                    source_has_more=data.get('has_more'),stream_frames=len(payloads),acquisition='normal_browser_response')
                self.o.ledger.manifest['search_pages'].append(e);self.o.ledger.flush();self.search_event.set();return
            q=parse_qs(urlparse(response.url).query)
            pid=(q.get('aweme_id') or q.get('item_id') or [None])[0]
            if kind=='post_detail':
                info=data.get('aweme_detail') or {};pid=str(info.get('aweme_id') or pid or '')
                if pid in self.selected:
                    post=normalize_post('douyin',pid,info);self.o.ledger.save(post)
                return
            if pid not in self.selected:return
            root=(q.get('comment_id') or [None])[0] if kind=='reply_page' else None
            ids=[];new=[]
            for raw in data.get('comments') or []:
                cid=str(raw.get('cid') or '')
                if cid and cid not in self.o.observed and len(self.o.observed)>=self.o.args.max_records:
                    self.failure='record_limit_reached';break
                rec,_=self.o.save_comment(pid,raw,root);ids.append(rec['id'])
                key=(kind,pid,root)
                stream=self.streams.setdefault(key,{'ids':set(),'end':False})
                if rec['id'] not in stream['ids']:new.append(rec['id'])
                stream['ids'].add(rec['id'])
                if kind=='main_page' and raw.get('reply_comment_total'):
                    reply=self.streams.setdefault(('reply_page',pid,rec['id']),{'ids':set(),'end':False})
                    reply['declared']=raw['reply_comment_total']
                    for child in raw.get('reply_comment') or []:
                        sub,_=self.o.save_comment(pid,child,rec['id']);reply['ids'].add(sub['id'])
            key=(kind,pid,root);stream=self.streams.setdefault(key,{'ids':set(),'end':False})
            # Missing has_more is unknown, never an end signal.
            end=(data.get('has_more') in (False,0) if 'has_more' in data else False) and not self.failure
            stream['end']=stream['end'] or end
            self.counter[key]=self.counter.get(key,0)+1
            self.o.ledger.event(kind,post_id=pid,root_id=root,page=self.counter[key],
                cursor=(q.get('cursor') or [None])[0],next_cursor=data.get('cursor'),
                returned_ids=ids,new_ids=new,source_end=end,partial_page=bool(self.failure),acquisition='normal_browser_response')
            self.o.ledger.export()
        except Exception as exc:
            from collect import safe_error
            self.failure=safe_error(exc)

    async def auth_status(self):
        # A cookie or localStorage flag alone is not proof of authentication.
        await self.settle()
        page=self.o.page
        try:
            login=await page.get_by_text('登录',exact=True).first.is_visible(timeout=800)
            logout=await page.get_by_text('退出登录',exact=True).first.is_visible(timeout=800)
            me=await page.locator('a[href*="/user/self"]').first.is_visible(timeout=800)
        except Exception:login=logout=me=False
        self.o.ledger.manifest['auth_evidence']={'self_profile_response_verified':self.self_verified,
            'login_control_visible':login,'logout_visible':logout,'self_link_visible':me}
        if self.self_verified or logout or (me and not login):return 'authenticated'
        return 'unauthenticated' if login else 'unknown_response'

    async def pause(self):
        await asyncio.sleep(self.o.args.delay);await self.settle()

    async def verification_visible(self):
        for frame in self.o.page.frames:
            for selector in ('[id*="captcha"]','[class*="captcha"]','[id*="verify"]'):
                try:
                    nodes=frame.locator(selector)
                    for i in range(min(await nodes.count(),6)):
                        if await nodes.nth(i).is_visible(timeout=500):return True
                except Exception:pass
            if re.search(r'(captcha|verifycenter)',urlparse(frame.url).path,re.I):
                try:
                    if frame!=self.o.page.main_frame and await (await frame.frame_element()).is_visible():return True
                except Exception:pass
        return False

    async def wait_verification(self):
        if not self.verification_signal and not await self.verification_visible():return
        from collect import CollectionStop
        if not self.o.args.interactive:
            self.o.ledger.event('verification_required',operation='background_search')
            raise CollectionStop('needs_interactive_verification')
        self.o.ledger.manifest['status']='waiting_for_user_verification';self.o.ledger.flush()
        self.o.ledger.event('verification_required',operation='browser_search')
        print(json.dumps({'event':'needs_user_verification','platform':'douyin','run_path':str(self.o.ledger.path)},ensure_ascii=False),flush=True)
        deadline=time.monotonic()+self.o.args.wait
        # Observe only the visible page. Never click or solve the challenge.
        while time.monotonic()<deadline:
            await asyncio.sleep(3)
            if self.o.page.is_closed():raise CollectionStop('verification_window_closed')
            if not self.verification_signal and not await self.verification_visible():
                await self.pause();self.o.ledger.manifest['status']='collecting';self.o.ledger.flush();return
        raise CollectionStop('verification_required')

    async def search(self):
        page=self.o.page
        # Submit the same homepage search control observed in the live website.
        # Direct navigation to the search route need not initialize the app.
        fields=page.get_by_placeholder('搜索你感兴趣的内容',exact=True)
        await fields.fill(self.o.args.keyword,timeout=20000)
        self.search_started=True
        await fields.press('Enter')
        try:await asyncio.wait_for(self.search_event.wait(),45)
        except asyncio.TimeoutError:
            from collect import CollectionStop
            raise CollectionStop('search_response_not_observed') from None
        await self.pause()
        await self.wait_verification()
        for _ in range(self.o.args.search_pages-1):
            await page.mouse.wheel(0,750);await self.pause()
        items=list(self.items.values())
        # Retain only target-App descriptions in the technical sample.
        return sorted([x for x in items if self.o.args.app in (x.get('desc') or '') or self.o.args.app.replace('音乐','') in (x.get('desc') or '')],key=lambda x:x.get('create_time') or 0,reverse=True)

    async def collect_post(self,item):
        from collect import normalize_post
        pid=str(item['aweme_id']);self.selected.add(pid)
        post=normalize_post('douyin',pid,item);self.o.ledger.save(post)
        self.o.ledger.manifest['posts'].append(post);self.o.ledger.flush()
        page=self.o.page
        # The visible result opens an SPA player. Direct /video navigation can
        # wait on unrelated resources and need not initialize this view.
        from collect import CollectionStop
        card=page.get_by_text(post['body'][:40],exact=False)
        if await card.count()!=1:raise CollectionStop('post_card_not_uniquely_located')
        await card.click(timeout=7000);await self.pause()
        tip=page.get_by_text('我知道了',exact=True)
        if await tip.count() and await tip.first.is_visible():await tip.first.click(timeout=3000)
        buttons=page.locator('[data-e2e="feed-comment-icon"]');opened=False
        for i in range(min(await buttons.count(),8)):
            button=buttons.nth(i);box=await button.bounding_box()
            if box and box['y']>=0 and box['y']+box['height']<=900 and box['x']>=0:
                await button.click(timeout=5000);await self.pause();opened=True;break
        if not opened:raise CollectionStop('visible_comment_control_not_found')
        clicked=set()
        for _ in range(self.o.args.main_pages):
            # Click only the site's visible reply expander; no API replay.
            expand=page.get_by_text(re.compile(r'^(展开|查看).*\d+.*(回复|条)$'))
            for i in range(min(await expand.count(),20)):
                button=expand.nth(i);label=await button.inner_text()
                if label in clicked or len(clicked)>=self.o.args.reply_pages:continue
                if await button.is_visible():
                    clicked.add(label);await button.click(timeout=3000);await self.pause()
            await page.mouse.move(1130,650);await page.mouse.wheel(0,650);await self.pause()
        for (kind,post_id,root),state in self.streams.items():
            if post_id!=pid:continue
            declared=state.get('declared')
            self.o.ledger.manifest['threads'].append(dict(kind='reply' if root else 'main',post_id=pid,
                root_id=root,unique_ids=len(state['ids']),declared_total=declared,
                declared_count_gap=None if declared is None else int(declared)!=len(state['ids']),
                stop_reason='source_end_confirmed' if state['end'] else 'visible_actions_limit_unconfirmed'))
        if not any(k[1]==pid and k[0]=='main_page' for k in self.streams):
            self.o.ledger.manifest['threads'].append(dict(kind='main',post_id=pid,unique_ids=0,stop_reason='no_comment_response_observed'))
            # Keep a local diagnostic of the visible public post, separate from
            # research evidence. It is not an inferred comment or completeness.
            await page.screenshot(path=str(self.o.ledger.path/'post-diagnostic.png'))
            body=(await page.locator('body').inner_text())[-8000:]
            (self.o.ledger.path/'post-diagnostic.json').write_text(json.dumps({'post_id':pid,'visible_text':body},ensure_ascii=False,indent=2),encoding='utf-8')
        self.o.ledger.export()
        await page.keyboard.press('Escape')
