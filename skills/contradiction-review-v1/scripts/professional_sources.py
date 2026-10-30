#!/usr/bin/env python3
"""Discover public professional articles, fetch originals, and keep human/model selection separate.

No article quota, semantic quality classifier, login, browser profile or feedback-count uplift.
Native search that needs JS/auth stays a recorded gap with host-search queries.
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
REGISTRY=json.loads((SKILL/'references/professional-sources.json').read_text(encoding='utf-8'))
SITES={s['id']:s for s in REGISTRY['sources']}
UA='AppResearch/1.0 (public product and design research)'
STOP={'access_denied','verification_required','robots_disallowed','certificate_error'}

def now():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def readlines(path):return [json.loads(l) for l in Path(path).read_text(encoding='utf-8').split('\n') if l.strip()]
def jsonlines(path,rows):
    Path(path).write_text(''.join(json.dumps(r,ensure_ascii=False).replace('\u2028','\\u2028').replace('\u2029','\\u2029').replace('\u0085','\\u0085')+'\n' for r in rows),encoding='utf-8')
def cfg():return json.loads((SKILL/'runtime.json').read_text(encoding='utf-8'))
def app_key(app):return hashlib.sha256(app.encode()).hexdigest()[:12]
def canonical(url):
    p=urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path,'',''))
def allowed(url,site):
    p=urllib.parse.urlsplit(url);host=p.hostname or ''
    return p.scheme in ('https','http') and not p.username and not p.password and (host==site['domain'] or host.endswith('.'+site['domain']))
def article_url(url,site):return allowed(url,site) and bool(re.match(site['article_pattern'],urllib.parse.urlsplit(url).path))

class Page(HTMLParser):
    """Extract explicit article containers; never turn the entire navigation page into an article."""
    CONTAINERS={'article--content','article-content','entry-content','post-content','article_content','works-content','article-view','rich-text-content'}
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.meta={};self.title=[];self.links=[];self.images=[];self.blocks=[];self.current=None;self.anchor=None;self.ld=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='meta':self.meta[a.get('property') or a.get('name') or '']=a.get('content','')
        if tag=='img' and a.get('src'):self.images.append(a['src'])
        if tag=='a':self.anchor={'url':a.get('href',''),'text':[]}
        is_article=tag=='article' or bool(set(a.get('class','').split())&self.CONTAINERS) or a.get('itemprop')=='articleBody'
        if is_article:
            block=[];self.blocks.append(block)
        else:block=None
        frame={'tag':tag,'block':block,'skip':tag in ('script','style','nav','footer','noscript'),'ld':tag=='script' and a.get('type')=='application/ld+json'}
        if frame['ld']:frame['text']=[];self.ld.append(frame['text'])
        if tag not in self.VOID:self.stack.append(frame)
        if tag in ('br','p'):
            for f in self.stack:
                if f['block'] is not None:f['block'].append('\n')
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor:
            self.links.append(dict(url=self.anchor['url'],title=''.join(self.anchor['text']).strip()));self.anchor=None
        if tag in self.VOID:return
        ix=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i]['tag']==tag),None)
        if ix is not None:self.stack=self.stack[:ix]
    def handle_data(self,data):
        if any(f['tag']=='title' for f in self.stack):self.title.append(data)
        for f in self.stack:
            if f.get('ld'):f['text'].append(data)
        if any(f['skip'] for f in self.stack):return
        if self.anchor:self.anchor['text'].append(data)
        for f in self.stack:
            if f['block'] is not None:f['block'].append(data)
    def article(self):
        blocks=[''.join(b).strip() for b in self.blocks]
        author=self.meta.get('author') or self.meta.get('article:author') or None
        date=self.meta.get('article:published_time') or self.meta.get('datePublished') or None
        def visit(v):
            nonlocal author,date
            if isinstance(v,list):
                for x in v:visit(x)
            elif isinstance(v,dict):
                if isinstance(v.get('articleBody'),str):blocks.append(v['articleBody'])
                if v.get('@type') in ('Article','NewsArticle','BlogPosting'):
                    date=date or v.get('datePublished');a=v.get('author')
                    author=author or (a.get('name') if isinstance(a,dict) else a if isinstance(a,str) else None)
                if '@graph' in v:visit(v['@graph'])
        for block in self.ld:
            try:visit(json.loads(''.join(block)))
            except ValueError:pass
        return dict(title=self.meta.get('og:title') or ''.join(self.title).strip(),body=max(blocks,key=len,default=''),author=author,published_at_display=date,image_urls=self.images)

class FetchError(Exception):pass
class GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,site):self.site=site
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl,self.site):raise FetchError('redirect_outside_source')
        return super().redirect_request(req,fp,code,msg,headers,newurl)
class Fetcher:
    def __init__(self,site,delay=1.5,timeout=12):self.site=site;self.delay=delay;self.timeout=timeout;self.robots={};self.last=0
    def raw(self,url):
        if not allowed(url,self.site):raise FetchError('source_url_not_allowed')
        wait=self.delay-(time.monotonic()-self.last)
        if wait>0:time.sleep(wait)
        self.last=time.monotonic()
        try:
            opener=urllib.request.build_opener(GuardedRedirect(self.site))
            with opener.open(urllib.request.Request(url,headers={'User-Agent':UA}),timeout=self.timeout) as r:
                data=r.read(5_000_001)
                if len(data)>5_000_000:raise FetchError('response_too_large')
                encoding=r.headers.get_content_charset() or 'utf-8'
                return data.decode(encoding,'replace'),r.geturl()
        except urllib.error.HTTPError as e:raise FetchError('access_denied' if e.code in (401,403,429) else 'http_'+str(e.code)) from e
        except urllib.error.URLError as e:
            raise FetchError('certificate_error' if 'CERTIFICATE_VERIFY_FAILED' in str(e) else 'network_error') from e
        except (TimeoutError,OSError) as e:raise FetchError('network_error') from e
    def get(self,url):
        p=urllib.parse.urlsplit(url);origin=p.scheme+'://'+p.netloc
        if origin not in self.robots:
            try:
                body,_=self.raw(origin+'/robots.txt');robot=urllib.robotparser.RobotFileParser();robot.parse(body.splitlines());self.robots[origin]=robot
            except FetchError as e:
                if str(e) in STOP:raise
                if str(e) not in ('http_404','http_410'):raise FetchError('robots_unavailable') from e
                self.robots[origin]=None
        robot=self.robots[origin]
        if robot and not robot.can_fetch(UA,url):raise FetchError('robots_disallowed')
        text,final=self.raw(url)
        # A new host/scheme must have its own robots check before fetching article bodies.
        if final!=url and urllib.parse.urlsplit(final).netloc!=p.netloc:
            fp=urllib.parse.urlsplit(final);new_origin=fp.scheme+'://'+fp.netloc
            if new_origin not in self.robots:
                try:
                    body,_=self.raw(new_origin+'/robots.txt');r=urllib.robotparser.RobotFileParser();r.parse(body.splitlines());self.robots[new_origin]=r
                except FetchError as e:
                    if str(e) not in ('http_404','http_410'):raise
                    self.robots[new_origin]=None
            if self.robots[new_origin] and not self.robots[new_origin].can_fetch(UA,final):raise FetchError('robots_disallowed')
        parsed=Page();parsed.feed(text)
        if re.search(r'人机验证|访问验证|安全验证|captcha|访问过于频繁',''.join(parsed.title),re.I):raise FetchError('verification_required')
        return text,final

def make_plan(app,features=(),competitors=(),sites=None):
    terms=list(dict.fromkeys([app,*[app+' '+f for f in features],app+' 产品分析',app+' 交互 改版']))
    return dict(app=app,created_at=now(),article_target=None,minimum_per_site=None,counts_as_user_feedback=False,
        selection='先目标产品和议题，再相同任务/竞品；只保留有依据、有分析过程且能说明适用边界的文章。数量不作为完成标准。',
        sites=[dict(SITES[s],queries=[dict(query=q,url=SITES[s]['search_url'].format(query=urllib.parse.quote(q))) for q in terms],
            host_search_queries=[f'site:{SITES[s]["domain"]} "{app}" 产品分析 交互',*[f'site:{SITES[s]["domain"]} "{app}" "{f}"' for f in features]],
            secondary_queries=[f'site:{SITES[s]["domain"]} "{comp}" '+(' '.join(features) or '产品分析') for comp in competitors]) for s in (sites or SITES)])

def discover(html,base,site):
    parser=Page();parser.feed(html);found={}
    for link in parser.links:
        url=urllib.parse.urljoin(base,link['url'])
        if article_url(url,site):found.setdefault(canonical(url),dict(url=canonical(url),title=link['title'],site_id=site['id']))
    return list(found.values())

def collect_site(spec,app,folder,query_budget,candidate_limit,imported=()):
    site=SITES[spec['id']];fetcher=Fetcher(site);audit=[];candidates={};records=[];status='search_finished'
    for entry in spec['queries'][:query_budget]:
        try:
            html,final=fetcher.get(entry['url']);raw=folder/(site['id']+'-search-'+str(len(audit))+'.html');raw.write_text(html,encoding='utf-8')
            found=discover(html,final,site)
            audit.append(dict(url=entry['url'],status='read',candidate_links=len(found),source_file=str(raw),sha256=hashlib.sha256(raw.read_bytes()).hexdigest()))
            candidates.update({r['url']:r for r in found})
            if not found:status='needs_host_search'
        except FetchError as e:
            status=str(e);audit.append(dict(url=entry['url'],status=status))
            # Stop a restricted source. No identity switching, HTTP downgrade or retry.
            if status in STOP:break
            status='needs_host_search';break
    for r in imported:
        if r.get('site_id')==site['id'] and article_url(r.get('url',''),site):candidates.setdefault(canonical(r['url']),dict(r,url=canonical(r['url'])))
    # Search pages may contain creator agreements and footer recommendations.
    # The initial native pass fetches only explicit product matches; host-selected
    # candidates may cover the same task/competitor, but remain quality-pending.
    imported_urls={canonical(r['url']) for r in imported if r.get('site_id')==site['id'] and article_url(r.get('url',''),site)}
    ordered=[r for r in candidates.values() if (app in r.get('title','') or r['url'] in imported_urls)
             and not re.search(r'创作者协议|用户协议|隐私政策|服务条款|注册协议',r.get('title',''))]
    ordered.sort(key=lambda r:(app not in r.get('title',''),r['url']))
    if not ordered and status=='search_finished':status='needs_host_search'
    if status not in STOP:
        for item in ordered[:candidate_limit]:
            try:
                html,final=fetcher.get(item['url']);page=Page();page.feed(html);article=page.article()
                if not article_url(final,site):raise FetchError('not_article_url')
                rid='professional-'+hashlib.sha256(canonical(final).encode()).hexdigest()[:20]
                raw=folder/(rid+'.html');raw.write_text(html,encoding='utf-8')
                (folder/(rid+'.txt')).write_text(article['body'],encoding='utf-8')
                if len(article['body'].strip())<80:
                    audit.append(dict(url=final,status='body_not_extracted',source_file=str(raw)));continue
                if re.search(r'创作者协议|用户协议|隐私政策|服务条款|注册协议',article['title']):
                    audit.append(dict(url=final,status='navigation_not_research_article',source_file=str(raw)));continue
                records.append(dict(platform='web',kind='post',id=rid,post_id=rid,app=app,site=site['name'],site_id=site['id'],
                    title=article['title'] or item.get('title'),body=article['body'],author=article['author'],published_at=None,
                    published_at_display=article['published_at_display'],retrieved_at=now(),source_url=canonical(final),client='unknown',
                    material_role='professional_reference_candidate',review_status='pending_quality_review',
                    app_match_observed=app in article['body'] or app in article['title'],image_urls=article['image_urls'],images_reviewed=False,
                    source_file=str(raw),source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),context_status='article_text_obtained_images_unreviewed'))
                audit.append(dict(url=final,status='article_text_obtained',id=rid,source_file=str(raw),sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),discovery='host_search_import' if item['url'] in imported_urls else 'native_search'))
            except FetchError as e:
                audit.append(dict(url=item['url'],status=str(e)))
                if str(e) in STOP:status=str(e);break
    if not records and status=='search_finished':status='needs_host_search'
    return dict(site_id=site['id'],status=status,candidate_links=len(candidates),bodies_obtained=len(records),selected_articles=0,
        semantic_review_pending=bool(records),requests=audit,host_search_queries=spec['host_search_queries'],secondary_queries=spec['secondary_queries']),records

def run_collect(args):
    out=Path(args.output) if args.output else Path(cfg()['output'])/'professional'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+app_key(args.app))
    out.mkdir(parents=True,exist_ok=False);plan=make_plan(args.app,args.feature,args.competitor,args.sites);write(out/'plan.json',plan)
    imported=readlines(args.candidate_file) if args.candidate_file else []
    with ThreadPoolExecutor(max_workers=len(plan['sites'])) as pool:
        results=list(pool.map(lambda spec:collect_site(spec,args.app,out,args.query_budget,args.candidate_limit,imported),plan['sites']))
    all_records=[r for _,rows in results for r in rows];jsonlines(out/'records.jsonl',all_records)
    manifest=dict(app=args.app,created_at=now(),source_role='professional_reference',counts_as_user_feedback=False,article_target=None,
        sites=[meta for meta,_ in results],bodies_obtained=len(all_records),selected_articles=0,quality_review='pending',
        next_step='Read original texts, judge relevance and quality, then use review. Use host search for recorded discovery gaps; no quota to fill.')
    write(out/'manifest.json',manifest)
    # Explicit test outputs do not change the user's latest pointer.
    if not args.output:write(out.parent/('latest-'+app_key(args.app)+'.json'),dict(app=args.app,path=str(out)))
    print(json.dumps(dict(output=str(out),status='professional_review_pending',bodies_obtained=len(all_records),selected_articles=0,
        article_target=None,needs_host_search=[s['site_id'] for s in manifest['sites'] if s['host_search_queries'] and s['status']!='search_finished']),ensure_ascii=False))

def review(run,decisions):
    run=Path(run);meta=json.loads((run/'manifest.json').read_text(encoding='utf-8'));records={r['id']:r for r in readlines(run/'records.jsonl')};selected=[];seen=set()
    previous=run/'quality-review.json'
    prior={d['id']:d for d in json.loads(previous.read_text(encoding='utf-8'))} if previous.exists() else {}
    incoming=[d.get('id') for d in decisions]
    if len(incoming)!=len(set(incoming)):raise ValueError('repeated professional article decision')
    prior.update({d.get('id'):d for d in decisions});decisions=list(prior.values())
    for d in decisions:
        rid=d.get('id')
        if rid not in records or rid in seen:raise ValueError('unknown or repeated professional article ID')
        seen.add(rid)
        if d.get('decision') not in ('include','exclude'):raise ValueError('article decision is required')
        if not isinstance(d.get('rationale'),str) or not d['rationale'].strip():raise ValueError('quality/relevance rationale is required')
        if d['decision']=='exclude':continue
        for key in ('viewpoint','limitations'):
            if not isinstance(d.get(key),str) or not d[key].strip():raise ValueError('selected article needs '+key)
        if d.get('app_relation') not in ('same_app','same_task','cross_product','method_only'):raise ValueError('explicit article relation is required')
        r=records[rid];excerpt=d.get('excerpt')
        if not isinstance(excerpt,str) or not excerpt or len(excerpt)>400 or excerpt not in r['body']:raise ValueError('selected article needs a short exact source excerpt')
        selected.append(dict(r,body=excerpt,material_role='professional_reference',review_status='model_or_human_selected',
            quality_review=dict(d),full_text_file=str(run/(rid+'.txt'))))
    # Unreviewed/omitted candidates never become selected by default. Explicit empty selection is valid.
    jsonlines(run/'selected-records.jsonl',selected);write(run/'quality-review.json',decisions)
    meta.update(selected_articles=len(selected),reviewed_articles=len(seen),quality_review='complete' if len(seen)==len(records) else 'partial',reviewed_at=now())
    for s in meta.get('sites',[]):s['selected_articles']=sum(r.get('site_id')==s['site_id'] for r in selected)
    write(run/'manifest.json',meta);return selected

def merged(output,app):
    rows={};runs=[]
    for f in sorted((Path(output)/'professional').glob('*/manifest.json')):
        m=json.loads(f.read_text(encoding='utf-8'))
        if m.get('app')!=app:continue
        runs.append(dict(run=f.parent.name,bodies_obtained=m.get('bodies_obtained',0),selected_articles=m.get('selected_articles',0),quality_review=m.get('quality_review'),sites=m.get('sites',[])))
        selected=f.parent/'selected-records.jsonl'
        if not selected.exists():continue
        for r in readlines(selected):
            if r.get('app')!=app or r.get('kind')!='post' or r.get('material_role')!='professional_reference':raise ValueError('invalid professional selection')
            rows[r['id']]=r
    return list(rows.values()),dict(status='professional_articles_selected' if rows else 'professional_selection_pending' if runs else 'not_run',
        selected_articles=len(rows),counts_as_user_feedback=False,article_target=None,runs=runs)

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for cmd in ('plan','collect'):
        s=sub.add_parser(cmd);s.add_argument('--app',required=True);s.add_argument('--feature',action='append',default=[]);s.add_argument('--competitor',action='append',default=[])
        s.add_argument('--sites',nargs='+',choices=list(SITES),default=list(SITES));s.add_argument('--output',type=Path)
        if cmd=='collect':
            s.add_argument('--query-budget',type=int,default=2,help='bounded search requests per site, not an article quota')
            s.add_argument('--candidate-limit',type=int,default=8,help='bounded first-pass body fetches per site, not a selection target')
            s.add_argument('--candidate-file',type=Path,help='JSONL public article URLs discovered with host search')
    s=sub.add_parser('review');s.add_argument('run',type=Path);s.add_argument('decisions',type=Path)
    a=p.parse_args()
    if a.command=='plan':
        value=make_plan(a.app,a.feature,a.competitor,a.sites)
        if a.output:write(a.output,value)
        print(json.dumps(value,ensure_ascii=False,indent=2))
    elif a.command=='collect':
        if not 0<=a.query_budget<=8 or (a.query_budget==0 and not a.candidate_file) or not 1<=a.candidate_limit<=30:p.error('query-budget 0 requires candidate-file; maximum 8; candidate-limit 1..30 are request bounds only')
        run_collect(a)
    else:print(json.dumps(dict(selected_articles=len(review(a.run,readlines(a.decisions)))),ensure_ascii=False))
if __name__=='__main__':main()
