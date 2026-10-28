"""Validate optional presentation and evidence-to-framework mappings, not measured quality."""
import base64
from urllib.parse import urlsplit

DIMENSIONS={'tangibles','reliability','responsiveness','assurance','empathy'}
def web_url(value):
    if not isinstance(value,str):raise ValueError('framework source must be a web URL')
    p=urlsplit(value)
    if p.scheme not in {'https','http'} or not p.hostname or p.username or p.password:raise ValueError('invalid framework source URL')

def validate_frameworks(analytics):
    presentation=analytics.get('presentation',{})
    if not isinstance(presentation,dict):raise ValueError('invalid presentation')
    if presentation.get('product_source'):web_url(presentation['product_source'])
    hero=presentation.get('hero',{})
    if not isinstance(hero,dict):raise ValueError('invalid hero')
    photo=hero.get('image')
    if photo:
        if not isinstance(photo,dict):raise ValueError('invalid hero photo')
        web_url(photo.get('source_url'));web_url(photo.get('license_url'))
        if any(not isinstance(photo.get(k),str) or not photo[k].strip() for k in ('alt','caption','author','license')):raise ValueError('hero photo needs attribution')
        data=photo.get('data','')
        if not isinstance(data,str) or not data.startswith('data:image/jpeg;base64,'):raise ValueError('hero must embed JPEG data')
        try:raw=base64.b64decode(data.split(',',1)[1],validate=True)
        except Exception as exc:raise ValueError('invalid embedded hero photo') from exc
        if len(raw)>2_000_000 or not raw.startswith(b'\xff\xd8\xff'):raise ValueError('invalid or oversized hero JPEG')
    frameworks=analytics.get('frameworks',{})
    if not isinstance(frameworks,dict):raise ValueError('invalid frameworks')
    rice=frameworks.get('rice',{})
    if rice:
        if not isinstance(rice,dict):raise ValueError('invalid RICE settings')
        web_url(rice.get('source_url'))
        if any(k in rice for k in ('scores','ranking','measured_reach')):raise ValueError('RICE draft must not embed invented scores')
    quality=frameworks.get('service_quality');total=0
    if quality is not None:
        if not isinstance(quality,dict) or quality.get('measurement_status')!='not_conducted':raise ValueError('content mapping is not a SERVQUAL measurement')
        web_url(quality.get('source_url'))
        rows={r['evidence_id']:r for r in analytics['records']}
        expected={eid for s in analytics['issue_stats'] for eid in s['record_ids'] if rows[eid].get('semantic_candidate')}
        used=[]
        if not isinstance(quality.get('annotations'),list):raise ValueError('service quality needs original-level mappings')
        for annotation in quality['annotations']:
            if not isinstance(annotation,dict):raise ValueError('invalid service mapping')
            eid=annotation.get('evidence_id');used.append(eid)
            if eid not in rows or not annotation.get('review_status'):raise ValueError('invalid service mapping source')
            dimensions=annotation.get('dimensions')
            if not isinstance(dimensions,list):raise ValueError('invalid service dimensions')
            seen=set()
            for dim in dimensions:
                if not isinstance(dim,dict) or dim.get('key') not in DIMENSIONS or dim['key'] in seen:raise ValueError('invalid or duplicate service dimension')
                seen.add(dim['key'])
                if not isinstance(dim.get('anchor'),str) or not dim['anchor'] or dim['anchor'] not in rows[eid]['body'] or not dim.get('reason'):raise ValueError('service dimension needs exact source and reason')
            if not dimensions and not annotation.get('unmapped_reason'):raise ValueError('unmapped service feedback needs a reason')
            total+=1
        if len(used)!=len(set(used)) or set(used)!=expected:raise ValueError('service mappings must cover all mapped candidates')
        if any(k in quality for k in ('scores','ratings','gap_scores')):raise ValueError('no measured service score is available')
    return {'service_records_checked':total,'hero_embedded':bool(photo)}
