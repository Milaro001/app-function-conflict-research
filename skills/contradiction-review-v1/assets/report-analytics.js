// Derived, source-backed views for the existing standalone report surface.
// No external scripts, model-generated confidence scores, or network collection.
const qa=report.analytics||null;
const analyticRows=new Map((qa?.records||[]).map(r=>[r.evidence_id,r]));
for(const e of report.evidence){if(e.id.includes(':post:')&&!analyticRows.has(e.id))analyticRows.set(e.id,{...e,evidence_id:e.id,code:'post',kind:'post'})}
const issueStats=new Map((qa?.issue_stats||[]).map(r=>[r.issue_id,r]));
const codeNames={P:'具体问题／改动诉求',V:'功能价值／偏好',C:'辅助背景',U:'待补上下文',G:'非功能内容',E:'事件／评分表态',context_variant:'同文语境不同'};
const seriesTone={P:'var(--red)',V:'var(--green)',C:'var(--muted)',U:'var(--amber)',G:'var(--muted)',E:'var(--amber)',context_variant:'var(--purple)'};
const analyticsDialog=document.getElementById('analytics-dialog');
let inspectedIds=[],inspectedLimit=30,inspectedStanceIssue=null,inspectedServiceDim=null;
function percent(n,d){return d?`${(100*n/d).toFixed(1)}%`:'不适用'}
function evidenceJump(eid){goToIssue(selected,'evidence');const e=[...document.querySelectorAll('[data-evidence-id]')].find(e=>e.dataset.evidenceId===eid);e?.scrollIntoView({block:'start'});e?.focus()}
function qtable(parent,headers,rows,cls=''){
 const wrap=add(parent,'div',undefined,'table-wrap '+cls),t=add(wrap,'table');
 const tr=add(add(t,'thead'),'tr');for(const h of headers)add(tr,'th',h);
 const body=add(t,'tbody');for(const row of rows){const r=add(body,'tr');for(const v of row){const td=add(r,'td');if(v instanceof Node)td.append(v);else td.textContent=v==null?'待核':String(v)}}return t;
}
function renderInspectedRows(){
 const root=document.getElementById('analytics-records');root.replaceChildren();
 const code=document.getElementById('record-code').value;
 const rows=inspectedIds.map(id=>analyticRows.get(id)).filter(r=>r&&(!code||r.code===code));
 const kind=rows.length&&rows.every(r=>r.kind==='post')?'帖子ID':'原始评论ID';document.getElementById('record-count').textContent=`当前显示 ${Math.min(inspectedLimit,rows.length)} / ${rows.length} 条${kind}；同文组与ID数分别计。`;
 qtable(root,['原文与定位','来源／日期','已存语义标注'],rows.slice(0,inspectedLimit).map(r=>{
  const cell=el('div');add(cell,'p',r.body,'record-body');add(cell,'small',r.evidence_id,'muted');
  if(r.source_url){const a=add(cell,'a','来源原文');a.href=r.source_url;a.target='_blank';a.rel='noopener noreferrer'}
  const state=r.kind==='post'?'帖子正文，不计评论数':r.in_scope?'完全符合本轮条件':r.semantic_candidate?'与功能相关，条件仍待核':'辅助／排除／待补证';
  const stance=qa?.issue_stances?.[inspectedStanceIssue]?.find(a=>a.evidence_id===r.evidence_id);
  if(stance){const label=stanceStyles.find(x=>x[0]===stance.stance)?.[1];add(cell,'p',label+' · '+stance.note,'stance-note');for(const a of stance.anchors)add(cell,'small','立场依据：“'+a.text+'”','stance-anchor')}
  const service=qa?.frameworks?.service_quality?.annotations.find(a=>a.evidence_id===r.evidence_id)?.dimensions.find(d=>d.key===inspectedServiceDim);if(service){add(cell,'p',service.reason,'stance-note');add(cell,'small','维度依据：“'+service.anchor+'”','stance-anchor')}
  return [cell,`${sourceNames[r.platform]||r.platform}\n${displayDate(r.published_at)}`,`${r.code==='post'?'帖子正文':codeNames[r.code]||r.code}\n${state}`];
 }));
 if(rows.length>inspectedLimit){const b=add(root,'button','再显示30条');b.onclick=()=>{inspectedLimit+=30;renderInspectedRows()}}
}
function inspectRecords(ids,title,definition,stanceIssue=null,serviceDim=null){
 inspectedServiceDim=serviceDim;
 inspectedStanceIssue=stanceIssue;
 inspectedIds=[...new Set(ids||[])];inspectedLimit=30;
 document.getElementById('analytics-title').textContent=title;
 document.getElementById('analytics-definition').textContent=definition;
 document.getElementById('record-code').value='';renderInspectedRows();analyticsDialog.showModal();
}
document.getElementById('analytics-close').onclick=()=>analyticsDialog.close();
document.getElementById('record-code').onchange=()=>{inspectedLimit=30;renderInspectedRows()};

