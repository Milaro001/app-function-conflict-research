#!/usr/bin/env python3
"""Merge selected cached/public and MediaCrawler evidence without network calls.

Keep source IDs, original retrieval times, immutable input hashes and context gaps.
This creates a research corpus, not semantic labels or a popularity estimate.
"""
import sys
import argparse
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import collect


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_key(body):
    return ''.join(unicodedata.normalize('NFKC', body or '').split()).casefold()


def date_value(value):
    if not value:return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:return None


def temporal_layer(value, as_of):
    dt=date_value(value)
    if not dt:return 'undated'
    if dt>as_of:return 'future_or_clock_error'
    try:year_cutoff=as_of.replace(year=as_of.year-1)
    except ValueError:year_cutoff=as_of.replace(year=as_of.year-1,day=28)
    if dt>=as_of-timedelta(days=90):return 'recent_90d'
    if dt>=year_cutoff:return 'recent_12m'
    return 'historical'


def provenance(path, **extra):
    return dict(source_file=str(Path(path).resolve()),source_sha256=digest(path),**extra)


def appbao_rows(folder, app):
    path=Path(folder)/'comments.json'
    audit=json.loads((Path(folder)/'validation.json').read_text(encoding='utf-8'))
    fresh='listing' in audit  # written by scripts/appbao.py; older caches lack it
    origin=provenance(path,acquisition='appbao_public_api' if fresh else 'prior_public_frontend_run',fresh_collection=fresh)
    records=[]
    for row in json.loads(path.read_text(encoding='utf-8')):
        if row.get('app_name')!=app:raise ValueError('Cached AppBao data belongs to a different App')
        cid=str(row['review_id'])
        records.append(dict(platform='appbao',kind='comment',id=cid,post_id=row['app_id'],
            level=1,root_id=cid,parent_id=None,reply_to_id=None,parent_relation='top_level',
            # Reviews sit on the Android store listing; the author's own device is not stated.
            client='android',client_basis='store_listing',
            body=row.get('body') or '',published_at=row.get('date'),retrieved_at=row.get('retrieved_at'),
            source_url=row.get('source_url'),rating=row.get('rating'),version=row.get('version'),
            declared_replies=row.get('reply_count_declared'),context_status='replies_not_collected_in_expanded_run',
            provenance=origin))
    return records,dict(status='collected' if fresh else 'cached_import',pagination=audit.get('pagination') or 'see validation.json',
        original_collected_at=audit['completed_at'],main_only=True,
        visible_source_end=(audit.get('stop_reasons') or {}).get('time','short_page'),
        limitations=['Reply bodies not collected.']+(['AppBao exposes a limited newest-first list; low recent volume is a source limit.'] if fresh else []))


def forum_rows(folder, platform):
    records=[];topics=[]
    for path in sorted(Path(folder).glob(platform+'-*.json')):
        data=json.loads(path.read_text(encoding='utf-8'));tid=str(data['topic_id'])
        origin=provenance(path,acquisition='public_text_snapshot' if platform=='v2ex' else 'prior_discourse_public_stream',fresh_collection=False)
        posts=data.get('posts',[])
        # Floors restart in each topic; a bare floor number is not a site-wide ID.
        floor_ids={int(x['floor']):str(x.get('post_id') or f'topic-{tid}-floor-{x["floor"]}') for x in posts}
        if platform=='v2ex':
            records.append(dict(platform=platform,kind='post',id=tid,post_id=tid,title=data.get('title'),
                body=data.get('topic_body_with_supplements') or data.get('topic_body') or '',published_at=None,
                retrieved_at=data.get('collection_date'),source_url=data['url'],context_status='cached_text_only',provenance=origin))
            root=tid
        else:root=floor_ids.get(1)
        for row in posts:
            cid=floor_ids[int(row['floor'])]
            target_floor=row.get('reply_to_floor');target=floor_ids.get(target_floor)
            if target_floor and not target:target='missing-floor-'+str(target_floor)
            is_root=platform=='appinn' and row['floor']==1
            item=dict(platform=platform,kind='post' if is_root else 'comment',id=cid,post_id=tid,
                title=data.get('title') if is_root else None,body=row.get('text') or '',
                level=None if is_root else 1,root_id=root,parent_id=target,reply_to_id=target,
                parent_relation='explicit' if target else 'topic_container',
                # V2EX display dates lack year/timezone. Do not infer them from ID or retrieval.
                published_at=row.get('created_at') if platform=='appinn' else None,
                published_at_display=row.get('created_at_display'),retrieved_at=data.get('collection_date'),
                source_url=row.get('url'),floor=row.get('floor'),
                context_status='public_stream_text' if platform=='appinn' else 'cached_text_only',
                quoted_text=row.get('quoted_text') or [q.get('text') for q in row.get('quotes',[])],
                mentioned_floor_numbers=row.get('mentioned_floor_numbers',[]),
                media_context_status='not_interpreted',provenance=origin)
            if platform=='appinn':
                # Request sidecars record the original acquisition clock, not the import clock.
                raw=Path(folder).parent/'raw'/f'appinn-{tid}-initial.json.request.json'
                if raw.exists():item['retrieved_at']=json.loads(raw.read_text(encoding='utf-8')).get('fetched_at_utc')
            records.append(item)
        topics.append(dict(topic_id=tid,visible_stream_complete=data.get('complete_visible_stream'),
            live_server_verified=data.get('live_server_completeness_verified',False),
            missing_floors=data.get('missing_floor_numbers') or data.get('empty_body_floors') or [],
            declared=data.get('declared_posts_count') or data.get('declared_reply_count')))
    return records,dict(status='cached_import',topics=topics,
        limitations=['V2EX uses earlier cached text; '+str(sum(1 for r in records if r['kind']=='comment' and not (r.get('body') or '').strip()))+' displayed replies have no body; dates are unverified.'] if platform=='v2ex'
        else ['Visible stream only; unlisted/deleted posts and image contents unverified.'])


