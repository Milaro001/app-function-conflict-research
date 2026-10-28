#!/usr/bin/env python3
"""Count existing semantic annotations; this module does not label sentiment or infer conflicts."""
import sys
import argparse
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

CODE_NAMES={'P':'具体问题／改动诉求','V':'功能价值／偏好','C':'答疑／转述／附和等背景',
            'U':'上下文或对象待核','G':'泛评／闲聊等非功能内容','E':'事件／评分表态',
            'context_variant':'同文在不同语境下标签不同'}

def text_key(body):
    value=''.join(c for c in unicodedata.normalize('NFKC',body).casefold() if c.isalnum())
    return hashlib.sha256(value.encode()).hexdigest() if value else None

def date(value):
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        return d if d.tzinfo else None
    except (ValueError,TypeError,AttributeError):return None

def candidate(row):
    return (row.get('code') in ('P','V') and row.get('basis') in ('self_report','direct_preference')
            and row.get('context_dependency') in ('none','resolved')
            and bool(row.get('anchor')) and row['anchor'] in row['body'])

def scope_match(row,scope):
    d=date(row.get('published_at'))
    start,end=date(scope.get('start')),date(scope.get('end'))
    return (candidate(row) and d is not None and start is not None and end is not None and start<=d<=end
            and not row.get('scope_exclusion') and row.get('app')==scope.get('app')
            and (scope.get('client')=='all' or row.get('client')==scope.get('client','android'))
            and (not scope.get('version') or row.get('version')==scope['version'])
            and (scope.get('payment','all')=='all' or row.get('payment')==scope['payment']))