// Tooltips add detail; totals, units and denominators remain visible without hover.
const chartTip=document.getElementById('chart-tooltip');
function hideChartTip(){chartTip.hidden=true}
function showChartTip(target,title,lines,event){
 chartTip.replaceChildren();add(chartTip,'strong',title);
 for(const row of lines){const line=add(chartTip,'div',undefined,'tip-line');if(row.color){const swatch=add(line,'i');swatch.style.background=row.color}add(line,'span',row.label);if(row.value!==undefined)add(line,'b',row.value)}
 chartTip.hidden=false;const box=target.getBoundingClientRect();
 const x=event?.clientX??box.left+box.width/2,y=event?.clientY??box.bottom;
 chartTip.style.left=Math.max(8,Math.min(innerWidth-chartTip.offsetWidth-8,x+14))+'px';
 chartTip.style.top=Math.max(8,Math.min(innerHeight-chartTip.offsetHeight-8,y+14))+'px';
}
function chartHover(target,title,lines){
 target.addEventListener('pointerenter',e=>showChartTip(target,title,lines,e));target.addEventListener('pointermove',e=>showChartTip(target,title,lines,e));
 target.addEventListener('pointerleave',hideChartTip);target.addEventListener('focus',()=>showChartTip(target,title,lines));target.addEventListener('blur',hideChartTip);
 target.addEventListener('click',hideChartTip);target.addEventListener('keydown',e=>{if(e.key==='Escape')hideChartTip()});
}
document.getElementById('overview-view').addEventListener('scroll',hideChartTip,{passive:true});
document.getElementById('content').addEventListener('scroll',hideChartTip,{passive:true});
window.addEventListener('resize',hideChartTip);
const watchedCharts=new Set();
const chartEntrance=new IntersectionObserver(entries=>{for(const e of entries)e.target.classList.toggle('chart-in',e.isIntersecting)},{threshold:.12});
function watchChart(chart){
 for(const old of watchedCharts)if(!old.isConnected){chartEntrance.unobserve(old);watchedCharts.delete(old)}
 watchedCharts.add(chart);chartEntrance.observe(chart);
}
function chartCard(parent,title,scope){const sec=add(parent,'section',undefined,'quant-section chart-card');add(sec,'h3',title);add(sec,'p',scope,'chart-subtitle');return sec}
function chartLegend(parent,items){const l=add(parent,'div',undefined,'chart-legend');for(const [label,color]of items){const a=add(l,'span');const swatch=add(a,'i');swatch.style.background=color;a.append(document.createTextNode(label))}return l}
function niceMax(value){if(value<=5)return 5;const scale=Math.pow(10,Math.floor(Math.log10(value))),part=value/scale;return [1,2,2.5,5,10].find(n=>n>=part)*scale}
function barChart(parent,rows,{unit='组',denominator=null,definition='',max=null}={}){
 const plot=add(parent,'div',undefined,'bar-chart compact-bars');plot.setAttribute('aria-label','可查看原文的条形图');plot.style.setProperty('--bar-rows',Math.max(1,rows.length));
 const upper=max||niceMax(Math.max(1,...rows.map(r=>r.value)));
 const axis=add(plot,'div',undefined,'bar-axis');for(const n of [0,.2,.4,.6,.8,1])add(axis,'span',String(Number((upper*n).toFixed(2)))+(n===1?' '+unit:''));
 for(const r of rows){
  const row=add(plot,'button',undefined,'bar-row');row.type='button';row.dataset.value=r.value;
  const name=`${r.label}：${count(r.value)}${unit}${denominator?`，占${percent(r.value,denominator)}`:''}`;
  row.setAttribute('aria-label',name+(r.record_ids?.length?'，查看原文':'，无对应原文'));
  add(row,'span',r.label,'bar-label');const track=add(row,'span',undefined,'bar-track');
  const fill=add(track,'span',undefined,'bar-fill chart-grow-x');fill.style.setProperty('--stagger',plot.querySelectorAll('.bar-row').length*55+'ms');fill.style.width=`${r.value/upper*100}%`;fill.style.background=r.color||'var(--chart-blue)';
  add(row,'span',count(r.value),'bar-value');
  chartHover(row,r.label,[{label:'数量',value:count(r.value)+' '+unit,color:r.color||'var(--chart-blue)'},...(denominator?[{label:'本图分母',value:count(denominator)+' '+unit},{label:'占比',value:percent(r.value,denominator)}]:[])]);
  if(r.record_ids?.length)row.onclick=()=>inspectRecords(r.record_ids,name,definition);
 }
 watchChart(plot);return plot;
}
function groupedRows(rows){const groups=new Map();for(const r of rows){if(!r.text_group)continue;if(!groups.has(r.text_group))groups.set(r.text_group,[]);groups.get(r.text_group).push(r)}return groups}
const stanceStyles=[['positive','正向立场','var(--green)'],['negative','负向立场','var(--red)'],['mixed','正负并存','var(--amber)'],['unclear','立场未明','var(--chart-muted)']];
function splitStances(i,s){
 const annotations=qa?.issue_stances?.[i.id];if(!Array.isArray(annotations))return null;
 const byId=new Map(annotations.map(a=>[a.evidence_id,a]));
 const result=Object.fromEntries(stanceStyles.map(([key])=>[key,{value:0,ids:[]}]));
 const rows=(s?.record_ids||[]).map(id=>analyticRows.get(id)).filter(r=>r?.semantic_candidate);
 for(const rs of groupedRows(rows).values()){
  const labels=new Set(rs.map(r=>byId.get(r.evidence_id)?.stance||'unclear'));
  const key=labels.size===1?[...labels][0]:'unclear';result[key].value++;result[key].ids.push(...rs.map(r=>r.evidence_id));
 }return result;
}
function issueComposition(parent){
 const all=report.issues.map(i=>{const s=issueStats.get(i.id);return {i,s,parts:splitStances(i,s)}});
 const annotated=all.some(x=>x.parts),keys=stanceStyles.filter(([key])=>['positive','negative'].includes(key)||all.some(x=>x.parts?.[key].value));
 chartLegend(parent,annotated?keys.map(([,label,color])=>[label,color]):[['尚未标注立场','var(--chart-blue)']]);
 const upper=niceMax(Math.max(1,...all.map(x=>x.s?.semantic_groups||0)));
 const plot=add(parent,'div',undefined,'bar-chart issue-composition');plot.setAttribute('aria-label','议题的正向与负向立场分布');plot.style.setProperty('--issue-rows',Math.max(1,all.length));
 const axis=add(plot,'div',undefined,'bar-axis');for(const n of [0,.2,.4,.6,.8,1])add(axis,'span',String(Number((upper*n).toFixed(2)))+(n===1?' 组':''));
 for(const [index,{i,s,parts}]of all.entries()){
  const total=s?.semantic_groups||0,row=add(plot,'div',undefined,'composition-row');row.dataset.issueId=i.id;
  const label=add(row,'button',qa?.issue_profiles?.[i.id]?.chart_label||i.decision_object,'composition-label');label.title=i.decision_object;label.setAttribute('aria-label',i.decision_object);label.onclick=()=>goToIssue(i.id);
  const track=add(row,'div',undefined,'composition-track'),stack=add(track,'div',undefined,'composition-stack chart-grow-x');stack.style.width=total/upper*100+'%';stack.style.setProperty('--stagger',index*65+'ms');
  const lines=[...(parts?keys.map(([key,label,color])=>({label,value:parts[key].value+' 组',color})):[{label:'尚未标注立场',value:total+' 组'}]),{label:'本议题候选',value:total+' 组'},{label:'另有相关帖子',value:(s?.post_count||0)+' 条'}];chartHover(track,i.decision_object,lines);
  for(const [key,label,color]of parts?stanceStyles:[['unreviewed','尚未标注立场','var(--chart-blue)']]){
   const part=parts?parts[key]:{value:total,ids:s?.record_ids||[]};if(!part.value)continue;
   const seg=add(stack,'button',undefined,'composition-segment');seg.style.width=part.value/total*100+'%';seg.style.background=color;seg.dataset.stance=key;seg.dataset.value=part.value;
   seg.setAttribute('aria-label',`${i.decision_object}，${label}${part.value}组，查看原文`);chartHover(seg,i.decision_object,lines);
   seg.onclick=()=>inspectRecords(part.ids,`${i.decision_object} · ${label}${part.value}组`,'立场针对当前议题独立标注，不由P/V推断。单位为去同文候选组，下钻按评论ID显示；不是人数。',i.id);
  }
  if(!total){stack.remove();add(track,'span',`仅${s?.post_count||0}条关联帖`,'no-comment-mark');chartHover(label,i.decision_object,lines)}
  add(row,'strong',total,'bar-value');
 }
 add(parent,'p',annotated?'按本议题的具体功能另行标注正负立场，AI初审未人工复核；正负并存与立场未明分列。议题可重叠，帖子另计；好评与差评不自动构成冲突。':'尚未逐条标注正负立场，此处只显示候选总数。议题可重叠，帖子另计。','chart-footnote');watchChart(plot);return plot;
}
function monthKey(value){const d=new Date(value);if(!value||Number.isNaN(d.getTime()))return null;const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).formatToParts(d);return parts.find(x=>x.type==='year').value+'-'+parts.find(x=>x.type==='month').value}
function monthlyRows(rows,start,end){
 const buckets=new Map(),lo=new Date(start),hi=new Date(end),first=monthKey(start),last=monthKey(end);if(!first||!last)return [];
 let [y,m]=first.split('-').map(Number);for(let n=0;n<36;n++){const k=`${y}-${String(m).padStart(2,'0')}`;buckets.set(k,{month:k,P:0,V:0,mixed:0,record_ids:[]});if(k===last)break;if(++m===13){m=1;y++}}
 for(const rs of groupedRows(rows.filter(r=>r.semantic_candidate)).values()){
  const dated=rs.filter(r=>r.published_at&&new Date(r.published_at)<=hi&&new Date(r.published_at)>=lo);if(!dated.length)continue;
  const latest=dated.reduce((a,b)=>new Date(a.published_at)>new Date(b.published_at)?a:b),bucket=buckets.get(monthKey(latest.published_at));if(!bucket)continue;
  const codes=new Set(rs.map(r=>r.code)),key=codes.size===1&&codes.has('P')?'P':codes.size===1&&codes.has('V')?'V':'mixed';bucket[key]++;bucket.record_ids.push(...dated.map(r=>r.evidence_id));
 }
 return [...buckets.values()].map(r=>({...r,value:r.P+r.V+r.mixed}));
}
function monthChart(parent,rows,{start,end,total,unit='组',posts=false}={}){
 const data=posts?rows:monthlyRows(rows,start,end);const upper=niceMax(Math.max(1,...data.map(r=>r.value)));
 const frame=add(parent,'div',undefined,'monthly-chart bar-chart');frame.dataset.total=total;frame.setAttribute('aria-label',posts?'关联帖月份分布':'相关反馈月份分布');
 const axis=add(frame,'div',undefined,'month-y');for(const n of [1,.8,.6,.4,.2,0])add(axis,'span',String(Number((upper*n).toFixed(2))));
 const plot=add(frame,'div',undefined,'month-plot');plot.style.setProperty('--months',data.length||1);
 for(const r of data){const b=add(plot,'button',undefined,'month-column');b.dataset.month=r.month;b.dataset.value=r.value;b.setAttribute('aria-label',`${r.month}：${r.value}${unit}，${r.record_ids.length?'查看原文':'无已采材料'}`);
  const area=add(b,'span',undefined,'month-area'),stack=add(area,'span',undefined,'month-stack chart-grow-y');stack.style.setProperty('--stagger',plot.querySelectorAll('.month-column').length*35+'ms');stack.style.height=r.value/upper*100+'%';
  const fill=add(stack,'span');fill.style.height='100%';fill.style.background='var(--chart-blue)';
  if(r.value)add(stack,'b',r.value,'month-total');
  const tick=add(b,'span',r.month.slice(5),'month-tick');if(r.month.endsWith('-01'))tick.textContent=r.month.slice(2,4)+'/01';
  chartHover(b,r.month,[{label:'合计',value:r.value+' '+unit},{label:'本图分母',value:total+' '+unit},{label:'占比',value:percent(r.value,total)}]);
  if(r.record_ids.length)b.onclick=()=>inspectRecords(r.record_ids,r.month+' · '+r.value+unit,'按已采材料发布时间分月；这是样本出现月份，不代表总体需求趋势。');
 }
 add(parent,'p',`${data[0]?.month||'时间待核'} — ${data.at(-1)?.month||'时间待核'} · ${total}${unit}。首尾月可能不完整；样本分布不代表需求升降。`,'chart-footnote');watchChart(frame);return frame;
}
function stageFlow(root){
 const flow=add(root,'div',undefined,'screening-flow');flow.setAttribute('aria-label','语义筛选各阶段');
 for(const [n,r]of qa.screening.entries()){const b=add(flow,'button',undefined,'screening-node');add(b,'span',String(n+1).padStart(2,'0'),'screening-index');add(b,'strong',count(r.value));add(b,'span',r.label);chartHover(b,r.label,[{label:'数量',value:r.value+' 组'},{label:'计数口径',value:'去同文组'}]);if(r.record_ids.length)b.onclick=()=>inspectRecords(r.record_ids,r.label+' · '+r.value+'组','原始评论ID另计；此处按非纯符号同文组逐步筛选。')}
 return flow;
}
function drawOverview(root){
 const intro=drawReportCover(root),dataArea=add(root,'section',undefined,'overview-data-area');dataArea.id='research-charts';dataArea.dataset.density='compact';const dataHeading=add(dataArea,'div',undefined,'data-heading');const headingCopy=add(dataHeading,'div');add(headingCopy,'p','反馈与样本分布','eyebrow');add(headingCopy,'h2','研究总览');
 const actions=add(dataHeading,'div',undefined,'overview-chart-actions');const density=add(actions,'button','展开图表');density.setAttribute('aria-expanded','false');density.onclick=()=>{const expanded=dataArea.dataset.density==='compact';dataArea.dataset.density=expanded?'expanded':'compact';density.textContent=expanded?'收紧图表':'展开图表';density.setAttribute('aria-expanded',String(expanded));window.dispatchEvent(new Event('resize'))};const topicEntry=add(actions,'button',`查看${report.issues.length}个功能议题`,'primary');topicEntry.disabled=!report.issues.length;topicEntry.onclick=()=>showView('issues');
 add(intro,'p',report.app+' · 全局研究总览','eyebrow');
 const title=add(intro,'div',undefined,'overview-title-row');add(title,'h2','本轮材料与功能议题');const enter=add(title,'button',`查看${report.issues.length}个功能议题`,'primary');enter.disabled=!report.issues.length;enter.onclick=()=>showView('issues');
 if(!qa){add(root,'p','当前报告没有逐条量化输入，现有原文与议题仍可查看。');installReportMotion(root);return}
 const m=qa.metrics,summary=add(intro,'div',undefined,'overview-reading');
 if(report.issues[0]){add(summary,'span','当前首先验证','node-label');add(summary,'strong',report.issues[0].title)}
 add(summary,'p',`${m.raw_comment_ids}条评论ID → ${m.text_groups}条去重后反馈 → ${m.semantic_groups}条与功能相关，占比${percent(m.retention_numerator,m.retention_denominator)}。${m.window_groups}组位于选定时间窗；范围合格数为 ${m.qualified_groups}，未知条件保留待核。`);
 stageFlow(intro);
 const grid=add(dataArea,'div',undefined,'chart-grid overview-charts');
 const a=chartCard(grid,'功能议题 × 正负立场',`单位：去同文候选组 · 全局候选${m.semantic_groups}组`);issueComposition(a);
 const b=chartCard(grid,'近一年相关反馈的月份分布',`单位：去重后的反馈条数 · 时间窗内${m.window_groups}条`);monthChart(b,qa.records,{start:qa.scope.start,end:qa.scope.end,total:m.window_groups});
 const c=chartCard(grid,'信源平台分布',`单位：评论ID · 分母${m.raw_comment_ids}条`);c.classList.add('source-overview');barChart(c,qa.source_counts.map(r=>({...r,label:sourceNames[r.platform]||r.platform})),{unit:'条',denominator:m.raw_comment_ids,definition:'按来源与评论ID计数，尚未按同文去重；不代表各平台用户占比。'});add(c,'p','悬停查看数量和占比；点击条形可查原文。','chart-footnote');
 for(const card of grid.children)revealSection(card);
 const foot=add(intro,'div',undefined,'time-summary');for(const r of qa.time_counts){const b=add(foot,'button',undefined,'time-chip');add(b,'strong',r.value);add(b,'span',r.label);chartHover(b,r.label,[{label:'数量',value:r.value+' 组'},{label:'全部候选',value:m.semantic_groups+' 组'},{label:'占比',value:percent(r.value,m.semantic_groups)}]);if(r.record_ids.length)b.onclick=()=>inspectRecords(r.record_ids,r.label+' · '+r.value+'组',qa.definitions.time)}
 drawFrameworks(root);
 const boundary=add(root,'section',undefined,'research-boundary');boundary.id='research-boundary';const prelude=add(boundary,'details',undefined,'overview-prelude');add(prelude,'summary','本轮研究概览与筛选过程');prelude.append(intro);add(boundary,'p','如何理解这轮研究','eyebrow');add(boundary,'h2','计数、时间口径与研究边界');const detail=add(boundary,'div',undefined,'boundary definitions');for(const v of Object.values(qa.definitions))add(detail,'p',v);add(detail,'p','标注是AI初筛，数量复算不等于独立人工准确率测试。');const frameworks=root.querySelector('.frameworks-container');if(frameworks)root.insertBefore(boundary,frameworks);installReportMotion(root);
}
function drawIssueData(root,i){
 const s=issueStats.get(i.id);if(!qa||!s){add(root,'p','当前议题尚未提供逐条量化映射。');return}
 const rs=s.record_ids.map(id=>analyticRows.get(id)).filter(Boolean),recent=qa.time_counts.find(r=>r.key==='recent90')?.value;
 const tiles=add(root,'div',undefined,'share-grid');
 for(const [label,n,d]of [['全部候选中的占比',s.semantic_groups,qa.metrics.semantic_groups],['时间窗内的占比',s.window_groups,qa.metrics.window_groups],['近期观察窗内的占比',s.recent90_groups,recent],['完全符合本轮条件',s.qualified_groups,qa.metrics.qualified_groups]]){
  const t=add(tiles,'div',undefined,'share-tile');add(t,'span',label);add(t,'strong',rs.length?percent(n,d):'暂无映射评论');add(t,'small',`${n} / ${d} 组`);
 }
 add(root,'p',rs.length?`${s.comment_groups}个映射评论组来自${s.comment_ids}条评论ID；另有${s.post_count}条关联帖。议题可重叠，以上占比不相加为100%，独立人数未知。`:`本议题只有${s.post_count}条关联帖，没有映射评论，暂不计算评论占比。`,'chart-footnote');
 const grid=add(root,'div',undefined,'chart-grid issue-charts'),material=rs.length?rs:s.post_ids.map(id=>analyticRows.get(id)).filter(Boolean),sourceMap=new Map();
 for(const r of material){if(!sourceMap.has(r.platform))sourceMap.set(r.platform,[]);sourceMap.get(r.platform).push(r.evidence_id)}
 const source=chartCard(grid,rs.length?'本议题的评论来源':'本议题的帖子来源',`分母：${material.length}${rs.length?'条评论ID':'条帖子'}`);
 barChart(source,[...sourceMap].map(([platform,ids])=>({label:sourceNames[platform]||platform,value:ids.length,record_ids:ids})),{unit:rs.length?'条评论ID':'条帖子',denominator:material.length,definition:'只统计当前议题的映射材料，不是整轮来源分布。'});
 if(rs.length){const time=chartCard(grid,'本议题候选出现的月份',`单位：同文候选组 · 选定时间窗内${s.window_groups}组`);monthChart(time,rs,{start:qa.scope.start,end:qa.scope.end,total:s.window_groups})}
 else {const time=chartCard(grid,'关联帖子出现的月份','单位：帖子；与评论分开计数');const groups=new Map();for(const r of material){const month=monthKey(r.published_at);if(!month)continue;if(!groups.has(month))groups.set(month,{month,value:0,record_ids:[]});const a=groups.get(month);a.value++;a.record_ids.push(r.evidence_id)}monthChart(time,[...groups.values()].sort((a,b)=>a.month.localeCompare(b.month)),{total:material.length,unit:'帖',posts:true})}
 const button=add(root,'button','查看本议题原文证据','primary');button.onclick=()=>goToIssue(i.id,'evidence');
}
function drawReasoning(root,i){const p=qa?.issue_profiles?.[i.id];if(i.insight){drawInsightMaps(root,i,p,issueStats.get(i.id));return true}if(!p)return false;drawReasonMaps(root,i,p,issueStats.get(i.id));return true}
