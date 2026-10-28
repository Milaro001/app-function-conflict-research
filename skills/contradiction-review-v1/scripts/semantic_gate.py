"""Evidence-routing validator, NOT a semantic classifier or truth detector.
Input labels must come from the semantic model or a human. No network access.
"""
import sys
import json
import argparse

KINDS={'problem','preference','attitude','event_position','other'}
BASES={'self_report','direct_preference','hearsay','explicit_nonuse','unknown'}
EVENTS={'none','context_only','explicit_rating_mobilization','explicit_event_rating','unknown'}

def route(record):
    if not isinstance(record,dict):raise ValueError('record must be an object')
    text=record.get('text')
    if not isinstance(text,str):raise ValueError('text must be a string')
    out=[]
    claims=record.get('claims')
    if not isinstance(claims,list):raise ValueError('claims must be an array')
    claim_ids=set()
    for claim in claims:
        if not isinstance(claim,dict):raise ValueError('claim must be an object')
        claim_id=claim.get('claim_id')
        if not isinstance(claim_id,str) or not claim_id or claim_id in claim_ids:raise ValueError('claim_id must be a unique nonempty string')
        claim_ids.add(claim_id)
        if claim.get('kind') not in KINDS or claim.get('basis') not in BASES:raise ValueError('invalid kind/basis')
        if claim.get('event_signal') not in EVENTS:raise ValueError('invalid event signal')
        if claim.get('emotion') not in {'low','high','unknown'}:raise ValueError('invalid emotion')
        if claim.get('context_dependency') not in {'none','unresolved'}:raise ValueError('invalid context dependency')
        anchor=claim.get('anchor')
        if not isinstance(anchor,str) or not anchor or anchor not in text:raise ValueError('claim anchor is not in source text')
        feature_anchor=claim.get('feature_anchor')
        if feature_anchor is not None and not isinstance(feature_anchor,str):raise ValueError('feature anchor must be text or null')
        if feature_anchor and feature_anchor not in text:raise ValueError('feature anchor is not in source text')
        if claim.get('feature') is not None and not isinstance(claim['feature'],str):raise ValueError('feature must be text or null')
        event=claim['event_signal']
        if event.startswith('explicit_') and (not isinstance(claim.get('event_anchor'),str) or not claim['event_anchor'] or claim['event_anchor'] not in text):raise ValueError('explicit event signal needs an exact source anchor')
        if claim.get('experience_truth','unverified')!='unverified':raise ValueError('this prototype has no external truth verification input')
        if claim.get('motive_judgment','not_inferred')!='not_inferred':raise ValueError('hidden motive judgment is not supported')
        functional=claim['kind'] in {'problem','preference'}
        explicit_feature=bool(claim.get('feature') and feature_anchor and feature_anchor in anchor)
        unresolved=claim['context_dependency']=='unresolved'
        problem_candidate=functional and claim['kind']=='problem' and explicit_feature and claim['basis']=='self_report' and not unresolved
        preference_candidate=functional and claim['kind']=='preference' and explicit_feature and claim['basis'] in {'direct_preference','self_report'} and not unresolved
        if unresolved:pool='needs_context'
        elif problem_candidate:pool='functional_problem_candidate'
        elif preference_candidate:pool='functional_preference_candidate'
        elif functional and claim['basis'] in {'hearsay','explicit_nonuse'}:pool='secondary_or_nonexperience'
        elif functional:pool='needs_review'
        elif claim['kind']=='event_position':pool='event_context'
        elif claim['kind']=='attitude':pool='attitude_only'
        else:pool='other'
        out.append(dict(claim_id=claim.get('claim_id'),pool=pool,problem_count_candidate=bool(problem_candidate),preference_count_candidate=bool(preference_candidate),event_signal=event,emotion=claim['emotion'],experience_truth='unverified',motive_judgment='not_inferred',conflict_status='not_assessed'))
    return dict(record_id=record.get('record_id'),claims=out,limits='Routing of supplied annotations only; deduplication, source breadth, truth verification and conflict pairing remain separate.')

def main():
    p=argparse.ArgumentParser();p.add_argument('input',help='UTF-8 JSON record or array');a=p.parse_args()
    with open(a.input,encoding='utf-8') as f:data=json.load(f)
    result=[route(x) for x in data] if isinstance(data,list) else route(data)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
