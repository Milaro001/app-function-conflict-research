// Observe each reading pane independently. Effects move visual children, keeping
// the module anchors and scroll positions stable while they enter and leave.
let issueScrollCleanup=null;
const issueScrollPreference=matchMedia('(prefers-reduced-motion: reduce)');
function clearIssueScrollMotion(){issueScrollCleanup?.();issueScrollCleanup=null}
function installIssueScrollMotion(){
 clearIssueScrollMotion();
 if(view!=='issues'||issueScrollPreference.matches||!('IntersectionObserver' in window))return;
 const workspace=document.getElementById('issues-view'),cleanups=[];
 function group(root,anchors,visuals){
  if(!root.clientHeight||!anchors.length)return;
  let active=true,lastTop=root.scrollTop,direction=1,exitFrame=0;
  const viewport=root.getBoundingClientRect(),records=new Map();
  const clamp=value=>Math.max(0,Math.min(1,value));
  function updateExits(){
   exitFrame=0;if(!active||workspace.hidden)return;
   const bounds=root.getBoundingClientRect(),updates=[];
   for(const record of records.values()){
    if(record.phase==='pending')continue;
    const rect=record.anchor.getBoundingClientRect(),edge=Math.max(32,Math.min(150,rect.height*.7,root.clientHeight*.22));
    const focused=record.anchor.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select,[contenteditable="true"]');
    const alpha=focused?1:clamp((direction>0?rect.bottom-bounds.top:bounds.bottom-rect.top)/edge);
    updates.push({record,alpha,shift:(direction>0?-24:24)*(1-alpha)});
   }
   for(const {record,alpha,shift}of updates){
    if(alpha>=.999){record.anchor.style.removeProperty('--issue-exit-filter');record.anchor.style.removeProperty('--issue-exit-translate')}
    else{record.anchor.style.setProperty('--issue-exit-filter',`opacity(${alpha})`);record.anchor.style.setProperty('--issue-exit-translate',`0 ${shift}px`)}
   }
  }
  function scheduleExits(){if(!exitFrame&&active)exitFrame=requestAnimationFrame(updateExits)}
  function show(record){
   clearTimeout(record.timer);record.timer=0;record.phase='shown';
   record.anchor.classList.remove('issue-scroll-pending','issue-scroll-revealing');
   record.anchor.style.removeProperty('--issue-scroll-from');record.anchor.style.removeProperty('--issue-scroll-delay');
   scheduleExits();
  }
  function arm(record){
   clearTimeout(record.timer);record.timer=0;record.phase='pending';
   for(const visual of record.visuals)visual.classList.remove('issue-entry-card');
   record.anchor.classList.remove('issue-scroll-revealing');record.anchor.classList.add('issue-scroll-pending');
  }
  function reveal(record,order){
   clearTimeout(record.timer);record.phase='revealing';
   for(const visual of record.visuals)visual.classList.remove('issue-entry-card');
   record.anchor.classList.remove('issue-scroll-pending','issue-scroll-revealing');
   record.anchor.style.removeProperty('--issue-exit-filter');record.anchor.style.removeProperty('--issue-exit-translate');
   record.anchor.style.setProperty('--issue-scroll-from',direction>0?'24px':'-24px');
   const delay=Math.min(order,3)*70;record.anchor.style.setProperty('--issue-scroll-delay',delay+'ms');
   void record.anchor.offsetWidth;record.anchor.classList.add('issue-scroll-revealing');
   record.timer=setTimeout(()=>show(record),520+delay);
   scheduleExits();
  }
  for(const anchor of anchors){
   const rect=anchor.getBoundingClientRect(),record={anchor,visuals:visuals(anchor),timer:0,phase:'shown'};
   records.set(anchor,record);
   for(const visual of record.visuals)visual.classList.add('issue-scroll-surface');
   if(rect.bottom<=viewport.top||rect.top>=viewport.bottom)arm(record);
  }
  const enter=new IntersectionObserver(entries=>{
   if(!active||workspace.hidden)return;
   const ready=entries.filter(entry=>entry.isIntersecting&&records.get(entry.target)?.phase==='pending');
   ready.sort((a,b)=>direction*(a.boundingClientRect.top-b.boundingClientRect.top));
   ready.forEach((entry,index)=>reveal(records.get(entry.target),index));
  },{root,rootMargin:'-8px 0px -16px 0px',threshold:0});
  // Rearm only once a whole card/module has left the viewport by a clear margin.
  const leave=new IntersectionObserver(entries=>{
   if(!active||workspace.hidden)return;
   for(const entry of entries)if(!entry.isIntersecting){const record=records.get(entry.target);if(record.phase!=='pending')arm(record)}
  },{root,rootMargin:'56px 0px 56px 0px',threshold:0});
  const scroll=()=>{const top=root.scrollTop;if(Math.abs(top-lastTop)>.5)direction=top>lastTop?1:-1;lastTop=top;scheduleExits()};
  const focus=event=>{for(const record of records.values())if(record.anchor.contains(event.target)){show(record);break}};
  root.addEventListener('scroll',scroll,{passive:true});root.addEventListener('focusin',focus);
  for(const anchor of anchors){enter.observe(anchor);leave.observe(anchor)}
  cleanups.push(()=>{active=false;cancelAnimationFrame(exitFrame);enter.disconnect();leave.disconnect();root.removeEventListener('scroll',scroll);root.removeEventListener('focusin',focus);for(const record of records.values()){show(record);record.anchor.style.removeProperty('--issue-exit-filter');record.anchor.style.removeProperty('--issue-exit-translate');for(const visual of record.visuals)visual.classList.remove('issue-scroll-surface')}});
 }
 function slot(node,kind){
  if(node.parentElement.classList.contains('issue-scroll-slot'))return node.parentElement;
  const anchor=el('div',undefined,'issue-scroll-slot '+kind);node.before(anchor);anchor.append(node);return anchor;
 }
 group(workspace.querySelector('aside'),[...workspace.querySelectorAll('.issue-reveal-slot')],anchor=>[anchor.querySelector('.issue')]);
 const pane=document.getElementById('content');let anchors=[];
 if(tab==='analysis')anchors=[...pane.querySelectorAll('.map-step')];
 else if(tab==='evidence')anchors=[...pane.querySelectorAll('.evidence')].map(node=>slot(node,'issue-evidence-slot'));
 else if(tab==='issue-data')anchors=[...pane.querySelectorAll('.share-tile,.issue-charts .chart-card')].map(node=>slot(node,'issue-grid-slot'));
 else if(tab==='review')anchors=[...pane.querySelectorAll('.review-step')].map(node=>slot(node,'issue-review-slot'));
 group(pane,anchors,anchor=>anchor.matches('.map-step')?[...anchor.children].filter(node=>node.matches('.step-toggle,.step-body')):[anchor.firstElementChild]);
 const numbers=[...pane.querySelectorAll('.share-tile strong')];
 if(numbers.length){
  const timers=new Map();
  const observer=new IntersectionObserver(entries=>{
   const ready=entries.filter(entry=>entry.isIntersecting&&entry.target.classList.contains('issue-number-pending')).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top||a.boundingClientRect.left-b.boundingClientRect.left);
   for(const entry of entries)if(!entry.isIntersecting){clearTimeout(timers.get(entry.target));entry.target.classList.remove('issue-number-revealing');entry.target.classList.add('issue-number-pending')}
   ready.forEach((entry,index)=>{const node=entry.target;node.classList.remove('issue-number-pending');node.style.setProperty('--issue-number-delay',Math.min(index,3)*60+'ms');node.classList.add('issue-number-revealing');timers.set(node,setTimeout(()=>node.classList.remove('issue-number-revealing'),600+Math.min(index,3)*60))});
  },{root:pane,threshold:0});
  for(const node of numbers){node.classList.add('issue-number-pending');observer.observe(node)}
  cleanups.push(()=>{observer.disconnect();for(const node of numbers){clearTimeout(timers.get(node));node.classList.remove('issue-number-pending','issue-number-revealing');node.style.removeProperty('--issue-number-delay')}});
 }
 issueScrollCleanup=()=>cleanups.forEach(cleanup=>cleanup());
}
issueScrollPreference.addEventListener('change',()=>{clearIssueEntrance();clearIssuePanelEntrance();installIssueScrollMotion()});
let issueScrollResizeFrame=0;
window.addEventListener('resize',()=>{
 if(view!=='issues')return;cancelAnimationFrame(issueScrollResizeFrame);
 issueScrollResizeFrame=requestAnimationFrame(()=>{if(view==='issues')installIssueScrollMotion()});
},{passive:true});