def live_rows(root, platform, app):
    runs=[]
    for path in (Path(root)/'runs').glob('*/manifest.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['platform']==platform and data.get('app')==app:runs.append((path,data))
    # Bounded pilots and recent-sample batches are both collection runs. Merge every
    # finished batch by source ID (later observation wins) so earlier batches are not
    # silently dropped; identical IDs are never counted twice.
    batches=sorted([(p,d) for p,d in runs if d['mode'] in ('pilot','recent_sample') and d.get('finished_at')],key=lambda x:x[1]['started_at'])
    if not batches:return [],dict(status='no_completed_pilot',limitations=['No completed live pilot.'])
    path,data=batches[-1]
    by_key={};gaps=set()
    for batch_path,batch in batches:
        record_file=batch_path.parent/'records.jsonl'
        if not record_file.exists():continue
        origin=provenance(record_file,acquisition='mediacrawler_'+batch['mode'],run_id=batch['run_id'],fresh_collection=True)
        for line in record_file.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            row=json.loads(line);row['provenance']=origin;by_key[(row['kind'],row['id'])]=row
        # Metadata repair is a separate recorded observation; never edit original pilot files.
        overlays=[(p,d) for p,d in runs if d.get('source_run')==batch['run_id'] and d.get('status')=='context_refreshed']
        for overlay,meta in sorted(overlays,key=lambda x:x[1]['started_at']):
            source=overlay.parent/'records.jsonl'
            for line in source.read_text(encoding='utf-8').splitlines():
                row=json.loads(line)
                row['provenance']=provenance(source,acquisition='metadata_followup',run_id=meta['run_id'],source_run=batch['run_id'],fresh_collection=True)
                by_key[(row['kind'],row['id'])]=row
        gaps|=set((batch.get('counts') or {}).get('missing_reply_targets',[]))
    present={r['id'] for r in by_key.values() if r['kind']=='comment'}
    for row in by_key.values():
        # A target missing in one batch may arrive in another batch.
        target=row.get('reply_to_id')
        row['context_status']='missing_direct_reply_target' if row['id'] in gaps and target not in present else 'returned_links_only'
    pages=path.parent/'pages.jsonl'
    events=[json.loads(x) for x in pages.read_text(encoding='utf-8').splitlines()] if pages.exists() else []
    auth=[d for _,d in runs if d.get('mode') in ('auth','context') and d.get('started_at','')>=data['finished_at']
        and d.get('browser_profile')==data.get('browser_profile') and d.get('process_id')!=data.get('process_id')
        and any(a['status']=='authenticated' and a.get('profile_reused') for a in d.get('auth_checks',[]))]
    return list(by_key.values()),dict(status=data['status'],run_id=data['run_id'],profile_name=data.get('profile_name'),
        session_reopen=any(a['round']=='reopen_same_profile' and a['status']=='authenticated' for a in data.get('auth_checks',[])),
        cross_process_reuse=bool(auth),page_responses=dict(Counter(e['kind'] for e in events)),
        thread_stop_reasons=dict(Counter(t['stop_reason'] for t in data.get('threads',[]))),
        counts=data.get('counts',{}),merged_run_ids=[d['run_id'] for _,d in batches],
        limitations=['Technical sample; post images and video not interpreted.'])


def appstore_rows(folder, app):
    folder=Path(folder);meta=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if meta.get('app')!=app:raise ValueError('App Store data belongs to a different App')
    path=folder/'records.jsonl';origin=provenance(path,acquisition='itunes_public_rss',fresh_collection=True)
    records=[dict(json.loads(x),provenance=origin) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    return records,dict(status='collected',listing=meta.get('listing'),collected_at=meta.get('completed_at'),
        stop_reason=meta.get('stop_reason'),limitations=meta.get('limitations',[]))


def web_rows(path, app):
    path=Path(path);origin=provenance(path,acquisition='agent_public_web_read',fresh_collection=True)
    records=[dict(json.loads(x),provenance=origin) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if any(r.get('app')!=app for r in records):raise ValueError('Web evidence belongs to a different App')
    return records,dict(status='public_web_import',sites=dict(Counter(r.get('site') for r in records)),
        limitations=['Agent-read public page excerpts; not a complete crawl of any site.'])


def annotate(records,as_of):
    by_id={};conflicts=[]
    for row in records:
        key=(row['platform'],row['kind'],row['id'])
        if key in by_id and by_id[key].get('body')!=row.get('body'):conflicts.append(key)
        by_id[key]=row
    ordered=sorted(by_id.values(),key=lambda r:(r['platform'],r['kind'],r['id']))
    groups={}
    for row in ordered:
        row['evidence_id']=':'.join((row['platform'],row['kind'],row['id']))
        body=row.get('body') or ''
        row['nonempty_body']=bool(body.strip());row['text_usable']=any(ch.isalnum() for ch in body)
        row['temporal_layer']=temporal_layer(row.get('published_at'),as_of)
        row['semantic_status']='not_reviewed'
        # Same text remains inspectable in every source. The group prevents repeat
        # text from being silently counted as independent support.
        signature=text_key(body)
        row['text_group']=hashlib.sha256(signature.encode()).hexdigest() if row['text_usable'] else None
        row['duplicate_text_of']=groups.get(row['text_group']) if row['text_group'] else None
        if row['text_group']:groups.setdefault(row['text_group'],row['evidence_id'])
    return ordered,conflicts


def build(args):
    cfg=collect.CFG;cached=cfg.get('cached_sources',{})
    records=[];sources={}
    appbao=args.appbao_dir or cached.get('appbao')
    forums=args.forums_dir or cached.get('forums')
    if cached.get('app')!=args.app:
        # A new App request must never inherit the NetEase demo corpus.
        appbao=args.appbao_dir;forums=args.forums_dir
    import appbao as appbao_source, appstore as appstore_source, web_import
    # Default to this App's most recent public-store / web collections when not given explicitly.
    appbao=appbao or appbao_source.latest_dir(collect.OUTPUT,args.app)
    appstore=args.appstore_dir or appstore_source.latest_dir(collect.OUTPUT,args.app)
    web=args.web_file or web_import.latest_file(collect.OUTPUT,args.app)
    for platform in ('appbao','appstore','appinn','v2ex','bili','xhs','wb','douyin','zhihu','web'):
        if platform=='appbao' and appbao:rows,meta=appbao_rows(appbao,args.app)
        elif platform=='appstore' and appstore:rows,meta=appstore_rows(appstore,args.app)
        elif platform=='web' and web:rows,meta=web_rows(web,args.app)
        elif platform in ('appinn','v2ex') and forums:rows,meta=forum_rows(forums,platform)
        elif platform in ('bili','xhs','wb','douyin','zhihu'):rows,meta=live_rows(collect.OUTPUT,platform,args.app)
        else:rows,meta=[],dict(status='input_not_configured')
        if platform in args.defer:meta.update(status='deferred_by_user',collection_attempts_resumed=False)
        sources[platform]=meta;records.extend(rows)
    as_of=date_value(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if not as_of:raise ValueError('as-of requires an ISO timestamp with timezone')
    records,conflicts=annotate(records,as_of)
    if conflicts:raise ValueError('Conflicting duplicate IDs; inspect source namespaces before importing')
    for platform,meta in sources.items():
        rows=[r for r in records if r['platform']==platform]
        usable=[r for r in rows if r['text_usable']]
        comments=[r for r in usable if r['kind']=='comment']
        meta['corpus_counts']=dict(record_ids=len(rows),post_ids=sum(r['kind']=='post' for r in rows),
            comment_ids=sum(r['kind']=='comment' for r in rows),nonempty_bodies=sum(r['nonempty_body'] for r in rows),
            usable_text_bodies=len(usable),usable_comment_bodies=len(comments),
            unique_text_groups=len({r['text_group'] for r in usable}),
            comment_temporal_layers=dict(Counter(r['temporal_layer'] for r in comments)),
            published_min=min((r['published_at'] for r in rows if date_value(r.get('published_at'))),default=None),
            published_max=max((r['published_at'] for r in rows if date_value(r.get('published_at'))),default=None))
    out=Path(args.output or collect.OUTPUT/'corpus');out.mkdir(parents=True,exist_ok=True)
    with (out/'evidence.jsonl').open('w',encoding='utf-8') as f:
        for row in records:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    collect.RUNTIME.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(collect.RUNTIME/'evidence.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS corpus_entries_v2(app TEXT,platform TEXT,kind TEXT,id TEXT,payload TEXT,PRIMARY KEY(app,platform,kind,id))')
        # This is a reproducible current snapshot; raw collector tables and runs stay intact.
        db.execute('DELETE FROM corpus_entries_v2 WHERE app=?',(args.app,))
        db.executemany('INSERT INTO corpus_entries_v2 VALUES(?,?,?,?,?)',[(args.app,r['platform'],r['kind'],r['id'],json.dumps(r,ensure_ascii=False)) for r in records])
    comments=[r for r in records if r['kind']=='comment' and r['text_usable']]
    report=dict(app=args.app,built_at=collect.now(),as_of=as_of.isoformat(),sources=sources,
        total_record_ids=len(records),usable_comment_bodies=len(comments),
        unique_comment_text_groups=len({r['text_group'] for r in comments}),
        recent_12m_unique_comment_text_groups=len({r['text_group'] for r in comments if r['temporal_layer'] in ('recent_90d','recent_12m')}),
        exact_text_groups_all_bodies=len({r['text_group'] for r in records if r['text_usable']}),
        comment_temporal_layers=dict(Counter(r['temporal_layer'] for r in comments)),
        conflicting_duplicate_ids=conflicts,
        semantic_reviewed=0,qualified_function_feedback=None,qualified_conflicts=None,
        limitations=['Source IDs are not unique people.','Merged corpus is not 2000 current, relevant, qualified feature reviews.',
            'No semantic classifications or priority ranks have been inferred by this import.'])
    collect.write_json(out/'coverage.json',report)
    lines=[f'# {args.app}多来源采集整合','',f'统计截止：{as_of.isoformat()}。原文、引用关系和采集来源已统一入库。','',
        '| 来源 | 评论ID | 可用评论正文 | 近12个月（含90天） | 历史 | 日期不明 | 状态 |',
        '|---|---:|---:|---:|---:|---:|---|']
    names={'appbao':'应用宝','appstore':'App Store','appinn':'小众软件论坛','v2ex':'V2EX','bili':'B站','xhs':'小红书','wb':'微博','douyin':'抖音','zhihu':'知乎','web':'公开网页补证'}
    for platform,meta in sources.items():
        c=meta['corpus_counts'];t=c['comment_temporal_layers']
        lines.append(f"| {names[platform]} | {c['comment_ids']} | {c['usable_comment_bodies']} | {t.get('recent_90d',0)+t.get('recent_12m',0)} | {t.get('historical',0)} | {t.get('undated',0)} | {meta['status']} |")
    lines+=['','正文可用只表示不是空白或纯符号，尚未判定是否为具体功能反馈。帖子正文单列，不作为评论数量重复相加。',
        '近12个月以各条评论的发布时间判断；不能因为旧帖最近被回复，就将全帖算作近期。',
        '应用宝与App Store由公开接口采集（无需登录）；论坛为既有缓存导入。社媒合并同一App各站全部已结束批次（试采与近期抽样），按来源ID去重，不重复计数；未接入或待登录不称采集通过。',
        '核心社媒为小红书、微博、知乎；B站与抖音补充。各站实际状态见上表，扩量仍须按平台通过采集与上下文门槛。','',
        '详见 coverage.json 的各站翻页和缺口，以及 evidence.jsonl 中逐条原文与来源哈希。']
    (out/'来源整合结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(out),'records':len(records),'usable_comment_bodies':len(comments),
        'temporal_layers':report['comment_temporal_layers'],'semantic_reviewed':0},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',required=True);p.add_argument('--appbao-dir');p.add_argument('--forums-dir')
    p.add_argument('--appstore-dir');p.add_argument('--web-file',type=Path)
    p.add_argument('--output');p.add_argument('--as-of');p.add_argument('--defer',nargs='*',default=[],choices=['wb','xhs','bili','douyin','zhihu'])
    build(p.parse_args())
