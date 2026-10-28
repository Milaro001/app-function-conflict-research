// HTML nodes keep text selectable and accessible; SVG connects their actual bounds.
// Dashed links are hypotheses to test, never a claim of demonstrated causality.
let reasonSequence=0;
const wireObservers=new Set();
function clearReasonWires(){for(const o of wireObservers)o.disconnect();wireObservers.clear()}
const reasonDialog=document.getElementById('reason-dialog');
document.getElementById('reason-close').onclick=()=>reasonDialog.close();
function nodeDetails(title,sections,ids=[]){
 hideChartTip();document.getElementById('reason-title').textContent=title;const body=document.getElementById('reason-body');body.replaceChildren();
 for(const [label,text]of sections){const s=add(body,'section',undefined,'node-detail-section');add(s,'h3',label);add(s,'p',text)}
 for(const id of [...new Set(ids)]){const e=byId.get(id)||analyticRows.get(id);if(!e)continue;const s=add(body,'section',undefined,'node-detail-source');add(s,'small',(sourceNames[e.platform]||e.platform)+' · '+displayDate(e.published_at));add(s,'h3','原文与已取得上下文');add(s,'pre',e.context_text||e.body);if(e.source_url){const a=add(s,'a','打开来源原文');a.href=e.source_url;a.target='_blank';a.rel='noopener noreferrer'}
  if(report.issues.find(x=>x.id===selected)?.anchors.some(a=>a.evidence_id===id)){const b=add(s,'button','在议题证据中定位','table-link');b.onclick=()=>{reasonDialog.close();evidenceJump(id)}}
 }reasonDialog.showModal();
}
const stepFoldKey='cr-step-folds:'+report.bundle_id;
let stepFolds={};try{const saved=JSON.parse(localStorage.getItem(stepFoldKey)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))stepFolds=saved}catch{}
function mapStep(root,n,title,subtitle){
 const section=add(root,'details',undefined,'reason-step map-step');section.id='step-'+n;section.dataset.step=n;
 section.open=stepFolds[selected]?.[n]!==true;
 const summary=add(section,'summary',undefined,'step-toggle');const h=add(summary,'h3');add(h,'span',String(n).padStart(2,'0'),'step-number');h.append(document.createTextNode(title));
 const cue=add(summary,'span',undefined,'step-fold-cue');add(cue,'span','收起','step-fold-label');add(cue,'i',undefined,'step-chevron');
 const body=add(section,'div',undefined,'step-body');if(subtitle)add(body,'p',subtitle,'map-caption');
 const iid=selected;section.addEventListener('toggle',()=>{section.querySelector('.step-fold-label').textContent=section.open?'收起':'展开';stepFolds[iid]??={};stepFolds[iid][n]=!section.open;try{localStorage.setItem(stepFoldKey,JSON.stringify(stepFolds))}catch{}});
 if(!section.open)section.querySelector('.step-fold-label').textContent='展开';return body;
}
function openAnalysisStep(n){const target=document.getElementById('step-'+n);if(!target)return;target.open=true;requestAnimationFrame(()=>target.scrollIntoView({block:'start'}))}
function graphBoard(parent,kind,name){const board=add(parent,'div',undefined,'graph-board '+kind);board.dataset.graphId='graph-'+(++reasonSequence);board.setAttribute('role','group');board.setAttribute('aria-label',name);const grid=add(board,'div',undefined,'graph-grid');return {board,grid,links:[]}}
const graphExpansions=new WeakMap();
function graphNode(parent,label,text,kind='context',options={}){
 const node=add(parent,'article',undefined,'graph-node node-'+kind);node.dataset.nodeId='node-'+(++reasonSequence);
 add(node,'span',label,'node-label');const copy=add(node,'strong',text,'node-copy');
 const note=options.note?add(node,'span',options.note,'node-note'):null;
 if(options.className)node.classList.add(...options.className.split(' '));
 const shown=[label,text,options.note||''].join('\n').replace(/\s/g,'');
 const extraSections=(options.sections||[]).filter(([,t])=>t&&!shown.includes(String(t).replace(/\s/g,'')));
 const extraIds=(options.ids||[]).filter(id=>{const e=byId.get(id)||analyticRows.get(id);return e?.body&&!shown.includes(e.body.replace(/\s/g,''))||e?.context_text&&/原帖|父回复|回复对象/.test(e.context_text)});
 const open=add(node,'button','展开说明与原文 ↗','node-open');open.type='button';open.hidden=true;open.setAttribute('aria-label','展开：'+label);open.onclick=()=>nodeDetails(label,options.sections||[['完整说明',text]],options.ids||[]);
 graphExpansions.set(node,()=>{const clipped=copy.scrollHeight>copy.clientHeight+2||note&&note.scrollHeight>note.clientHeight+2;open.hidden=!(clipped||extraSections.length||extraIds.length);node.classList.toggle('can-expand',!open.hidden)});
 return node;
}
function refreshExpansions(board){for(const n of board.querySelectorAll('.graph-node'))graphExpansions.get(n)?.()}
function observeExpansions(board){const observer=new ResizeObserver(()=>requestAnimationFrame(()=>refreshExpansions(board)));observer.observe(board);wireObservers.add(observer);requestAnimationFrame(()=>refreshExpansions(board))}
function link(map,from,to,dashed=false){map.links.push({from,to,dashed})}
function finishMap(map){
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.classList.add('map-wires');svg.setAttribute('aria-hidden','true');map.board.prepend(svg);
 const redraw=()=>{if(!map.board.isConnected||!map.board.offsetWidth)return;const bounds=map.board.getBoundingClientRect(),width=map.board.offsetWidth,height=map.board.offsetHeight,scale=bounds.width/width;svg.setAttribute('width',width);svg.setAttribute('height',height);svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.replaceChildren();const localBox=node=>{const r=node.getBoundingClientRect();return {left:(r.left-bounds.left)/scale,top:(r.top-bounds.top)/scale,right:(r.right-bounds.left)/scale,bottom:(r.bottom-bounds.top)/scale,width:r.width/scale,height:r.height/scale}};
  const defs=document.createElementNS(ns,'defs'),marker=document.createElementNS(ns,'marker'),mark='arrow-'+map.board.dataset.graphId;marker.id=mark;marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','8');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','5');marker.setAttribute('markerHeight','5');marker.setAttribute('orient','auto-start-reverse');const arrow=document.createElementNS(ns,'path');arrow.setAttribute('d','M 0 1 L 9 5 L 0 9');arrow.setAttribute('fill','none');arrow.setAttribute('stroke','var(--diagram-line)');arrow.setAttribute('stroke-width','1.5');marker.append(arrow);defs.append(marker);svg.append(defs);
  for(const e of map.links){const a=localBox(e.from),b=localBox(e.to);let x1,y1,x2,y2,d;
   const horizontal=b.left>=a.right-2&&Math.abs((a.top+a.height/2)-(b.top+b.height/2))<Math.max(a.height,b.height)/2;
   if(horizontal){x1=a.right;y1=a.top+a.height/2;x2=b.left-2;y2=b.top+b.height/2;const mid=(x1+x2)/2;d=`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
   else if(b.top-a.bottom>45){x1=a.left;y1=a.top+a.height/2;x2=b.left-2;y2=b.top+b.height/2;d=`M ${x1} ${y1} H 6 V ${y2} H ${x2}`}
   else {x1=a.left+a.width/2;y1=a.bottom;x2=b.left+b.width/2;y2=b.top-2;const mid=(y1+y2)/2;d=`M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`}
   const path=document.createElementNS(ns,'path');path.setAttribute('d',d);path.setAttribute('fill','none');path.setAttribute('stroke','var(--diagram-line)');path.setAttribute('stroke-width','1.6');path.setAttribute('marker-end',`url(#${mark})`);if(e.dashed)path.setAttribute('stroke-dasharray','5 5');svg.append(path);
  }
 };
 const observer=new ResizeObserver(()=>requestAnimationFrame(()=>{refreshExpansions(map.board);redraw()}));observer.observe(map.board);wireObservers.add(observer);requestAnimationFrame(()=>{refreshExpansions(map.board);redraw()});
}
// This canvas changes only the view; node positions and research evidence stay intact.
const diagramViews=new Map();
function createDiagramCanvas(parent,issueId){
 const workbench=add(parent,'div',undefined,'diagram-workbench');
 const toolbar=add(workbench,'div',undefined,'canvas-toolbar');toolbar.setAttribute('role','group');toolbar.setAttribute('aria-label','条件图缩放工具');
 const title=add(toolbar,'span','条件对齐画布','canvas-title');
 const controls=add(toolbar,'div',undefined,'canvas-controls');
 const minus=add(controls,'button','−');minus.type='button';minus.setAttribute('aria-label','缩小条件图');
 const level=add(controls,'button','100%','canvas-level');level.type='button';level.setAttribute('aria-label','以100%查看条件图');
 const plus=add(controls,'button','＋');plus.type='button';plus.setAttribute('aria-label','放大条件图');
 const fitButton=add(controls,'button','适应画布');fitButton.type='button';
 const help=add(workbench,'p','拖动画布移动 · 按住 Ctrl / ⌘ 滚动可缩放 · 触屏支持双指缩放','canvas-help');help.id='canvas-help-'+issueId;
 const viewport=add(workbench,'div',undefined,'diagram-viewport');viewport.tabIndex=0;viewport.setAttribute('role','region');viewport.setAttribute('aria-label','可缩放与拖动的条件对齐图');viewport.setAttribute('aria-describedby',help.id);
 const world=add(viewport,'div',undefined,'diagram-world');
 let state={zoom:1,x:0,y:18,mode:'detail',...(diagramViews.get(issueId)||{})},ready=false;
 const minZoom=.2,maxZoom=2;
 const size=()=>({w:world.offsetWidth,h:world.offsetHeight,vw:viewport.clientWidth,vh:viewport.clientHeight});
 const constrain=()=>{const {w,h,vw,vh}=size();if(!vw||!vh)return;const sw=w*state.zoom,sh=h*state.zoom;state.x=sw<vw?(vw-sw)/2:Math.max(vw-sw-70,Math.min(70,state.x));state.y=sh<vh?(vh-sh)/2:Math.max(vh-sh-70,Math.min(70,state.y))};
 const paint=()=>{constrain();world.style.transform=`translate(${state.x}px,${state.y}px) scale(${state.zoom})`;level.textContent=Math.round(state.zoom*100)+'%';minus.disabled=state.zoom<=minZoom+.001;plus.disabled=state.zoom>=maxZoom-.001;viewport.dataset.zoom=state.zoom;viewport.dataset.panX=state.x;viewport.dataset.panY=state.y;diagramViews.set(issueId,{...state})};
 const zoomAt=(zoom,px=viewport.clientWidth/2,py=viewport.clientHeight/2)=>{if(!ready)return;const next=Math.max(minZoom,Math.min(maxZoom,zoom)),ratio=next/state.zoom;state.x=px-(px-state.x)*ratio;state.y=py-(py-state.y)*ratio;state.zoom=next;state.mode='detail';paint()};
 const fit=()=>{const {w,h,vw,vh}=size();if(!w||!h||!vw||!vh)return;state.zoom=Math.max(minZoom,Math.min(1,(vw-32)/w,(vh-32)/h));state.x=(vw-w*state.zoom)/2;state.y=(vh-h*state.zoom)/2;state.mode='fit';paint()};
 const reset=()=>{state.zoom=1;state.x=(viewport.clientWidth-world.offsetWidth)/2;state.y=18;state.mode='detail';paint()};
 minus.onclick=()=>zoomAt(state.zoom/1.25);plus.onclick=()=>zoomAt(state.zoom*1.25);level.onclick=reset;fitButton.onclick=fit;
 viewport.addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey)return;event.preventDefault();const box=viewport.getBoundingClientRect();zoomAt(state.zoom*Math.exp(-event.deltaY*.008),event.clientX-box.left,event.clientY-box.top)},{passive:false});
 const pointers=new Map();let gesture=null,dragged=false;
 const local=event=>{const box=viewport.getBoundingClientRect();return {x:event.clientX-box.left,y:event.clientY-box.top}};
 const startGesture=()=>{const points=[...pointers.values()];if(points.length>=2){const [a,b]=points;gesture={kind:'pinch',distance:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),zoom:state.zoom,x:state.x,y:state.y,mid:{x:(a.x+b.x)/2,y:(a.y+b.y)/2}}}else if(points.length){gesture={kind:'pan',point:points[0],x:state.x,y:state.y}}else gesture=null};
 viewport.addEventListener('pointerdown',event=>{if(!ready||event.button!==0||event.target.closest('button,a,input,select,textarea'))return;event.preventDefault();viewport.focus({preventScroll:true});pointers.set(event.pointerId,local(event));viewport.setPointerCapture(event.pointerId);dragged=false;startGesture();viewport.classList.add('is-dragging')});
 viewport.addEventListener('pointermove',event=>{if(!pointers.has(event.pointerId)||!gesture)return;const point=local(event);pointers.set(event.pointerId,point);state.mode='detail';if(gesture.kind==='pan'){const dx=point.x-gesture.point.x,dy=point.y-gesture.point.y;dragged||=Math.hypot(dx,dy)>4;state.x=gesture.x+dx;state.y=gesture.y+dy}else{const [a,b]=[...pointers.values()];if(!b)return;dragged=true;const mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};state.zoom=Math.max(minZoom,Math.min(maxZoom,gesture.zoom*Math.hypot(a.x-b.x,a.y-b.y)/gesture.distance));const ratio=state.zoom/gesture.zoom;state.x=mid.x-(gesture.mid.x-gesture.x)*ratio;state.y=mid.y-(gesture.mid.y-gesture.y)*ratio}paint()});
 const endPointer=event=>{pointers.delete(event.pointerId);if(viewport.hasPointerCapture(event.pointerId))viewport.releasePointerCapture(event.pointerId);startGesture();if(!pointers.size){viewport.classList.remove('is-dragging');setTimeout(()=>{dragged=false},0)}};
 viewport.addEventListener('pointerup',endPointer);viewport.addEventListener('pointercancel',endPointer);
 viewport.addEventListener('click',event=>{if(dragged){event.preventDefault();event.stopPropagation();dragged=false}},true);
 viewport.addEventListener('keydown',event=>{if(event.target!==viewport)return;const step=event.shiftKey?80:40;if(['+','=','-','0','1','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))event.preventDefault();else return;
  if(event.key==='+'||event.key==='=')zoomAt(state.zoom*1.25);else if(event.key==='-')zoomAt(state.zoom/1.25);else if(event.key==='0')fit();else if(event.key==='1')reset();else{state.mode='detail';if(event.key==='ArrowLeft')state.x+=step;if(event.key==='ArrowRight')state.x-=step;if(event.key==='ArrowUp')state.y+=step;if(event.key==='ArrowDown')state.y-=step;paint()}
 });
 const refresh=()=>{if(!viewport.isConnected||!viewport.clientWidth||!viewport.clientHeight||!world.offsetHeight)return;if(!ready){ready=true;if(diagramViews.has(issueId))paint();else reset()}else if(state.mode==='fit')fit();else paint()};
 return {world,mount(){const observer=new ResizeObserver(()=>requestAnimationFrame(refresh));observer.observe(viewport);observer.observe(world);wireObservers.add(observer);requestAnimationFrame(refresh)}};
}

function drawReasonMaps(root,i,p,s){
 const intro=add(root,'div',undefined,'analysis-map-intro');
 const material=add(intro,'div',undefined,'issue-evidence-strip');for(const [label,value]of [['条相关反馈',s?.semantic_groups],['条关联帖子',s?.post_count],['个平台',s?.source_count],['条完全符合本轮条件',s?.qualified_groups]]){const a=add(material,'span');add(a,'strong',count(value));a.append(document.createTextNode(' '+label))}
 const key=add(intro,'div',undefined,'map-key');for(const [label,cls]of [['蓝色 · 原文与研究对象','evidence'],['灰蓝 · 分析与条件','context'],['琥珀 · 待验证原因','hypothesis'],['青色 · 改法与验证','test']])add(key,'span',label,'map-key-'+cls);
 add(intro,'p','短内容直接阅读；较长说明或补充原文可展开。实线组织材料，虚线表示尚待验证的解释，不表示原因已经证实。','chart-footnote');
 const nav=add(root,'nav',undefined,'step-nav');nav.setAttribute('aria-label','议题分析步骤');for(const [n,t]of [[1,'反馈时间线'],[2,'条件对齐'],[3,'关系判断'],[4,'假设与反证'],[5,'方案比较'],[6,'下一步']]){const b=add(nav,'button',String(n).padStart(2,'0')+' '+t);b.onclick=()=>openAnalysisStep(n)}

 const foldActions=add(nav,'span',undefined,'step-fold-actions');for(const [label,open]of [['全部收起',false],['全部展开',true]]){const button=add(foldActions,'button',label);button.onclick=()=>{for(const step of root.querySelectorAll('.map-step'))step.open=open}};

 // 01. Source publication dates are not verified release or incident dates.
 const a=mapStep(root,1,'用户重点意见时间线','按发布日期排列，点击查看完整原文。');
 const timeline=add(a,'ol',undefined,'feedback-timeline');
 const facts=[...p.facts].sort((a,b)=>{const da=Date.parse(byId.get(a.evidence_id)?.published_at),db=Date.parse(byId.get(b.evidence_id)?.published_at);return (Number.isFinite(da)?da:Infinity)-(Number.isFinite(db)?db:Infinity)});
 for(const f of facts){
  const source=byId.get(f.evidence_id),item=add(timeline,'li',undefined,'timeline-entry');item.dataset.evidenceId=f.evidence_id;
  const date=source?.published_at,stamp=add(item,'time',date?new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(date)):'日期待核','timeline-date');if(date)stamp.dateTime=date;
  const body=add(item,'div',undefined,'timeline-content');add(body,'h4','“'+f.anchor+'”','timeline-opinion');
  const meta=add(body,'div',undefined,'timeline-meta');add(meta,'span',(sourceNames[source?.platform]||source?.platform||'来源待核')+(date&&new Date(date)<new Date(qa.scope.start)?' · 历史反馈':''));
  if(source?.source_url){const url=add(meta,'a','查看来源 ↗');url.href=source.source_url;url.target='_blank';url.rel='noopener noreferrer'}
  const extra=source?.body&&source.body.trim()!==f.anchor.trim()||source?.context_text&&/原帖|父回复|回复对象/.test(source.context_text);
  if(extra){const open=add(meta,'button','查看完整原文','text-button');open.onclick=()=>nodeDetails('这条反馈的原文与上下文',[['重点意见',f.anchor]],[f.evidence_id])}
 }

 // 02. A shared decision branches into the reported aims and comparison conditions.
 const b=mapStep(root,2,'先确认是不是同一件事','先看各自要完成什么，再核对使用条件。'),canvas=createDiagramCanvas(b,i.id),conditions=graphBoard(canvas.world,'condition-map','决策、诉求与条件分支图');
 const decision=graphNode(conditions.grid,'共同的决策对象',p.decision,'root',{className:'map-root'});
 const aims=add(conditions.grid,'div',undefined,'graph-two map-wide');const sideA=graphNode(aims,'已取得的诉求／目标',p.side_a,'context'),sideB=graphNode(aims,i.relation==='one_sided_issue'?'另一侧证据状态':'另一些材料／条件',p.side_b,'context');link(conditions,decision,sideA);link(conditions,decision,sideB);
 const hub=graphNode(conditions.grid,'进入可比性检查','核对以下条件，再判断能否放在一起比较。','context',{className:'map-wide'});link(conditions,sideA,hub);link(conditions,sideB,hub);const checks=add(conditions.grid,'div',undefined,'graph-three map-wide');for(const row of p.alignment||[]){const check=graphNode(checks,row[0],row[1],'check',{note:row[2],sections:[['需要对齐的条件',row[0]],['现有材料',row[1]],['对判断的作用',row[2]]]});link(conditions,hub,check)}finishMap(conditions);canvas.mount();

 // 03. A comparison and verdict need no directional arrows.
 const c=mapStep(root,3,'这些用户到底想改什么','先并排比较现有材料，再说明是否真的需要在两种要求之间取舍。');
 const relation=add(c,'div',undefined,'relation-comparison');
 const pair=add(relation,'div',undefined,'graph-two');graphNode(pair,'一侧用户的目标',p.side_a,'context');graphNode(pair,i.relation==='one_sided_issue'?'相反意见找到了吗':'另一些材料说了什么',p.side_b,'context');
 const result=graphNode(relation,relations[i.relation][0],p.why_relation,'result',{sections:[['判定依据',p.why_relation],['适用边界',(i.conditions||[]).join('\n\n')]]});observeExpansions(relation);

 // 04. Evidence -> tentative interpretation -> discriminating observation.
 const d=mapStep(root,4,'用什么观察区分原因假设','每条虚线都是待验证的解释路径，反证问题用于推翻或修正假设。'),hypotheses=graphBoard(d,'hypothesis-map','原因假设与反证路径图');
 for(const [n,h]of (i.hypotheses||[]).entries()){
  const row=add(hypotheses.grid,'div',undefined,'graph-three map-wide'),ids=h.support_ids||[];
  const anchors=ids.map(id=>p.facts.find(f=>f.evidence_id===id)?.anchor||byId.get(id)?.body||'原文待补');
  const support=graphNode(row,'用户原话 · '+ids.length+'条',anchors.join('\n'),'evidence',{ids,sections:anchors.map((t,k)=>['依据 '+(k+1),t])});
  const hypothesis=graphNode(row,'可能的原因（待验证）'+(n+1),h.statement,'hypothesis',{ids,sections:[['原因假设',h.statement],['怎样区分或推翻',h.disconfirming_question||'需补可区分的观察']]});
  const test=graphNode(row,'怎么验证',h.disconfirming_question||'需补可区分的观察','test');link(hypotheses,support,hypothesis,true);link(hypotheses,hypothesis,test,true);
 }finishMap(hypotheses);

 // 05. Aligned alternative panels keep each complete proposal in one place.
 const e=mapStep(root,5,'把两种改法放在一起比较','每张卡是一套完整方案，按相同项目比较条件、代价和验证方法；两者都是待验证的备选改法。');
 const comparison=add(e,'div',undefined,'proposal-comparison');add(comparison,'p','共同的决策对象','node-label');add(comparison,'h4',p.decision,'proposal-goal');
 const panels=add(comparison,'div',undefined,'proposal-panels');
 for(const [n,o]of (i.options||[]).entries()){
  const panel=add(panels,'article',undefined,'proposal-panel');
  const head=add(panel,'header');add(head,'span','方案 '+String.fromCharCode(65+n),'proposal-letter');add(head,'h4',o.action);
  const details=add(panel,'dl');for(const [label,content]of [['适用条件',o.conditions],['代价与受影响对象',o.tradeoff],['怎样验证',o.validation_task]]){const row=add(details,'div',undefined,'proposal-row');add(row,'dt',label);add(row,'dd',content)}
 }

 // 06. Priority remains qualitative, connected to the available material and next task.
 const f=mapStep(root,6,'从排序依据走向下一步','这里安排调查和验证顺序，不换算未经测量的上线优先分。'),roadmap=graphBoard(f,'roadmap-map','排序依据与下一步路径图');
 const inputs=add(roadmap.grid,'div',undefined,'graph-three map-wide');
 const impact=graphNode(inputs,'任务影响',p.task_impact,'context'),volume=graphNode(inputs,'材料覆盖',s?`${s.comment_groups}个映射评论组，${s.post_count}条关联帖，${s.source_count}个材料来源；独立人数未知。`:'材料量待核','evidence'),current=graphNode(inputs,'近期适用性',s?`选定时间窗内${s.window_groups}个候选组，近期观察窗${s.recent90_groups}组；设备与版本仍需核对。`:'近期条件待核','check');
 const rank=graphNode(roadmap.grid,'本轮为什么先验证这些',(i.ranking_reasons||[]).join('\n\n'),'result',{className:'map-wide'}),next=graphNode(roadmap.grid,'下一步具体任务',p.next_step,'action',{className:'map-wide'});for(const node of [impact,volume,current])link(roadmap,node,rank);link(roadmap,rank,next);finishMap(roadmap);
 const choose=add(f,'button','选择这项议题的下一步','primary');choose.onclick=()=>goToIssue(i.id,'review');
 if(i.conditions?.length){const boundary=add(root,'details',undefined,'boundary');add(boundary,'summary','完整适用条件与证据缺口');list(boundary,i.conditions)}
}
