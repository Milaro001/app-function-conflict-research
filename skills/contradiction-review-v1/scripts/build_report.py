#!/usr/bin/env python3
"""Build an offline evidence-linked report from supplied research annotations.

This renderer validates structure and quotations; it does not classify feedback,
prove conflicts, approve a Human Gate, or start collection.
"""
import sys
import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SKILL=Path(__file__).resolve().parents[1]
RELATIONS={'conflict_candidate','compatible_preferences','condition_difference','one_sided_issue','insufficient_context'}
ROOT_FIELDS={'schema_version','report_id','app','scope','counts','sources','issues','evidence','limitations','generated_at','handoff','analytics'}


STAGE_KEYS={'discover','onboard','track','notify','pickup','send','pay','service','after_sale','account','other'}
LEVELS={'高','中','低','待核'}
METHODS={'数据核查','可用性测试','用户访谈','A/B测试','工单核查','问卷'}


def text(value,limit,name):
    if not isinstance(value,str) or not value.strip():raise ValueError(name+' must be non-empty text')
    if len(value)>limit:raise ValueError(f'{name} exceeds {limit} characters (writing-style.md): {value[:20]}…')


def cited(values,ids,name):
    if not isinstance(values,list) or any(v not in ids for v in values):raise ValueError(name+' must list existing evidence IDs')


def validate_insight(issue,ids):
    """Optional deeper-analysis block; see references/analysis-workflow.md (8 steps)."""
    x=issue.get('insight')
    if x is None:return 0
    if not isinstance(x,dict):raise ValueError('insight must be an object')
    known={'headline','key_points','confidence','segments','journey','root_cause','benchmarks','impact','metrics','next_steps'}
    if set(x)-known:raise ValueError('unknown insight fields: '+', '.join(sorted(set(x)-known)))
    text(x.get('headline'),30,'insight.headline')
    points=x.get('key_points',[])
    if not isinstance(points,list) or len(points)>3:raise ValueError('insight.key_points: at most 3')
    for v in points:text(v,40,'key point')
    conf=x.get('confidence')
    if conf is not None:
        if conf.get('level') not in {'高','中','低'}:raise ValueError('confidence.level must be 高/中/低')
        text(conf.get('reason'),40,'confidence.reason')
    for seg in x.get('segments',[]):
        for k,n in (('name',16),('situation',40),('need',40)):text(seg.get(k),n,'segment.'+k)
        cited(seg.get('evidence_ids',[]),ids,'segment.evidence_ids')
    journey=x.get('journey')
    if journey is not None:
        stages=journey.get('stages')
        if not isinstance(stages,list) or not 2<=len(stages)<=7:raise ValueError('journey needs 2..7 stages')
        keys=[]
        for st in stages:
            if st.get('key') not in STAGE_KEYS:raise ValueError('invalid journey stage key')
            keys.append(st['key'])
            text(st.get('label'),8,'stage.label')
            for k in ('user_action','touchpoint','backstage'):text(st.get(k),30,'stage.'+k)
            f=st.get('feeling')
            if f is not None and (type(f) is not int or not -2<=f<=2):raise ValueError('stage.feeling must be -2..2 or null')
            cited(st.get('evidence_ids',[]),ids,'stage.evidence_ids')
            # A feeling is read from users' words; with no quote it stays unknown.
            if f is not None and not st.get('evidence_ids'):raise ValueError('stage.feeling needs evidence_ids')
            basis=st.get('feeling_basis')
            if basis is not None:
                if not isinstance(basis,dict):raise ValueError('feeling_basis must be an object')
                eid=basis.get('evidence_id');anchor=basis.get('anchor')
                if eid not in st.get('evidence_ids',[]) or not isinstance(anchor,str) or not anchor or anchor not in ids[eid]['body']:raise ValueError('feeling_basis must quote a stage source')
                text(basis.get('interpretation'),150,'feeling_basis.interpretation')
        if journey.get('breakpoint') not in keys:raise ValueError('journey.breakpoint must be one of its stages')
    for c in x.get('root_cause',[]):
        if c.get('level') not in {'symptom','direct','underlying'} or c.get('status') not in {'observed','hypothesis'}:raise ValueError('invalid root_cause level/status')
        text(c.get('statement'),40,'root_cause.statement');cited(c.get('evidence_ids',[]),ids,'root_cause.evidence_ids')
        if c['status']=='observed' and not c.get('evidence_ids'):raise ValueError('observed root cause needs evidence')
    for b in x.get('benchmarks',[]):
        if b.get('status') not in {'to_check','reported_by_user'}:raise ValueError('benchmark.status must be to_check or reported_by_user')
        text(b.get('name'),16,'benchmark.name');text(b.get('question'),50,'benchmark.question')
        if b['status']=='reported_by_user':cited(b.get('evidence_ids') or [None],ids,'benchmark.evidence_ids')
    imp=x.get('impact')
    if imp is not None:
        if imp.get('task') not in {'阻断','拖慢','困扰'} or imp.get('level') not in LEVELS:raise ValueError('invalid impact')
        text(imp.get('scope_note'),50,'impact.scope_note')
    for m in x.get('metrics',[]):
        text(m.get('name'),14,'metric.name');text(m.get('definition'),50,'metric.definition');text(m.get('pass_rule'),40,'metric.pass_rule')
    for n in x.get('next_steps',[]):
        if n.get('method') not in METHODS:raise ValueError('next_step.method must be one of '+'/'.join(sorted(METHODS)))
        for k,lim in (('owner',20),('action',50),('sample',24),('duration',10),('pass_rule',50),('decides',30)):text(n.get(k),lim,'next_step.'+k)
    for o in issue.get('options',[]):
        for k in ('effort','impact_level'):
            if k in o and o[k] not in LEVELS:raise ValueError('option.'+k+' must be 高/中/低/待核')
        if o.get('estimate_basis') is not None:text(o['estimate_basis'],250,'option.estimate_basis')
        if o.get('estimate_assumptions') is not None:text(o['estimate_assumptions'],180,'option.estimate_assumptions')
        w=o.get('wireframe')
        if w is not None:
            if not isinstance(w,dict) or not all(isinstance(w.get(k),list) and 1<=len(w[k])<=6 for k in ('before','after')):raise ValueError('wireframe needs before/after lists (1..6)')
            for v in w['before']+w['after']:text(v,26,'wireframe element')
    return 1


