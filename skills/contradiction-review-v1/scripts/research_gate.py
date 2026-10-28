#!/usr/bin/env python3
"""Validate supplied semantic labels and scope; never infer labels from keywords.

Input is {scope, records}. Records carry original text, provenance, and model or
human annotations. Passing this quantity check proves neither experience truth,
true conflict, current-version applicability, nor permission to collect more.
"""
import sys
import argparse
import json
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CODES=set('PVCUGE')
CLIENTS={'android','ios','harmonyos','windows','macos','web','unknown'}
SOURCES={'appbao','appstore','xhs','bili','wb','v2ex','appinn','douyin','zhihu','jike','douban','maimai','web'}
CONTEXTS={'none','resolved','unresolved','unknown'}
BASES={'self_report','direct_preference','hearsay','explicit_nonuse','unknown'}


def time_value(value):
    if value in (None,'','unknown'):return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError,TypeError):return None


def text_key(body):
    return ''.join(c for c in unicodedata.normalize('NFKC',body).casefold() if c.isalnum())


def evaluate(data,collection_gate=None):
    scope=data['scope'];records=data['records']
    app=scope.get('app');client=scope.get('client','android')
    start=time_value(scope.get('start'));end=time_value(scope.get('end'))
    if not isinstance(app,str) or not app.strip():raise ValueError('scope.app is required')
    if client not in CLIENTS|{'all'}:raise ValueError('invalid scope.client')
    if client=='unknown':raise ValueError('unknown is not a research target client')
    version=scope.get('version')
    if version is not None and (not isinstance(version,str) or version in ('','unknown')):raise ValueError('scope.version must name a version or be null')
    payment=scope.get('payment','all')
    if payment not in {'all','free','paid'}:raise ValueError('invalid scope.payment')
    focus=scope.get('issue_ids',[])
    if not isinstance(focus,list) or any(not isinstance(i,str) or not i for i in focus):raise ValueError('invalid scope.issue_ids')
    if not start or not end or start>end:raise ValueError('scope requires an ordered, timezone-aware start/end')
    allowed=set(scope.get('allowed_sources',['appbao','appstore','xhs','wb','zhihu','bili','douyin','v2ex','appinn','web']))
    if not allowed or not allowed<=SOURCES:raise ValueError('invalid source scope')
    target=scope.get('target_effective',1000);minimum=scope.get('issue_collection_min',100)
    if type(target) is not int or target<1 or type(minimum) is not int or minimum<1:raise ValueError('invalid quantity target')
    target_kind=scope.get('target_kind','research_feedback')
    if target_kind not in {'research_feedback','problem_request'}:raise ValueError('invalid target_kind')
    if not isinstance(records,list):raise ValueError('records must be an array')
    categories=Counter();excluded=Counter();eligible=defaultdict(list);pending=defaultdict(list);identity={};observed=set()
    PENDING={'client_unknown','version_unknown','payment_unknown'}
    for record in records:
        rid=record.get('evidence_id');body=record.get('body');code=record.get('code')
        platform=record.get('source_platform')
        if not isinstance(rid,str) or not rid or not isinstance(body,str):raise ValueError('each record needs evidence_id and body')
        if code not in CODES:raise ValueError('invalid screening code; no motive/true-user labels supported')
        if platform not in SOURCES:raise ValueError('invalid source_platform')
        ident=(platform,rid)
        if ident in observed:
            if identity[ident]!=(body,code):raise ValueError('conflicting duplicate evidence identity')
            excluded['duplicate_id']+=1;continue
        observed.add(ident);identity[ident]=(body,code);categories[code]+=1
        if record.get('client','unknown') not in CLIENTS:raise ValueError('invalid record.client')
        if record.get('context_dependency','unknown') not in CONTEXTS:raise ValueError('invalid context_dependency')
        if record.get('basis','unknown') not in BASES:raise ValueError('invalid basis')
        if record.get('review_status','pending') not in {'pending','model_first_pass','human_reviewed'}:raise ValueError('invalid review_status')
        if record.get('human_review_status','unreviewed') not in {'unreviewed','approved','rejected'}:raise ValueError('invalid human_review_status')
        if record.get('payment','unknown') not in {'free','paid','unknown'}:raise ValueError('invalid record.payment')
        issue_ids=record.get('issue_ids',[])
        if not isinstance(issue_ids,list) or any(not isinstance(i,str) or not i for i in issue_ids):raise ValueError('invalid issue_ids')
        anchor=record.get('anchor')
        if code in {'P','V'} and (not isinstance(anchor,str) or not anchor or anchor not in body):
            raise ValueError('retained semantic annotation needs an exact source anchor')
        reason=None
        if code not in {'P','V'}:reason='not_functional_research_feedback'
        elif not text_key(body):reason='empty_or_symbol_only'
        elif record.get('human_review_status')=='rejected':reason='human_rejected'
        elif record.get('review_status','pending')=='pending':reason='semantic_review_pending'
        elif not record.get('source_url') and not record.get('source_file'):reason='missing_provenance'
        elif platform not in allowed:reason='source_outside_scope'
        elif record.get('app') in (None,'','unknown'):reason='app_unknown'
        elif record['app']!=app:reason='different_app'
        elif record.get('basis','unknown') in {'hearsay','explicit_nonuse','unknown'}:reason='experience_or_preference_basis_unresolved'
        elif record.get('context_dependency','unknown') in {'unresolved','unknown'}:reason='context_pending'
        elif time_value(record.get('published_at')) is None:reason='publication_time_unknown'
        elif not start<=time_value(record.get('published_at'))<=end:reason='outside_time_window'
        elif client!='all' and record.get('client','unknown')=='unknown':reason='client_unknown'
        elif client!='all' and record['client']!=client:reason='different_client'
        elif version is not None and record.get('version') in (None,'','unknown'):reason='version_unknown'
        elif version is not None and record['version']!=version:reason='different_version'
        elif payment!='all' and record.get('payment','unknown')=='unknown':reason='payment_unknown'
        elif payment!='all' and record['payment']!=payment:reason='different_payment_condition'
        elif focus and not set(focus).intersection(issue_ids):reason='issue_outside_scope'
        if reason in PENDING:
            # Unknown is not a mismatch: hold it in a separate tier unless a known
            # condition already contradicts the scope.
            known_mismatch=((client!='all' and record.get('client','unknown') not in ('unknown',client))
                or (version is not None and record.get('version') not in (None,'','unknown',version))
                or (payment!='all' and record.get('payment','unknown') not in ('unknown',payment))
                or (focus and not set(focus).intersection(issue_ids)))
            if not known_mismatch:pending[text_key(body)].append(record)
        if reason:excluded[reason]+=1;continue
        eligible[text_key(body)].append(record)
    for group in eligible.values():
        if len({r['code'] for r in group})>1:raise ValueError('same text has inconsistent P/V labels; adjudicate first')
    counts=Counter(group[0]['code'] for group in eligible.values())
    human=sum(any(r.get('human_review_status')=='approved' for r in group) for group in eligible.values())
    issues=defaultdict(set)
    for key,group in eligible.items():
        for record in group:
            issue_ids=record.get('issue_ids',[])
            if not isinstance(issue_ids,list) or any(not isinstance(i,str) or not i for i in issue_ids):raise ValueError('invalid issue_ids')
            for issue in issue_ids:issues[issue].add(key)
    selected=counts['P'] if target_kind=='problem_request' else sum(counts.values())
    pending_groups={k:g for k,g in pending.items() if k not in eligible}
    pending_counts=Counter(g[0]['code'] for g in pending_groups.values())
    pending_selected=pending_counts['P'] if target_kind=='problem_request' else sum(pending_counts.values())
    technical=None if collection_gate is None else collection_gate.get('can_expand')
    if technical is not None and type(technical) is not bool:raise ValueError('invalid collection technical gate')
    return dict(scope=scope,input_rows=len(records),unique_evidence_ids=len(observed),categories=dict(categories),
        effective_text_groups=sum(counts.values()),problem_request_groups=counts['P'],value_preference_groups=counts['V'],
        excluded_records=dict(excluded),duplicate_text_observations=sum(len(g)-1 for g in eligible.values()),
        target_kind=target_kind,target_effective=target,target_count=selected,data_quantity_met=selected>=target,
        missing_to_target=max(0,target-selected),human_approved_groups=human,
        tiers=dict(strict_qualified=selected,condition_pending=pending_selected,combined=selected+pending_selected,
            pending_reasons=dict(Counter(r for r in excluded if r in PENDING)),
            note='condition_pending passed every other check; only client/version/payment is unstated. It is never counted as strict.'),
        missing_to_target_including_pending=max(0,target-selected-pending_selected),
        human_gate_status='not_assessed',conflict_status='not_assessed',current_version_applicability='not_assessed',
        collection_technical_gate=technical,
        issues={i:dict(related_feedback_groups=len(keys),collection_threshold_met=len(keys)>=minimum,
            conflict_status='not_assessed') for i,keys in sorted(issues.items())},
        effective_evidence_groups=[sorted(r['evidence_id'] for r in group) for group in eligible.values()],
        limits=['Validation/counting of supplied annotations only; not semantic inference or truth verification.',
            'Text groups are not unique people or independent experiences.',
            'A quantity pass never grants collection permission or passes G2/G3.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--collection-gate',type=Path)
    args=p.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'))
    gate=json.loads(args.collection_gate.read_text(encoding='utf-8')) if args.collection_gate else None
    result=evaluate(data,gate)
    encoded=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(encoded,encoding='utf-8')
    else:print(encoded,end='')


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
