"""Discover recent posts, then collect explicitly selected IDs and their context.

Reuses the bounded collector's isolated sessions, delay and stop rules. Search
summaries are discovery leads; only fetched post bodies are research evidence.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import collect as c


async def discover(owner, keywords, pages):
    from media_platform.xhs.help import get_search_id
    from media_platform.xhs.field import SearchSortType
    from media_platform.bilibili.field import SearchOrderType
    from media_platform.weibo.field import SearchType
    from media_platform.zhihu.field import SearchSort as ZhihuSort, SearchTime as ZhihuTime
    items = {}; skipped = 0
    for keyword in keywords:
        search_id = get_search_id()
        for pn in range(1,pages+1):
          try:
            if owner.platform == 'xhs':
                res = await owner.call('recent_search',lambda:owner.client.get_note_by_keyword(keyword,search_id=search_id,page=pn,sort=SearchSortType.LATEST),page=pn)
                raw = [x for x in res.get('items',[]) if x.get('note_card')]
            elif owner.platform == 'bili':
                res = await owner.call('recent_search',lambda:owner.client.search_video_by_keyword(keyword,page=pn,order=SearchOrderType.LAST_PUBLISH),page=pn)
                raw = res.get('result') or []
            elif owner.platform == 'zhihu':
                found = await owner.call('recent_search',lambda:owner.client.get_note_by_keyword(keyword,page=pn,sort=ZhihuSort.DEFAULT,search_time=ZhihuTime.ONE_YEAR),page=pn)
                raw = [x.model_dump() for x in found]; res = {'has_more': bool(raw)}
            else:
                res = await owner.call('recent_search',lambda:owner.client.get_note_by_keyword(keyword,page=pn,search_type=SearchType.REAL_TIME),page=pn)
                raw = c.weibo_cards(res.get('cards'))
          except c.CollectionStop as stop:
            # One failed keyword page must not end the batch; a block or CAPTCHA still does.
            if str(stop) in ('access_denied','verification_required','needs_user_auth') or skipped>=3:raise
            skipped+=1
            # Let a rate limit clear before the next keyword instead of failing it too.
            await asyncio.sleep(30 if owner.platform=='xhs' else 10)
            break
          if True:
            ids=[]
            for x in raw:
                pid = str(x.get('aid') or x.get('idstr') or x.get('content_id') or x.get('id'))
                if pid == 'None': continue
                ids.append(pid)
                items.setdefault(pid,{'item':x,'keywords':[],'order':len(items)})['keywords'].append(keyword)
            owner.ledger.manifest['search_pages'].append(owner.ledger.event('recent_search_page',keyword=keyword,page=pn,order='latest',returned_ids=ids,source_has_more=res.get('has_more')))
            # Persist after every page so a later failed page keeps earlier discoveries.
            save_candidates(owner.ledger,items)
            owner.ledger.flush()
            if not raw or res.get('has_more') is False: break
    return items


def save_candidates(ledger,items):
    # Source access tokens stay in the private local runtime; the run folder gets briefs only.
    private=c.RUNTIME/'search-candidates';private.mkdir(mode=0o700,parents=True,exist_ok=True)
    c.write_json(private/(ledger.run_id+'.json'),items)
    (private/(ledger.run_id+'.json')).chmod(0o600)
    c.write_json(ledger.path/'candidates.json',[brief(pid,entry) for pid,entry in items.items()])


def brief(pid,entry):
    x=entry['item'];card=x.get('note_card') or x
    return {'id':pid,'title':c.plain_html(card.get('display_title') or card.get('title') or card.get('text') or ''),
            'published_at':c.timestamp(x.get('pubdate') or x.get('created_at') or x.get('created_time') or x.get('time') or card.get('time')),
            # XHS search cards carry only a display label such as "3天前".
            'published_display':next((t.get('text') for t in card.get('corner_tag_info') or [] if t.get('type')=='publish_time'),None),
            'keywords':entry['keywords']}


APP_WORDS=('app','App','APP','软件','客户端','小程序','更新','版本','页面','功能')


def auto_select(app,items,limit,since=None,topics=()):
    """Newest-first candidates whose title/body names the App; a fast default, not a relevance verdict."""
    names={app,re.sub(r'(?i)\s*(app|客户端|软件)$','',app)}
    rows=[];titles=set()
    # Newest first, so a repeated title keeps its most recent upload.
    ordered=sorted(items.items(),key=lambda kv:(brief(*kv)['published_at'] or '',-kv[1].get('order',0)),reverse=True)
    for pid,entry in ordered:
        b=brief(pid,entry);x=entry['item'];card=x.get('note_card') or x
        text=b['title']+' '+c.plain_html(card.get('desc') or card.get('content_text') or '')
        if not any(n and n in text for n in names):continue
        # Short or common App names ("菜鸟") also appear in unrelated posts; also require a planned
        # feature word or a word about the software itself.
        if not any(t in text for t in (*topics,*APP_WORDS)):continue
        if since and b['published_at'] and b['published_at']<since:continue
        # Repeated listing titles are usually product ads re-uploaded; keep one.
        key=re.sub(r'\W+','',b['title'])[:24]
        if key and key in titles:continue
        titles.add(key)
        rows.append((entry['keywords'][0],b['published_at'] or '',-entry.get('order',0),pid))
    # Newest first within each keyword, then round-robin so one keyword cannot fill the batch.
    by_kw={}
    for kw,date,order,pid in sorted(rows,reverse=True):by_kw.setdefault(kw,[]).append(pid)
    picked=[]
    while len(picked)<limit and any(by_kw.values()):
        for kw in list(by_kw):
            if by_kw[kw] and len(picked)<limit:picked.append(by_kw[kw].pop(0))
    return picked


async def detail(owner,item):
    pid=str(item.get('aid') or item.get('idstr') or item.get('content_id') or item.get('id'))
    if owner.platform=='zhihu':
        # The search hit is the full answer/article; no detail request is needed.
        return c.normalize_post('zhihu',pid,item),item
    if owner.platform=='bili':
        info=await owner.call('post_detail',lambda:owner.client.get_video_info(aid=int(pid)),post_id=pid)
    elif owner.platform=='wb':
        info=await owner.call('post_detail',lambda:owner.client.get_note_info_by_id(pid),post_id=pid)
    else:
        token=item.get('xsec_token') or (item.get('note_card') or {}).get('xsec_token') or ''
        info=await owner.call('post_detail',lambda:owner.client.get_note_by_id(pid,item.get('xsec_source') or 'pc_search',token),post_id=pid)
    return c.normalize_post(owner.platform,pid,info),info


async def sample_posts(owner,ledger,items,selected,args):
    # Capture all selected post contexts before comment limits.
    fetched={}
    for pid in selected:
        post,info=await detail(owner,items[pid]['item'])
        ledger.save(post);ledger.add_post(post);fetched[pid]=info;ledger.export()
    if args.comments:
        for pid in fetched:
            original_save=owner.save_comment
            post_seen=set()
            def bounded_save(post_id,raw,root=None):
                cid=str(raw.get('cid') or raw.get('rpid_str') or raw.get('rpid') or raw.get('idstr') or raw.get('id'))
                if cid not in post_seen and len(post_seen)>=args.per_post_records:raise c.CollectionStop('per_post_record_limit')
                result=original_save(post_id,raw,root);post_seen.add(result[0]['id']);return result
            owner.save_comment=bounded_save
            # Reuse the detail response fetched above; no second request per post.
            try:await owner.collect_post(items[pid]['item'],fetched[pid])
            except c.CollectionStop as e:
                ledger.manifest.setdefault('comment_stops',[]).append({'post_id':pid,'reason':str(e),'unique_comments_in_attempt':len(post_seen)})
                if str(e)=='per_post_record_limit':continue
                # A single post can have comments closed or deleted; skip it. Stop the
                # comment path on a block/login signal or repeated failures only.
                failures=ledger.manifest.setdefault('comment_failures',0)+1;ledger.manifest['comment_failures']=failures
                if str(e) in ('access_denied','verification_required','needs_user_auth','network_error') or failures>=3:
                    ledger.manifest['comment_stop_reason']=str(e)
                    break
                ledger.manifest['errors'].append({'operation':'post_comments_skipped','post_id':pid,'reason':str(e)})
                continue
            finally:owner.save_comment=original_save


async def run(args):
    from playwright.async_api import async_playwright
    import vendor_loader;vendor_loader.prepare(c.CFG['mediacrawler'])
    import config
    config.PLATFORM=args.platform;config.ENABLE_IP_PROXY=False;config.ENABLE_CDP_MODE=False
    from tools import utils
    utils.logger.disabled=True
    args.interactive=False;args.manual_start=False;args.wait=0
    args.keyword=args.keyword[0] if args.mode=='sample' else args.keyword
    # A one-session collect is a recent-sample batch for merging and the expansion gate.
    ledger=c.Ledger(args.platform,args.app,'recent_sample' if args.mode=='collect' else 'recent_'+args.mode,profile_name=args.profile)
    ledger.manifest.update(browser_mode='background',audio_muted=True,sampling_purpose='recent relevant post inventory; relevance reviewed separately',search_order='latest',target_posts=10)
    ledger.flush()
    from profile_lock import acquire_profile_lock
    lockpath=c.RUNTIME/('profile-'+args.platform+'-'+args.profile+'.lock')
    lockpath.touch(mode=0o600,exist_ok=True)
    with lockpath.open('r+',encoding='utf-8') as lock:
        try:acquire_profile_lock(lock)
        except BlockingIOError:raise SystemExit('This platform profile already has a running task')
        owner=c.Collector(args,ledger)
        try:
            async with async_playwright() as p:
                status=await owner.session(p,'initial')
                if status!='authenticated': raise c.CollectionStop(status)
                if args.mode=='discover':
                    items=await discover(owner,args.keyword,args.pages)
                    ledger.manifest.update(status='discovery_finished',candidate_ids=list(items),keywords=args.keyword)
                elif args.mode=='collect':
                    # Discover, select and sample in one browser session: one launch and one login check.
                    items=await discover(owner,args.keyword,args.pages)
                    selected=auto_select(args.app,items,args.auto_select or 30,args.since,args.topics)
                    ledger.manifest.update(candidate_ids=list(items),keywords=args.keyword,selected_ids=selected)
                    if not selected:raise c.CollectionStop('no_candidate_names_app')
                    await sample_posts(owner,ledger,items,selected,args)
                    ledger.manifest['status']='recent_sample_finished'
                else:
                    source=c.OUTPUT/'runs'/args.source_run
                    meta=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
                    if meta['platform']!=args.platform or meta['app']!=args.app or meta['profile_name']!=args.profile: raise ValueError('source app/platform/profile mismatch')
                    items=json.loads((c.RUNTIME/'search-candidates'/(args.source_run+'.json')).read_text(encoding='utf-8'))
                    selected=auto_select(args.app,items,args.auto_select,args.since,args.topics) if args.auto_select else args.post_ids.split(',')
                    if not selected:raise c.CollectionStop('no_candidate_names_app')
                    if len(set(selected))!=len(selected) or any(i not in items for i in selected):raise ValueError('invalid selected IDs')
                    ledger.manifest.update(source_search=args.source_run,selected_ids=selected)
                    await sample_posts(owner,ledger,items,selected,args)
                    ledger.manifest['status']='recent_sample_finished'
        except c.CollectionStop as e:ledger.manifest['status']=str(e)
        except Exception as e:
            ledger.manifest['status']=c.safe_error(e)
            ledger.manifest['errors'].append({'operation':'runtime','exception':type(e).__name__,'reason':c.safe_error(e)})
        finally:
            if owner.context:
                try:await owner.context.close()
                except Exception:pass  # async_playwright already closed the driver
            ledger.manifest['finished_at']=c.now();counts=ledger.export();ledger.db.close()
    print(json.dumps({'run_id':ledger.run_id,'status':ledger.manifest['status'],'counts':counts},ensure_ascii=False),flush=True)


def main():
    desired=Path(c.CFG['python'])
    if Path(sys.prefix).resolve()!=desired.parent.parent.resolve() and desired.exists():
        os.execv(str(desired),[str(desired),str(Path(__file__).resolve()),*sys.argv[1:]])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['discover','sample','collect'],help='collect = discover + auto-select + sample in one session')
    parser.add_argument('--platform',choices=['xhs','wb','bili','zhihu'],required=True)
    parser.add_argument('--app',required=True)
    parser.add_argument('--keyword',action='append',default=[])
    parser.add_argument('--keyword-plan',type=Path,help='keywords.json from keywords.py; uses its list for this platform')
    parser.add_argument('--auto-select',type=int,default=0,help='sample: pick up to N newest candidates naming the App instead of --post-ids')
    parser.add_argument('--since',help='sample --auto-select: skip candidates published before this ISO date')
    parser.add_argument('--pages',type=int,default=2)
    parser.add_argument('--source-run')
    parser.add_argument('--post-ids')
    parser.add_argument('--comments',action='store_true')
    parser.add_argument('--delay',type=float,default=1.5)
    parser.add_argument('--reply-min',type=int,default=0,help='page replies only for threads declaring >= N replies')
    parser.add_argument('--main-pages',type=int,default=2)
    parser.add_argument('--reply-pages',type=int,default=2)
    parser.add_argument('--max-records',type=int,default=500)
    parser.add_argument('--per-post-records',type=int,default=60)
    args=parser.parse_args();args.profile=c.CFG.get('profiles',{}).get(args.platform,'research')
    args.topics=()
    if args.keyword_plan:
        plan=json.loads(args.keyword_plan.read_text(encoding='utf-8'));args.topics=tuple(plan.get('features') or ())
        if not args.keyword:args.keyword=plan.get('platforms',{}).get(args.platform) or plan['keywords']
    if not args.keyword:args.keyword=[args.app+' 功能']
    if not 1<=args.pages<=5 or not 1<=len(args.keyword)<=12 or args.delay<1.5:parser.error('bounded discovery: 1..5 pages, 1..12 keywords, delay>=1.5')
    if not 1<=args.main_pages<=10 or not 1<=args.reply_pages<=8 or not 1<=args.max_records<=3000:parser.error('bounded comments: main pages 1..10, reply pages 1..8, records 1..3000')
    if not 1<=args.per_post_records<=300:parser.error('per-post-records must be 1..300')
    if args.mode=='sample' and not args.source_run:parser.error('sample needs --source-run')
    if args.mode=='sample' and not args.auto_select and (not args.post_ids or not 1<=len(args.post_ids.split(','))<=60):parser.error('sample needs --post-ids (1..60) or --auto-select N')
    if not 0<=args.auto_select<=60:parser.error('auto-select must be 0..60')
    asyncio.run(run(args))

if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
