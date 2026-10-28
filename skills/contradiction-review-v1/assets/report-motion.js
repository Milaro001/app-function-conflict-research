// View-only motion: gestures move between stable chapter anchors, never change data.
let reportMotion=null;
function revealTitleLetters(node,baseDelay){
 const text=node.textContent;node.replaceChildren();add(node,'span',text,'motion-reader');
 const visible=add(node,'span',undefined,'title-glyphs');visible.setAttribute('aria-hidden','true');
 const letters=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter('zh',{granularity:'grapheme'}).segment(text)].map(x=>x.segment):Array.from(text);
 const step=Math.min(32,1000/Math.max(1,letters.length));letters.forEach((char,index)=>{const glyph=add(visible,'span',char,'title-glyph');glyph.style.setProperty('--glyph-delay',baseDelay+index*step+'ms')});
}
function installReportMotion(content){
 reportMotion?.destroy();const root=document.getElementById('overview-view'),reduce=matchMedia('(prefers-reduced-motion: reduce)');
 const specs=[['.cover-stage','封面'],['#research-charts','研究总览'],['#research-boundary','研究边界'],['#service-framework','服务质量'],['#rice-framework','优先级工作表']];
 const chapters=specs.map(([selector,label])=>{const node=content.querySelector(selector);if(!node)return null;node.classList.remove('scroll-reveal','reveal-ready');node.classList.add('report-chapter');node.dataset.chapterLabel=label;const visual=el('div',undefined,'chapter-visual');while(node.firstChild)visual.append(node.firstChild);node.append(visual);return {node,visual,label}}).filter(Boolean);
 for(const chapter of chapters)for(const node of chapter.node.querySelectorAll('.scroll-reveal'))node.classList.remove('scroll-reveal','reveal-ready');
 const cover=chapters[0]?.node,metrics=document.getElementById('metrics');
 for(const selector of ['.cover-copy h2','.cover-subtitle']){const node=content.querySelector(selector);if(node)revealTitleLetters(node,0)}
 const flow=[...content.querySelectorAll('.cover-description,.cover-metadata>span')];flow.forEach((node,index)=>{node.classList.add('cover-flow-item');node.style.setProperty('--flow-delay',Math.min(800,160+index*85)+'ms')});
 const kicker=content.querySelector('.cover-kicker');kicker?.classList.add('cover-kicker-reveal');const photo=content.querySelector('.cover-photo');photo?.classList.add('cover-photo-reveal');
 [...content.querySelectorAll('.cover-jumps>button')].forEach((node,index)=>{node.classList.add('cover-action-reveal');node.style.setProperty('--action-delay',340+index*70+'ms')});
 [...(metrics?.children||[])].forEach((node,index)=>node.style.setProperty('--metric-delay',560+index*100+'ms'));
 const back=add(root,'button',undefined,'report-return-top');back.hidden=true;back.setAttribute('aria-label','回到页首');const circle=add(back,'span','↑','return-top-circle');circle.setAttribute('aria-hidden','true');add(back,'span','回到页首');
 let frame=0,disposed=false,lastTop=root.scrollTop,direction=1,navigation=null,navTimeout=0,heroRunning=false,lastWheel=0,burstDirection=0,burstTotal=0,burstBlocked=false,burstReading=false,touch=null;
 const gestureGap=340,wheelThreshold=150,chartExitThreshold=240,edgeTolerance=3;
 const clamp=value=>Math.max(0,Math.min(1,value));
 function positions(){const top=root.getBoundingClientRect().top;return chapters.map(chapter=>({top:chapter.node.getBoundingClientRect().top-top+root.scrollTop,height:chapter.node.offsetHeight}))}
 function currentIndex(list=positions()){let index=0;for(let n=0;n<list.length;n++)if(list[n].top<=root.scrollTop+35)index=n;return index}
 function schedule(){if(!frame&&!disposed)frame=requestAnimationFrame(update)}
 function update(){
  frame=0;if(disposed)return;const height=root.clientHeight;root.style.setProperty('--chapter-viewport',height+'px');
  if(!height){cover?.classList.remove('hero-replay');heroRunning=false;metrics?.classList.remove('metrics-ready');return}
  const viewport=root.getBoundingClientRect(),top=root.scrollTop;if(Math.abs(top-lastTop)>1)direction=top>lastTop?1:-1;lastTop=top;root.dataset.scrollDirection=direction>0?'down':'up';
  const points=positions(),active=currentIndex(points);root.dataset.activeChapter=String(active);
  if(navigation&&Math.abs(top-points[navigation.target].top)<2){navigation=null;clearTimeout(navTimeout)}
  chapters.forEach((chapter,index)=>{
   const rect=chapter.node.getBoundingClientRect(),y=rect.top-viewport.top,bottom=y+rect.height,visible=Math.max(0,Math.min(height,bottom)-Math.max(0,y));
   let alpha;if(reduce.matches)alpha=1;else if(visible<=1)alpha=0;else if(y>=0)alpha=clamp((height-y)/(height*.38));else if(rect.height<=height+8)alpha=clamp(1-(-y)/(height*.8));else alpha=clamp(bottom/(height*.65));
   const departing=navigation&&index===navigation.origin&&navigation.origin!==navigation.target;
   if(departing&&!reduce.matches)alpha=0;
   chapter.node.dataset.scene=visible<=1?(bottom<=0?'above':'below'):departing?'departing':'visible';
   const shift=alpha===1?0:(y<0||departing?-44:-26)*(1-alpha),scale=reduce.matches?1:.93+alpha*.07;
   chapter.visual.style.setProperty('--scene-opacity',String(alpha));chapter.visual.style.setProperty('--scene-shift',shift+'px');chapter.visual.style.setProperty('--scene-scale',String(scale));chapter.visual.style.setProperty('--scene-clip',((1-alpha)*(y<0||departing?32:10))+'%');
  });
  if(cover){const r=cover.getBoundingClientRect(),y=r.top-viewport.top,seen=r.bottom>viewport.top+2&&y<height;if(!seen){heroRunning=false;cover.classList.remove('hero-replay')}else if(!heroRunning&&y>=-height*.2){heroRunning=true;cover.classList.add('hero-replay')}}
  if(metrics){const r=metrics.getBoundingClientRect(),seen=r.bottom>viewport.top+8&&r.top<viewport.bottom-8;metrics.classList.toggle('metrics-ready',seen&&(!metrics.closest('.cover-stage')||heroRunning))}
  back.hidden=top<height*.65;back.dataset.chapter=chapters[active]?.label||'';
 }
 function cancelNavigation(){navigation=null;clearTimeout(navTimeout);root.scrollTo({top:root.scrollTop,behavior:'instant'})}
 function go(index){
  if(!chapters.length)return;index=Math.max(0,Math.min(chapters.length-1,index));const points=positions(),origin=currentIndex(points);navigation={origin,target:index,started:performance.now()};hideChartTip();schedule();
  root.scrollTo({top:points[index].top,behavior:reduce.matches?'instant':'smooth'});clearTimeout(navTimeout);navTimeout=setTimeout(()=>{navigation=null;schedule()},1400);
 }
 function goToNode(node){const index=chapters.findIndex(chapter=>chapter.node===node||chapter.node.contains(node));if(index>=0)go(index);else node.scrollIntoView({block:'start',behavior:reduce.matches?'instant':'smooth'})}
 function protectedTarget(target){return target instanceof Element&&!!target.closest('input,textarea,select,[contenteditable="true"],dialog,.diagram-viewport,.table-wrap,.overview-prelude[open]')}
 function canReadInside(index,sign,list){const item=list[index],height=root.clientHeight;if(item.height<=height+8)return false;return sign>0?root.scrollTop<item.top+item.height-height-edgeTolerance:root.scrollTop>item.top+edgeTolerance}
 function onWheel(event){
  if(root.hidden||event.ctrlKey||event.metaKey||event.shiftKey||Math.abs(event.deltaX)>Math.abs(event.deltaY)||protectedTarget(event.target))return;
  const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?root.clientHeight:1);if(Math.abs(delta)<.5)return;const now=performance.now(),sign=Math.sign(delta);
  const list=positions(),index=currentIndex(list),fresh=now-lastWheel>gestureGap||sign!==burstDirection;
  if(fresh){burstTotal=0;burstBlocked=false;burstReading=canReadInside(index,sign,list);if(navigation&&sign!==burstDirection&&now-navigation.started>200)cancelNavigation()}lastWheel=now;burstDirection=sign;
  if(navigation||burstBlocked){event.preventDefault();return}
  if(canReadInside(index,sign,list)){
   burstReading=true;
   const item=list[index],edge=sign>0?item.top+item.height-root.clientHeight:item.top,remaining=Math.abs(edge-root.scrollTop);
   // Finish this chapter's content, then absorb the rest of this gesture's inertia.
   if(Math.abs(delta)>=remaining-edgeTolerance){event.preventDefault();root.scrollTo({top:edge,behavior:'instant'});burstBlocked=true}
   return;
  }
  const next=index+sign;if(next<0||next>=chapters.length)return;
  event.preventDefault();if(burstReading){burstBlocked=true;return}
  burstTotal+=delta;
  const threshold=chapters[index].node.id==='research-charts'?chartExitThreshold:wheelThreshold;
  if(Math.abs(burstTotal)<threshold)return;burstBlocked=true;go(next);
 }
 function onTouchStart(event){if(event.touches.length!==1||protectedTarget(event.target)){touch=null;return}touch={y:event.touches[0].clientY,index:currentIndex(),top:root.scrollTop}}
 function onTouchEnd(event){if(!touch||!event.changedTouches.length)return;const start=touch;touch=null;const distance=start.y-event.changedTouches[0].clientY;if(Math.abs(distance)<100)return;const sign=Math.sign(distance),list=positions();const at={...list[start.index]};if(at.height>root.clientHeight+8||start.index+sign<0||start.index+sign>=list.length)return;go(start.index+sign)}
 function onKey(event){if(root.hidden||protectedTarget(event.target)||event.altKey||event.ctrlKey||event.metaKey)return;let target=null;
  if(event.key==='Home'){target=0}else if(event.key==='PageDown'||event.key==='PageUp'){const sign=event.key==='PageDown'?1:-1,list=positions(),index=currentIndex(list);if(canReadInside(index,sign,list))return;target=index+sign}else return;
  event.preventDefault();go(target);
 }
 function onFocus(event){const chapter=chapters.find(x=>x.node.contains(event.target));if(!chapter)return;const r=event.target.getBoundingClientRect(),v=root.getBoundingClientRect();if(r.bottom<v.top||r.top>v.bottom)goToNode(chapter.node);schedule()}
 const resize=new ResizeObserver(schedule);resize.observe(root);for(const chapter of chapters)resize.observe(chapter.node);
 root.addEventListener('scroll',schedule,{passive:true});root.addEventListener('wheel',onWheel,{passive:false});root.addEventListener('touchstart',onTouchStart,{passive:true});root.addEventListener('touchend',onTouchEnd,{passive:true});document.addEventListener('keydown',onKey);root.addEventListener('focusin',onFocus);root.addEventListener('toggle',schedule,true);reduce.addEventListener('change',schedule);back.onclick=()=>go(0);
 const api={goToNode,go,chapters,destroy(){disposed=true;cancelAnimationFrame(frame);clearTimeout(navTimeout);resize.disconnect();root.removeEventListener('scroll',schedule);root.removeEventListener('wheel',onWheel);root.removeEventListener('touchstart',onTouchStart);root.removeEventListener('touchend',onTouchEnd);document.removeEventListener('keydown',onKey);root.removeEventListener('focusin',onFocus);root.removeEventListener('toggle',schedule,true);reduce.removeEventListener('change',schedule);back.remove()}};
 reportMotion=api;schedule();return api;
}
