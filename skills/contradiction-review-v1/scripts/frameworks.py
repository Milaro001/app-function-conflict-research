"""Validate optional presentation and evidence-to-framework mappings, not measured quality."""
import base64
from urllib.parse import urlsplit

DIMENSIONS={'tangibles','reliability','responsiveness','assurance','empathy'}
def web_url(value):
    if not isinstance(value,str):raise ValueError('framework source must be a web URL')
    p=urlsplit(value)
    if p.scheme not in {'https','http'} or not p.hostname or p.username or p.password:raise ValueError('invalid framework source URL')

def validate_hero_image(photo, required=False):
    if not photo:
        if required:raise ValueError('a sourced real product interface image is required for the cover')
        return False
    if not isinstance(photo,dict):raise ValueError('invalid hero image')
    if photo.get('kind') not in {'app_screenshot','website_screenshot','official_image','user_screenshot','report_screenshot'}:
        raise ValueError('hero image must show a real product interface from direct capture, official material, a user post or a report; no generated illustration')
    web_url(photo.get('source_url'))
    for k in ('alt','caption','author','usage_note'):
        if not isinstance(photo.get(k),str) or not photo[k].strip():raise ValueError('hero image needs '+k)
    from datetime import datetime
    try:
        captured=datetime.fromisoformat(photo['captured_at'].replace('Z','+00:00'))
        if captured.tzinfo is None:raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError):raise ValueError('hero image needs timezone-aware captured_at')
    if photo.get('license_url'):web_url(photo['license_url'])
    data=photo.get('data','')
    formats={'data:image/jpeg;base64,':b'\xff\xd8\xff','data:image/png;base64,':b'\x89PNG\r\n\x1a\n'}
    prefix=next((x for x in formats if isinstance(data,str) and data.startswith(x)),None)
    if not prefix:raise ValueError('hero image must embed JPEG or PNG data')
    try:raw=base64.b64decode(data[len(prefix):],validate=True)
    except Exception as exc:raise ValueError('invalid embedded hero image') from exc
    if len(raw)>2_000_000 or not raw.startswith(formats[prefix]):raise ValueError('invalid or oversized hero image')
    import hashlib
    if photo.get('sha256')!=hashlib.sha256(raw).hexdigest():raise ValueError('hero screenshot hash mismatch')
    return True


def validate_hero_gallery(hero):
    gallery=hero.get('images',[])
    if not isinstance(gallery,list) or len(gallery)>4:raise ValueError('hero gallery must contain at most four real product images')
    for image in gallery:validate_hero_image(image,required=True)
    return gallery


def validate_frameworks(analytics):
    presentation=analytics.get('presentation',{})
    if not isinstance(presentation,dict):raise ValueError('invalid presentation')
    if presentation.get('product_source'):web_url(presentation['product_source'])
    hero=presentation.get('hero',{})
    if not isinstance(hero,dict):raise ValueError('invalid hero')
    photo=hero.get('image')
    validate_hero_image(photo)
    gallery=validate_hero_gallery(hero)
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
    return {'service_records_checked':total,'hero_embedded':bool(photo),'hero_gallery_images_checked':len(gallery)}