def validate(data):
    if not isinstance(data,dict) or set(data)-ROOT_FIELDS:raise ValueError('invalid report fields')
    if data.get('schema_version')!=1:raise ValueError('schema_version must be 1')
    if not isinstance(data.get('app'),str) or not data['app'].strip():raise ValueError('app is required')
    for key in ('issues','evidence','sources','limitations'):
        if not isinstance(data.get(key),list):raise ValueError(key+' must be an array')
    if any(not isinstance(v,str) for v in data['limitations']):raise ValueError('limitations must contain text')
    handoff=data.get('handoff')
    if handoff is not None:
        if not isinstance(handoff,dict) or set(handoff)-{'conversation_url','local_bridge'}:raise ValueError('invalid handoff settings')
        if not re.fullmatch(r'codex://threads/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',handoff.get('conversation_url','')):
            raise ValueError('handoff needs a verified existing conversation URL')
        if type(handoff.get('local_bridge',False)) is not bool:raise ValueError('local_bridge must be boolean')
    for source in data['sources']:
        for post in source.get('recent_posts',[]):
            parsed=urlparse(post.get('source_url',''))
            if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('recent post needs an HTTP(S) source URL without credentials')
    scope=data.get('scope');counts=data.get('counts')
    if not isinstance(scope,dict) or not isinstance(counts,dict):raise ValueError('scope and counts are required')
    values=[]
    for key in ('raw_comments','screened_feedback','qualified_in_scope'):
        v=counts.get(key)
        if v is not None and (type(v) is not int or v<0):raise ValueError('invalid count '+key)
        values.append(v)
    known=[v for v in values if v is not None]
    if known!=sorted(known,reverse=True):raise ValueError('screened/scope counts cannot exceed their input')
    ids={}
    for item in data['evidence']:
        if not isinstance(item,dict):raise ValueError('invalid evidence')
        eid=item.get('id');body=item.get('body')
        if not isinstance(eid,str) or not eid or eid in ids:raise ValueError('evidence ID must be unique')
        if not isinstance(body,str) or not body.strip():raise ValueError('evidence body is required')
        url=item.get('source_url')
        if url:
            parsed=urlparse(url)
            if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('source_url must be an HTTP(S) page without credentials')
        elif not item.get('source_file'):raise ValueError('evidence needs a source URL or file')
        ids[eid]=item
    seen=set();anchors=0;insights=0
    for issue in data['issues']:
        if not isinstance(issue,dict):raise ValueError('invalid issue')
        iid=issue.get('id')
        if not isinstance(iid,str) or not iid or iid in seen:raise ValueError('issue ID must be unique')
        seen.add(iid)
        if not issue.get('title') or not issue.get('decision_object'):raise ValueError('issue needs title and decision_object')
        if issue.get('relation') not in RELATIONS:raise ValueError('invalid relation')
        citations=issue.get('anchors')
        if not isinstance(citations,list) or not citations:raise ValueError('issue needs evidence anchors')
        for citation in citations:
            eid=citation.get('evidence_id');anchor=citation.get('anchor')
            if eid not in ids or not isinstance(anchor,str) or not anchor or anchor not in ids[eid]['body']:
                raise ValueError('quotation is not in the referenced original evidence')
            anchors+=1
        for key in ('conditions','hypotheses','options','ranking_reasons'):
            if not isinstance(issue.get(key,[]),list):raise ValueError('invalid issue '+key)
        for hypothesis in issue.get('hypotheses',[]):
            if not hypothesis.get('statement') or any(e not in ids for e in hypothesis.get('support_ids',[])):
                raise ValueError('hypothesis needs a statement and valid evidence IDs')
        for option in issue.get('options',[]):
            if any(not isinstance(option.get(k),str) or not option[k] for k in ('action','conditions','tradeoff','validation_task')):
                raise ValueError('option needs action, conditions, tradeoff and validation_task')
        related=issue.get('related_feedback')
        if related is not None and (type(related) is not int or related<0):raise ValueError('invalid related feedback count')
        if issue.get('main_collection_eligible') and (related is None or related<100 or issue['relation']=='insufficient_context'):
            raise ValueError('insufficient evidence cannot enter the main collection')
        insights+=validate_insight(issue,ids)
    stages=[s for i in data['issues'] for s in (i.get('insight',{}).get('journey') or {}).get('stages',[])]
    options=[o for i in data['issues'] for o in i.get('options',[])]
    result={'issues':len(seen),'evidence':len(ids),'exact_anchors_checked':anchors,'issues_with_insight':insights}
    if insights:
        result['presentation_inputs']={'journey_steps':len(stages),'feeling_points_with_sources':sum(s.get('feeling') is not None and bool(s.get('evidence_ids')) for s in stages),
            'feeling_points_with_explicit_basis':sum(bool(s.get('feeling_basis')) for s in stages),
            'options_with_estimate_basis':sum(bool(o.get('estimate_basis')) for o in options),
            'options_with_wireframe':sum(bool(o.get('wireframe')) for o in options)}
        gaps=[]
        for issue in data['issues']:
            journey=(issue.get('insight',{}).get('journey') or {}).get('stages',[])
            if journey and not any(s.get('feeling') is not None for s in journey):gaps.append({'issue_id':issue['id'],'field':'journey.feeling','note':'全部阶段感受未知；保留空点并说明原因，检查是否遗漏了可解读的原话。'})
            for index,option in enumerate(issue.get('options',[])):
                missing=[k for k in ('effort','impact_level','estimate_basis','wireframe') if not option.get(k) or option.get(k)=='待核']
                if missing:gaps.append({'issue_id':issue['id'],'option_index':index,'missing':missing,'note':'补齐有依据的研究估计和改前改后示意；关键前提确实未知时明确保留原因。'})
        if gaps:result['presentation_gaps']=gaps
    if data.get('analytics') is not None:
        from quantification import validate_analytics
        result['quantification']=validate_analytics(data['analytics'],data)
    return result