def derive(corpus,issue_map,scope):
    """Return inspectable rows and counts at explicit ID and text-group grains."""
    records=[];seen=set()
    for item in corpus:
        if item.get('kind')!='comment':continue
        a=item.get('annotation') or {}
        if a.get('code') not in {'P','V','C','U','G','E'}:raise ValueError('existing semantic annotation is required')
        if item.get('app') not in (None,scope.get('app')):raise ValueError('quantitative corpus belongs to another App')
        eid=item.get('evidence_id') or ':'.join([item['platform'],'comment',str(item['id'])])
        if eid in seen:raise ValueError('duplicate evidence id in quantitative input')
        seen.add(eid)
        r={k:item.get(k) for k in ('app','platform','body','published_at','client','version','payment','source_url','post_id','parent_id')}
        r.update(evidence_id=eid,text_group=text_key(item.get('body') or ''),
                 code=a.get('code','U'),basis=a.get('basis','unknown'),anchor=a.get('anchor'),
                 feature=a.get('feature'),context_dependency=a.get('context_dependency','unresolved'),
                 scope_exclusion=a.get('additional_scope_exclusion'))
        r['semantic_candidate']=candidate(r);r['in_scope']=scope_match(r,scope)
        records.append(r)
    groups=defaultdict(list)
    for r in records:
        if r['text_group']:groups[r['text_group']].append(r)
    selected={g:rs for g,rs in groups.items() if any(r['semantic_candidate'] for r in rs)}
    pv={g:rs for g,rs in groups.items() if any(r['code'] in ('P','V') for r in rs)}
    start,end=date(scope.get('start')),date(scope.get('end'))
    if not start or not end or start>end:raise ValueError('scope needs an ordered timezone-aware time window')
    recent=date(scope.get('recent_start')) or end-timedelta(days=90)
    def within(rs,lo):return any(r['semantic_candidate'] and date(r['published_at']) and lo<=date(r['published_at'])<=end for r in rs)
    within_window={g:rs for g,rs in selected.items() if within(rs,start)}
    qualified={g:rs for g,rs in groups.items() if any(r['in_scope'] for r in rs)}
    codes=Counter(next(iter(s)) if len(s:=set(r['code'] for r in rs))==1 else 'context_variant' for rs in groups.values())
    stages=[('text_groups','去同文及纯符号后',len(groups)),('pv_groups','初筛为问题／价值偏好',len(pv)),
            ('semantic_groups','依据与上下文可用的候选',len(selected)),
            ('window_groups','选定时间内的功能候选',len(within_window)),('qualified_groups','全部选定条件已核齐',len(qualified))]
    stage_ids={
        'text_groups':{r['evidence_id'] for rs in groups.values() for r in rs},
        'pv_groups':{r['evidence_id'] for rs in pv.values() for r in rs},
        'semantic_groups':{r['evidence_id'] for rs in selected.values() for r in rs if r['semantic_candidate']},
        'window_groups':{r['evidence_id'] for rs in within_window.values() for r in rs if r['semantic_candidate'] and date(r['published_at']) and start<=date(r['published_at'])<=end},
        'qualified_groups':{r['evidence_id'] for rs in qualified.values() for r in rs if r['in_scope']}}
    code_rows=[]
    for code in CODE_NAMES:
        ids=[]
        for rs in groups.values():
            s={r['code'] for r in rs};kind=next(iter(s)) if len(s)==1 else 'context_variant'
            if kind==code:ids.extend(r['evidence_id'] for r in rs)
        code_rows.append(dict(code=code,label=CODE_NAMES[code],value=codes[code],record_ids=ids))
    source_rows=[]
    for platform,n in Counter(r['platform'] for r in records).most_common():
        ids=[r['evidence_id'] for r in records if r['platform']==platform]
        source_rows.append(dict(platform=platform,value=n,record_ids=ids))
    buckets=defaultdict(list)
    for g,rs in selected.items():
        ds=[date(r['published_at']) for r in rs if r['semantic_candidate'] and date(r['published_at']) and date(r['published_at'])<=end]
        latest=max(ds) if ds else None
        key='unknown' if latest is None else 'recent90' if latest>=recent else 'earlier_window' if latest>=start else 'historical'
        buckets[key].append(g)
    time_rows=[]
    for key,label in [('recent90','近期观察窗'),('earlier_window','窗口内的较早材料'),('historical','选定窗口之前'),('unknown','日期待核')]:
        gs=set(buckets[key]);time_rows.append(dict(key=key,label=label,value=len(gs),record_ids=sorted(r['evidence_id'] for g in gs for r in selected[g] if r['semantic_candidate'])))
    by_id={r['evidence_id']:r for r in records}
    all_ids={x.get('evidence_id'):x for x in corpus}
    issues=[]
    for iid,mapping in issue_map.items():
        ids=list(dict.fromkeys(mapping.get('candidate_ids',[])))
        if any(x not in by_id for x in ids):raise ValueError('issue map refers to an unavailable comment')
        rs=[by_id[x] for x in ids];gs={r['text_group'] for r in rs if r['text_group']}
        ps=set(mapping.get('source_posts_separate',[]))
        if mapping.get('source_post_separate'):ps.add(mapping['source_post_separate'])
        for r in rs:
            pid=f"{r['platform']}:post:{r['post_id']}"
            if pid in all_ids:ps.add(pid)
        if any(x not in all_ids for x in ps):raise ValueError('issue map refers to an unavailable post')
        platforms=set(r['platform'] for r in rs)|{all_ids[p]['platform'] for p in ps}
        issues.append(dict(issue_id=iid,comment_ids=len(ids),comment_groups=len(gs),
            semantic_groups=len({r['text_group'] for r in rs if r['semantic_candidate'] and r['text_group']}),
            qualified_groups=len({r['text_group'] for r in rs if r['in_scope'] and r['text_group']}),
            recent90_groups=len({r['text_group'] for r in rs if r['semantic_candidate'] and date(r['published_at']) and recent<=date(r['published_at'])<=end}),
            window_groups=len({r['text_group'] for r in rs if r['semantic_candidate'] and date(r['published_at']) and start<=date(r['published_at'])<=end}),
            post_count=len(ps),source_count=len(platforms),platforms=sorted(platforms),record_ids=ids,post_ids=sorted(ps)))
    return dict(schema_version=1,scope=scope,as_of=scope['end'],records=records,
        metrics=dict(raw_comment_ids=len(records),text_groups=len(groups),pv_groups=len(pv),semantic_groups=len(selected),
                     window_groups=len(within_window),qualified_groups=len(qualified),
                     retention_numerator=len(selected),retention_denominator=len(groups)),
        screening=[dict(key=k,label=l,value=n,record_ids=sorted(stage_ids[k])) for k,l,n in stages],
        code_counts=code_rows,source_counts=source_rows,time_counts=time_rows,issue_stats=issues,
        definitions={'grain':'原始条数按平台＋评论ID；同文按NFKC、大小写规范化后保留字母数字归组。',
          'retention':'候选保留率=依据与上下文可用的功能候选组÷去同文且非纯符号组。',
          'candidate':'候选仍包含不同客户端、版本及付费条件；不等同当前范围有效反馈。',
          'time':'同文跨时段出现时，按候选中最新可用发布时间分桶；不是按原帖最后回复时间。近期观察窗起点见scope.recent_start；未指定时为截止时间前90×24小时。',
          'issues':'议题可重叠，且未覆盖全部候选；评论组、帖子数、来源数分列，不相加为人数。',
          'labels':'P/V是功能信息类型，不是负面／正面情绪；未完成情绪标注时不生成情绪占比。',
          'scope':'条件已核齐为0表示当前证据尚未核齐，不表示没有真实需求或没有安卓用户。'})

