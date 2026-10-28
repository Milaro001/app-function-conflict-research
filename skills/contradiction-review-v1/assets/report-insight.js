// Insight maps: journey + service blueprint share one stage grid, so a column reads
// from the user's feeling down to the back-stage system behind it. Feelings are read
// from quotes (not measured); dashed lines and "待验证" mark causes not yet confirmed.
const insStageNames={discover:'了解与打开',onboard:'注册授权',track:'查看进度',notify:'通知提醒',pickup:'取件',send:'寄件',pay:'付款结算',service:'客服求助',after_sale:'售后理赔',account:'账号与设置',other:'其他'};
const insLevelNames={symptom:'表象',direct:'直接原因',underlying:'深层原因'};
const insFeel={'-2':'很困扰','-1':'不顺','0':'一般','1':'顺利','2':'满意'};
const insPointLabels=['用户遇到','可能原因','先做什么'];
function insQuote(p,id){const f=p?.facts?.find(x=>x.evidence_id===id);if(f)return f.anchor;const b=(byId.get(id)?.body||'').replace(/\s+/g,' ');return b.length>42?b.slice(0,42)+'…':b}
function insSources(ids){return new Set(ids.map(id=>byId.get(id)?.platform).filter(Boolean))}
function insMeter(parent,level,label){const m=add(parent,'span',undefined,'ins-meter');m.dataset.level=level;m.dataset.kind=label==='投入'?'effort':'impact';m.setAttribute('aria-label',label+'：'+level+'，研究估计');for(let k=0;k<3;k++)add(m,'i');add(m,'b',level);return m}
function insStrength(parent,ids){
 const n=ids.length,src=insSources(ids).size,level=n>=3&&src>=2?3:n>=2?2:n?1:0;
 const w=add(parent,'span',undefined,'ins-strength');w.dataset.level=level;for(let k=0;k<3;k++)add(w,'i');
 add(w,'b',n?`${n}条原话 · ${src}个平台`:'暂无原话');return w;
}
function insQuoteButton(parent,p,id,stage){
 const e=byId.get(id),b=add(parent,'button',undefined,'ins-quote');b.type='button';b.dataset.platform=e?.platform||'';if(stage!==undefined)b.dataset.stage=stage;
 add(b,'q',insQuote(p,id));add(b,'small',sourceNames[e?.platform]||e?.platform||'来源待核');
 b.onclick=()=>nodeDetails('用户原话',[['摘录',insQuote(p,id)]],[id]);return b;
}
function insHover(root){
 const set=k=>{root.dataset.hotStage=k??'';for(const n of root.querySelectorAll('[data-stage]'))n.classList.toggle('is-hot',k!=null&&n.dataset.stage===k)};
 root.addEventListener('pointerover',e=>{const t=e.target.closest('[data-stage]');if(t&&root.contains(t))set(t.dataset.stage)});
 root.addEventListener('pointerleave',()=>set(null));
 root.addEventListener('focusin',e=>{const t=e.target.closest('[data-stage]');set(t?t.dataset.stage:null)});
}
function insCurve(holder,stages,breakIndex){
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.classList.add('ins-curve');svg.setAttribute('role','img');
 svg.setAttribute('aria-label','各步骤感受示意，依据原话解读，不是实测评分');holder.append(svg);
 let played=false;
 const draw=()=>{
  const w=holder.clientWidth,h=150;if(!w)return;svg.setAttribute('width',w);svg.setAttribute('height',h);svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.replaceChildren();
  const col=w/stages.length,y=f=>22+(2-f)*(h-44)/4,mk=(tag,attrs)=>{const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);svg.append(n);return n};
  for(const [f,label]of [[2,'满意'],[0,'一般'],[-2,'很困扰']]){mk('line',{x1:0,x2:w,y1:y(f),y2:y(f),class:'ins-curve-grid'+(f===0?' is-zero':'')});mk('text',{x:4,y:y(f)-5,class:'ins-curve-axis'}).textContent=label}
  if(breakIndex>=0)mk('rect',{x:breakIndex*col+4,y:4,width:col-8,height:h-8,rx:10,class:'ins-curve-break'});
  const pts=stages.map((s,k)=>s.feeling==null?null:[col*(k+.5),y(s.feeling),s.feeling]);
  // Segments only join stages that both have quotes; a stage without material leaves a gap.
  let d='';for(let k=0;k<pts.length;k++){const p=pts[k];if(!p)continue;const prev=pts[k-1];if(prev){const mx=(prev[0]+p[0])/2;d+=` C ${mx} ${prev[1]}, ${mx} ${p[1]}, ${p[0]} ${p[1]}`}else d+=` M ${p[0]} ${p[1]}`}
  const path=mk('path',{d:d.trim(),class:'ins-curve-line'});
  stages.forEach((s,k)=>{const p=pts[k],cx=col*(k+.5);
   if(!p){mk('circle',{cx,cy:y(0),r:6,class:'ins-curve-empty'});mk('text',{x:cx,y:y(0)+22,class:'ins-curve-note','text-anchor':'middle'}).textContent=s.evidence_ids?.length?'感受待判':'待补原话';return}
   const dot=mk('circle',{cx:p[0],cy:p[1],r:k===breakIndex?9:7,class:'ins-curve-dot','data-feel':p[2],tabindex:0,role:'button','aria-label':s.label+'：'+insFeel[p[2]]+'，查看解读与原话'});dot.dataset.stage=k;
   const open=()=>nodeDetails(s.label+' · 感受解读',[['研究解读',s.feeling_basis?.interpretation||'依据对应原话作定性解读，不是连续实测或统计评分。'],...(s.feeling_basis?.anchor?[['感受依据',s.feeling_basis.anchor]]:[])],s.evidence_ids||[]);dot.onclick=open;dot.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open()}};
   if(k===breakIndex){mk('circle',{cx:p[0],cy:p[1],r:15,class:'ins-curve-ring'});mk('text',{x:p[0],y:Math.max(14,p[1]-22),class:'ins-curve-flag','text-anchor':'middle'}).textContent='断点'}
  });
  if(!played&&!matchMedia('(prefers-reduced-motion: reduce)').matches&&path.getTotalLength){const len=path.getTotalLength();path.style.strokeDasharray=len;path.style.strokeDashoffset=len;requestAnimationFrame(()=>{path.style.transition='stroke-dashoffset 1.1s cubic-bezier(.3,.7,.2,1)';path.style.strokeDashoffset=0})}
  played=true;
 };
 const ro=new ResizeObserver(()=>requestAnimationFrame(draw));ro.observe(holder);wireObservers.add(ro);return {setStages(next){stages=next;played=false;draw()}};
}
function insGuide(root,nav){
 const steps=()=>[...root.querySelectorAll('.map-step')];let at=0;
 const bar=add(root,'div',undefined,'ins-guide-bar');bar.hidden=true;bar.setAttribute('role','group');bar.setAttribute('aria-label','逐步讲解');
 const prev=add(bar,'button','上一步');const where=add(bar,'span','', 'ins-guide-where');const next=add(bar,'button','下一步','primary');const exit=add(bar,'button','退出讲解');
 const show=k=>{const list=steps();at=Math.max(0,Math.min(list.length-1,k));list.forEach((s,n)=>{s.open=n===at;s.classList.toggle('is-guided',n===at)});where.textContent=`第 ${at+1} / ${list.length} 步 · ${list[at].querySelector('h3').textContent.replace(/^\d+/,'')}`;prev.disabled=at===0;next.textContent=at===list.length-1?'完成':'下一步';requestAnimationFrame(()=>list[at].scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}))};
 const stop=()=>{bar.hidden=true;root.classList.remove('is-guiding');for(const s of steps()){s.open=true;s.classList.remove('is-guided')}};
 prev.onclick=()=>show(at-1);next.onclick=()=>at===steps().length-1?stop():show(at+1);exit.onclick=stop;
 requestAnimationFrame(()=>root.append(bar));
 const start=add(nav,'button','逐步讲解','ins-guide-start');start.type='button';start.onclick=()=>{root.classList.add('is-guiding');bar.hidden=false;show(0)};
}
function insProgress(root,nav){
 const scroller=document.getElementById('content'),buttons=[...nav.querySelectorAll('[data-goto]')];
 const io=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){for(const b of buttons)b.toggleAttribute('aria-current',b.dataset.goto===e.target.dataset.step)}},{root:scroller,rootMargin:'-20% 0px -70% 0px'});
 for(const s of root.querySelectorAll('.map-step'))io.observe(s);wireObservers.add(io);
}