def render(data):
    checks=validate(data)
    # UI transport settings do not change research evidence or discard existing
    # review choices. Changing the actual research still changes this namespace.
    # Derived views of the unchanged source annotations are tracked separately;
    # adding charts does not discard choices on the original issue interpretation.
    encoded=json.dumps({k:v for k,v in data.items() if k not in ('handoff','analytics')},ensure_ascii=False,sort_keys=True)
    bundle_id=hashlib.sha256(encoded.encode()).hexdigest()[:20]
    payload=dict(data,bundle_id=bundle_id)
    # Do not allow quoted source text to terminate the inert JSON script block.
    safe=json.dumps(payload,ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template=(SKILL/'assets/report-template.html').read_text(encoding='utf-8')
    if template.count('__REPORT_JSON__')!=1:raise ValueError('report template placeholder mismatch')
    analytics=(SKILL/'assets/report-analytics.js').read_text(encoding='utf-8')+'\n'+(SKILL/'assets/report-diagrams.js').read_text(encoding='utf-8')+'\n'+(SKILL/'assets/report-insight.js').read_text(encoding='utf-8')+'\n'+(SKILL/'assets/report-frameworks.js').read_text(encoding='utf-8')+'\n'+(SKILL/'assets/report-motion.js').read_text(encoding='utf-8')
    template=template.replace('__HANDOFF_SCRIPT__',(SKILL/'assets/report-handoff.js').read_text(encoding='utf-8')).replace('__ANALYTICS_SCRIPT__',analytics).replace('__REPORT_CSS__',(SKILL/'assets/report.css').read_text(encoding='utf-8'))
    return template.replace('__REPORT_JSON__',safe),checks,bundle_id


def build(data,destination):
    content,checks,bundle_id=render(data)
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    (out/'report.html').write_text(content,encoding='utf-8')
    (out/'report-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=['id','platform','body','published_at','source_url','source_file','parent_id','context_status']
    with (out/'evidence.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for item in data['evidence']:
            # Preserve exact source text in JSON; neutralize formula cells in CSV.
            row={k:item.get(k) for k in fields}
            for key,value in row.items():
                if isinstance(value,str) and value.startswith(('=','+','-','@')):row[key]="'"+value
            writer.writerow(row)
    receipt={'built_at':datetime.now(timezone.utc).isoformat(),'bundle_id':bundle_id,
        'structural_checks':checks,'human_G2':'unreviewed','human_G3':'unreviewed',
        'limits':['Structure and exact quotation validation only; semantic correctness and quantity are separate.',
                  'Local review choices are exported separately; they do not modify source evidence or grant publication approval.']}
    (out/'check-report.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    names=['report.html','report-data.json','evidence.csv','check-report.json']
    manifest={'app':data['app'],'bundle_id':bundle_id,'files':[{'name':name,'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest()} for name in names],
        'human_review_status':'unreviewed','external_requests_required':False}
    (out/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();manifest=build(json.loads(args.input.read_text(encoding='utf-8')),args.output)
    print(json.dumps({'report':str((args.output/'report.html').resolve()),'bundle_id':manifest['bundle_id'],'human_review_status':'unreviewed'},ensure_ascii=False))


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