def validate_analytics(a,report):
    if not isinstance(a,dict) or a.get('schema_version')!=1:raise ValueError('invalid analytics schema')
    rows=a.get('records',[])
    if not isinstance(rows,list):raise ValueError('analytics records must be an array')
    corpus=[]
    for r in rows:
        if not isinstance(r,dict) or not isinstance(r.get('evidence_id'),str) or not isinstance(r.get('body'),str):raise ValueError('invalid analytic record')
        annotation={k:r.get(k) for k in ('code','basis','anchor','feature','context_dependency')}
        annotation['additional_scope_exclusion']=r.get('scope_exclusion')
        corpus.append(dict(r,kind='comment',annotation=annotation,id=r['evidence_id']))
    expected=derive(corpus,{},a.get('scope',{}))
    for key in ('metrics','screening','code_counts','source_counts','time_counts'):
        if a.get(key)!=expected[key]:raise ValueError('quantitative rows do not reconcile: '+key)
    m=a['metrics']
    if m['raw_comment_ids']!=report['counts'].get('raw_comments') or m['semantic_groups']!=report['counts'].get('screened_feedback') or m['qualified_groups']!=report['counts'].get('qualified_in_scope'):
        raise ValueError('headline counts disagree with quantitative records')
    ids={r['evidence_id']:r for r in rows};issue_ids={i['id'] for i in report['issues']}
    for stat in a.get('issue_stats',[]):
        if stat['issue_id'] not in issue_ids:raise ValueError('unknown quantitative issue')
        used=stat.get('record_ids',[])
        if len(used)!=len(set(used)) or any(x not in ids for x in used):raise ValueError('invalid issue record IDs')
        rs=[ids[x] for x in used]
        if stat['comment_ids']!=len(rs) or stat['comment_groups']!=len({text_key(r['body']) for r in rs if text_key(r['body'])}):raise ValueError('issue count mismatch')
        if stat['semantic_groups']!=len({text_key(r['body']) for r in rs if candidate(r)}) or stat['qualified_groups']!=len({text_key(r['body']) for r in rs if scope_match(r,a['scope'])}):raise ValueError('issue eligibility mismatch')
        if stat['post_count']!=len(set(stat.get('post_ids',[]))):raise ValueError('post context count mismatch')
    evidence={e['id']:e for e in report['evidence']}
    for iid,profile in a.get('issue_profiles',{}).items():
        if iid not in issue_ids:raise ValueError('unknown issue profile')
        for f in profile.get('facts',[]):
            if f.get('evidence_id') not in evidence or not f.get('anchor') or f['anchor'] not in evidence[f['evidence_id']]['body']:raise ValueError('profile fact is not an exact source quote')
    stance_count=0
    stances=a.get('issue_stances')
    if stances is not None:
        if not isinstance(stances,dict) or set(stances)!=issue_ids:raise ValueError('stance review must cover each issue')
        stats={s['issue_id']:s for s in a.get('issue_stats',[])}
        for iid,annotations in stances.items():
            if not isinstance(annotations,list):raise ValueError('invalid stance annotations')
            used=[]
            for annotation in annotations:
                if not isinstance(annotation,dict):raise ValueError('invalid stance annotation')
                eid=annotation.get('evidence_id');used.append(eid)
                if eid not in ids or annotation.get('stance') not in {'positive','negative','mixed','unclear'}:raise ValueError('invalid stance or source')
                if not all(isinstance(annotation.get(k),str) and annotation[k].strip() for k in ('target','note','review_status')):raise ValueError('stance needs target, note and review status')
                anchors=annotation.get('anchors',[])
                if not isinstance(anchors,list):raise ValueError('invalid stance anchors')
                directions=set()
                for anchor in anchors:
                    if not isinstance(anchor,dict) or anchor.get('direction') not in {'positive','negative','unclear'} or not isinstance(anchor.get('text'),str) or not anchor['text'] or anchor['text'] not in ids[eid]['body']:raise ValueError('stance anchor must match original')
                    directions.add(anchor['direction'])
                stance=annotation['stance']
                required={'positive','negative'} if stance=='mixed' else {stance} if stance!='unclear' else set()
                if not required<=directions:raise ValueError('stance lacks directional anchors')
            if len(used)!=len(set(used)) or set(used)!=set(stats.get(iid,{}).get('record_ids',[])):raise ValueError('stance IDs must match issue mapping')
            stance_count+=len(annotations)
    from frameworks import validate_frameworks
    framework_checks=validate_frameworks(a)
    return {'records_reconciled':len(rows),'text_groups_reconciled':m['text_groups'],'issue_counts_reconciled':len(a.get('issue_stats',[])), 'stance_records_checked':stance_count,'frameworks':framework_checks}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('corpus',type=Path)
    p.add_argument('--issue-map',type=Path,required=True);p.add_argument('--scope',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    corpus=[json.loads(x) for x in a.corpus.read_text(encoding='utf-8').splitlines() if x.strip()]
    scope=json.loads(a.scope.read_text(encoding='utf-8'));scope=scope.get('scope',scope)
    result=derive(corpus,json.loads(a.issue_map.read_text(encoding='utf-8')),scope)
    result['source_fingerprints']=[dict(file=f.name,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in (a.corpus,a.issue_map,a.scope)]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['metrics'],ensure_ascii=False))

if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