function drawInsightMaps(root,i,p,s){
 const x=i.insight,stages=x.journey?.stages||[],breakIndex=stages.findIndex(st=>st.key===x.journey?.breakpoint);
 root.classList.add('insight-root');
 // Hero: the one-line conclusion and up to three points replace the long paragraph.
 const hero=add(root,'section',undefined,'ins-hero');hero.setAttribute('aria-label','本议题结论');
 add(hero,'h3',x.headline,'ins-headline');
 if(x.key_points?.length){const ul=add(hero,'ul',undefined,'ins-points');x.key_points.forEach((t,k)=>{const li=add(ul,'li');if(x.key_points.length===3)add(li,'span',insPointLabels[k],'ins-point-label');add(li,'span',t)})}
 const chips=add(hero,'div',undefined,'ins-chips');
 if(x.confidence){const c=add(chips,'span',undefined,'ins-chip');add(c,'b','可信度 '+x.confidence.level);add(c,'span',x.confidence.reason);c.dataset.level=x.confidence.level}
 if(x.impact){const c=add(chips,'span',undefined,'ins-chip');add(c,'b','影响 '+x.impact.task+' · '+x.impact.level);add(c,'span',x.impact.scope_note)}
 if(s){const c=add(chips,'span',undefined,'ins-chip');add(c,'b',`${count(s.semantic_groups)}条相关反馈`);add(c,'span',`另有${count(s.post_count)}条关联帖子，来自${count(s.source_count)}个平台；不等于人数`)}

 const nav=add(root,'nav',undefined,'step-nav ins-nav');nav.setAttribute('aria-label','议题分析步骤');
 const titles=[[1,'卡在哪一步'],[2,'前台与后台'],[3,'谁在说什么'],[4,'为什么'],[5,'怎么改'],[6,'怎么验证']];
 for(const [n,t]of titles){const b=add(nav,'button',String(n).padStart(2,'0')+' '+t);b.dataset.goto=n;b.onclick=()=>openAnalysisStep(n)}
 const foldActions=add(nav,'span',undefined,'step-fold-actions');for(const [label,open]of [['全部收起',false],['全部展开',true]]){const button=add(foldActions,'button',label);button.onclick=()=>{for(const step of root.querySelectorAll('.map-step'))step.open=open}}
 insGuide(root,foldActions);

 const service=add(root,'div',undefined,'ins-service');insHover(service);
 const cols=`repeat(${Math.max(stages.length,1)},minmax(150px,1fr))`;
 // 01 Journey: stage header, feeling curve, and the quotes behind each feeling.
 const a=mapStep(service,1,'用户在哪一步卡住','按原话重建任务旅程；曲线是不同作者原话的感受示意，不是同一用户的连续实测。');
 if(stages.length){
  const allIds=stages.flatMap(st=>st.evidence_ids||[]),platforms=[...insSources(allIds)];let curveView=null;
  if(platforms.length){const f=add(a,'div',undefined,'ins-filter');f.setAttribute('role','group');f.setAttribute('aria-label','按平台筛选原话');add(f,'span','原话来源','ins-filter-label');
   for(const key of ['',...platforms]){const b=add(f,'button',key?sourceNames[key]||key:'全部平台');b.type='button';b.setAttribute('aria-pressed',String(!key));
    b.onclick=()=>{for(const o of f.querySelectorAll('button'))o.setAttribute('aria-pressed',String(o===b));fillQuotes(key);
     const filtered=stages.map(st=>{const ids=(st.evidence_ids||[]).filter(id=>!key||byId.get(id)?.platform===key),basis=st.feeling_basis?.evidence_id,hasBasis=!key||(basis?byId.get(basis)?.platform===key:ids.length);return {...st,evidence_ids:ids,feeling:ids.length&&hasBasis?st.feeling:null}});curveView?.setStages(filtered);
     for(const [n,c]of [...a.querySelectorAll('.ins-quotes-col')].entries()){const muted=![...c.querySelectorAll('.ins-quote')].some(q=>!q.hidden);c.classList.toggle('is-muted',muted);const label=a.querySelector(`.ins-stage-head[data-stage="${n}"] small`);if(label)label.textContent=filtered[n].feeling==null?(filtered[n].evidence_ids.length?'感受待判':'待补原话'):insFeel[filtered[n].feeling]}}}}
  const scroll=add(a,'div',undefined,'ins-scroll');const grid=add(scroll,'div',undefined,'ins-journey');grid.style.setProperty('--cols',cols);
  stages.forEach((st,k)=>{const h=add(grid,'div',undefined,'ins-stage-head stage-cell');h.dataset.stage=k;h.tabIndex=0;if(k===breakIndex)h.classList.add('is-break');
   add(h,'span',String(k+1),'ins-stage-index');add(h,'strong',st.label);add(h,'small',st.feeling==null?(st.evidence_ids?.length?'感受待判':'待补原话'):insFeel[st.feeling])});
  const curve=add(grid,'div',undefined,'ins-curve-holder');curveView=insCurve(curve,stages,breakIndex);
  stages.forEach((st,k)=>{const c=add(grid,'div',undefined,'ins-quotes-col stage-cell');c.dataset.stage=k;if(k===breakIndex)c.classList.add('is-break')});
  function fillQuotes(key=''){for(const [k,c]of [...a.querySelectorAll('.ins-quotes-col')].entries()){c.replaceChildren();const st=stages[k],ids=(st.evidence_ids||[]).filter(id=>!key||byId.get(id)?.platform===key);
   if(!ids.length)add(c,'p',key?'这个平台暂未采到这一步的原话':'这一步还没有用户原话','ins-empty');for(const id of ids.slice(0,2))insQuoteButton(c,p,id,k);
   if(ids.length>2){const more=add(c,'button',`另 ${ids.length-2} 条原话`,'text-button');more.onclick=()=>nodeDetails(st.label+' 的用户原话',[],ids)}}}
  fillQuotes();
 }else add(a,'p','这项议题还没有整理成旅程步骤。','ins-empty');

 // 02 Blueprint: the same columns, split by the line of visibility.
 const b=mapStep(service,2,'问题出在前台还是后台','服务蓝图：上面两行是用户能看到的，下面一行是支撑它的系统或角色。断点所在列已高亮。');
 if(stages.length){
  const scroll=add(b,'div',undefined,'ins-scroll');const bp=add(scroll,'div',undefined,'ins-blueprint');bp.style.setProperty('--cols',cols);
  const lane=(label,field,cls)=>{add(bp,'div',label,'ins-lane-label '+cls);stages.forEach((st,k)=>{const c=add(bp,'div',st[field],'ins-cell stage-cell '+cls);c.dataset.stage=k;if(k===breakIndex)c.classList.add('is-break')})};
  add(bp,'div','','ins-lane-label ins-corner');stages.forEach((st,k)=>{const c=add(bp,'div',st.label,'ins-cell ins-cell-head stage-cell');c.dataset.stage=k;if(k===breakIndex)c.classList.add('is-break')});
  lane('用户在做什么','user_action','lane-user');lane('看到的界面','touchpoint','lane-front');
  add(bp,'div','用户看不到的部分','ins-visibility');
  lane('背后的系统','backstage','lane-back');
 }
 if(p?.alignment?.length){const check=add(b,'details',undefined,'ins-align');add(check,'summary','先确认是不是同一件事（'+p.alignment.length+'项）');const ul=add(check,'ul');for(const row of p.alignment){const [what,found,why]=Array.isArray(row)?row:[row.condition,row.observed,row.implication];const li=add(ul,'li');add(li,'strong',what);add(li,'span',found);add(li,'small',why)}}

 // 03 Segments: situational groups, not "likes vs dislikes".
 const c=mapStep(root,3,'谁在说，他们想要什么','按使用情境分人群；同一个人可能同时属于几类。');
 const segs=add(c,'div',undefined,'ins-segments');
 for(const seg of x.segments||[]){const card=add(segs,'article',undefined,'ins-segment');add(card,'h4',seg.name);
  const dl=add(card,'dl');for(const [k,v]of [['在什么情况下',seg.situation],['想要',seg.need]]){const r=add(dl,'div');add(r,'dt',k);add(r,'dd',v)}
  const ids=seg.evidence_ids||[];if(ids.length){const more=add(card,'button',undefined,'ins-segment-ids');insStrength(more,ids);more.onclick=()=>nodeDetails(seg.name+' 的原话',[['情境',seg.situation],['想要',seg.need]],ids)}}
 const verdict=add(c,'div',undefined,'ins-verdict');tag(verdict,i.relation);add(verdict,'p',p?.why_relation||relationExplanation[i.relation]);

 // 04 Root-cause ladder: solid = observed in quotes, dashed = still to verify.
 const d=mapStep(root,4,'为什么会这样','从表象往下追问；实线是原话里看得到的，虚线是还要验证的推测。');
 const ladder=add(d,'ol',undefined,'ins-ladder');
 for(const level of ['symptom','direct','underlying'])for(const rc of (x.root_cause||[]).filter(r=>r.level===level)){
  const li=add(ladder,'li',undefined,'ins-rung');li.dataset.status=rc.status;add(li,'span',insLevelNames[level],'ins-rung-level');
  const body=add(li,'div',undefined,'ins-rung-body');add(body,'p',rc.statement);const meta=add(body,'div',undefined,'ins-rung-meta');
  add(meta,'span',rc.status==='observed'?'已在原话中看到':'待验证','ins-status');
  const ids=rc.evidence_ids||[];const sb=add(meta,'button',undefined,'ins-strength-button');sb.type='button';insStrength(sb,ids);sb.disabled=!ids.length;sb.onclick=()=>nodeDetails(insLevelNames[level],[['判断',rc.statement]],ids);
 }
 if(i.hypotheses?.length){add(d,'h4','怎么区分这些原因','ins-subhead');const tests=add(d,'div',undefined,'ins-tests');
  for(const h of i.hypotheses){const row=add(tests,'div',undefined,'ins-test');add(row,'p',h.statement,'ins-test-claim');add(row,'p',h.disconfirming_question||'还需要补一个能区分的观察','ins-test-how');
   if(h.support_ids?.length){const b2=add(row,'button',undefined,'ins-strength-button');insStrength(b2,h.support_ids);b2.onclick=()=>nodeDetails('可能的原因（待验证）',[['原因',h.statement],['怎么验证',h.disconfirming_question||'']],h.support_ids)}}}

 // 05 Options matrix with before/after wireframes.
 const e=mapStep(root,5,'怎么改：方案对比','投入按改动范围估计，预期影响按目标任务判断；均为研究估计，需工程和业务复核。');
 const opts=i.options||[];
 if(opts.length){const scroll=add(e,'div',undefined,'ins-scroll');const m=add(scroll,'div',undefined,'ins-matrix');m.style.setProperty('--opts',opts.length);
  add(m,'div','','ins-m-corner');opts.forEach((o,k)=>add(m,'div','方案 '+String.fromCharCode(65+k),'ins-m-head'));
  const row=(label,fn)=>{add(m,'div',label,'ins-m-label');opts.forEach(o=>{const c=add(m,'div',undefined,'ins-m-cell');fn(c,o)})};
  row('改什么',(c,o)=>add(c,'p',o.action,'ins-m-action'));
  if(opts.some(o=>o.wireframe))row('界面怎么变',(c,o)=>{if(!o.wireframe){add(c,'p','暂无示意','ins-empty');return}const w=add(c,'div',undefined,'ins-wire');
   const phone=(title,items,mark)=>{const f=add(w,'figure',undefined,'ins-phone');add(f,'figcaption',title);const screen=add(f,'div',undefined,'ins-screen');for(const t of items){const blk=add(screen,'div',t,'ins-blk');if(mark&&!o.wireframe.before.includes(t))blk.classList.add('is-new')}};
   phone('现在',o.wireframe.before,false);add(w,'span','','ins-wire-arrow').setAttribute('aria-hidden','true');phone('改后',o.wireframe.after,true)});
  row('适合什么时候',(c,o)=>add(c,'p',o.conditions));
  row('代价与影响谁',(c,o)=>add(c,'p',o.tradeoff));
  if(opts.some(o=>o.effort||o.impact_level))row('投入 / 预期影响',(c,o)=>{const r=add(c,'div',undefined,'ins-meters');const a1=add(r,'span',undefined,'ins-meter-row');add(a1,'small','投入');insMeter(a1,o.effort||'待核','投入');const a2=add(r,'span',undefined,'ins-meter-row');add(a2,'small','预期影响');insMeter(a2,o.impact_level||'待核','预期影响')});
  if(opts.some(o=>o.estimate_basis))row('估计依据',(c,o)=>{add(c,'p',o.estimate_basis||'关键依赖待补，补齐后再估计。','ins-estimate-basis');if(o.estimate_assumptions)add(c,'small','前提：'+o.estimate_assumptions,'ins-estimate-assumptions')});
  row('怎么验证',(c,o)=>add(c,'p',o.validation_task));
 }
 if(x.benchmarks?.length){add(e,'h4','别人怎么做','ins-subhead');const ul=add(e,'ul',undefined,'ins-bench');
  for(const bm of x.benchmarks){const li=add(ul,'li');add(li,'strong',bm.name);add(li,'span',bm.question);const st=add(li,bm.status==='reported_by_user'?'button':'span',bm.status==='reported_by_user'?'用户提到 · 看原话':'待查证','ins-bench-status');st.dataset.status=bm.status;
   if(bm.status==='reported_by_user')st.onclick=()=>nodeDetails(bm.name,[['用户提到的对比',bm.question]],bm.evidence_ids||[])}}

 // 06 Verification route: a real sequence, so it is numbered.
 const f=mapStep(root,6,'怎么验证，做到什么算成功','按顺序做；每一步写清谁来做、多少样本、结果决定什么。');
 if(x.next_steps?.length){const ol=add(f,'ol',undefined,'ins-route');
  x.next_steps.forEach(n=>{const li=add(ol,'li',undefined,'ins-route-step');const head=add(li,'div',undefined,'ins-route-head');add(head,'span',n.method,'ins-method');add(head,'strong',n.owner);
   add(li,'p',n.action,'ins-route-action');const dl=add(li,'dl');for(const [k,v]of [['样本',n.sample],['用时',n.duration],['通过标准',n.pass_rule]]){const r=add(dl,'div');add(r,'dt',k);add(r,'dd',v)}
   add(li,'p','结果决定：'+n.decides,'ins-decides')})}
 else if(p?.next_step)add(f,'p',p.next_step);
 if(x.metrics?.length){add(f,'h4','成功指标','ins-subhead');const t=add(f,'table',undefined,'ins-metrics');const hr=add(add(t,'thead'),'tr');for(const h of ['指标','怎么算','做到什么算成功'])add(hr,'th',h);const tb=add(t,'tbody');
  for(const mtr of x.metrics){const r=add(tb,'tr');add(r,'th',mtr.name);add(r,'td',mtr.definition);add(r,'td',mtr.pass_rule)}add(f,'p','起点数值需上线前实测，这里不预填改善百分比。','chart-footnote')}
 const choose=add(f,'button','选择这项议题的下一步','primary');choose.onclick=()=>goToIssue(i.id,'review');
 if(i.conditions?.length){const boundary=add(root,'details',undefined,'boundary');add(boundary,'summary','这项判断的适用条件与证据缺口');list(boundary,i.conditions)}
 insProgress(root,nav);
}
