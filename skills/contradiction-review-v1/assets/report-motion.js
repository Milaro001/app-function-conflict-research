// Three page states; the original scene effects play while the viewport moves between them.
let reportMotion=null;
function revealTitleLetters(node,baseDelay){
 const text=node.textContent;node.replaceChildren();add(node,'span',text,'motion-reader');
 const visible=add(node,'span',undefined,'title-glyphs');visible.setAttribute('aria-hidden','true');
 const letters=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter('zh',{granularity:'grapheme'}).segment(text)].map(x=>x.segment):Array.from(text);
 const step=Math.min(32,1000/Math.max(1,letters.length));letters.forEach((char,index)=>{const glyph=add(visible,'span',char,'title-glyph');glyph.style.setProperty('--glyph-delay',baseDelay+index*step+'ms')});
}
function installReportMotion(content){
 reportMotion?.destroy();const root=document.getElementById('overview-view'),reduce=matchMedia('(prefers-reduced-motion: reduce)');
 const specs=[['.cover-stage','封面'],['#research-charts','研究总览'],['#research-boundary','研究边界']];
 const chapters=specs.map(([selector,label])=>{const node=content.querySelector(selector);if(!node)return null;node.classList.remove('scroll-reveal','reveal-ready');node.classList.add('report-chapter');node.dataset.chapterLabel=label;const visual=el('div',undefined,'chapter-visual');while(node.firstChild)visual.append(node.firstChild);node.append(visual);return {node,visual,label}}).filter(Boolean);
 const extra=content.querySelector('.frameworks-container');if(extra){if(extra.children.length&&chapters[2])chapters[2].visual.append(extra);else if(!extra.children.length)extra.remove()}
 root.classList.add('three-stop-overview');root.dataset.scrollMode='three_stops_original_motion';
 for(const [index,chapter]of chapters.entries()){const stop=el('section',undefined,'overview-stop');chapter.node.before(stop);stop.append(chapter.node);chapter.stop=stop;stop.dataset.page=String(index);stop.setAttribute('role','group');stop.setAttribute('aria-label',`${chapter.label}，第${index+1}页，共${chapters.length}页`)}
 for(const chapter of chapters)for(const node of chapter.node.querySelectorAll('.scroll-reveal'))node.classList.remove('scroll-reveal','reveal-ready');
 const cover=chapters[0]?.node,metrics=document.getElementById('metrics');
 for(const selector of ['.cover-copy h2','.cover-subtitle']){const node=content.querySelector(selector);if(node)revealTitleLetters(node,0)}
 const flow=[...content.querySelectorAll('.cover-description,.cover-metadata>span')];flow.forEach((node,index)=>{node.classList.add('cover-flow-item');node.style.setProperty('--flow-delay',Math.min(800,160+index*85)+'ms')});
 const kicker=content.querySelector('.cover-kicker');kicker?.classList.add('cover-kicker-reveal');const photo=content.querySelector('.cover-photo');photo?.classList.add('cover-photo-reveal');
 [...content.querySelectorAll('.cover-jumps>button')].forEach((node,index)=>{node.classList.add('cover-action-reveal');node.style.setProperty('--action-delay',340+index*70+'ms')});
 [...(metrics?.children||[])].forEach((node,index)=>node.style.setProperty('--metric-delay',560+index*100+'ms'));
 const back=add(root,'button',undefined,'report-return-top');back.hidden=true;back.setAttribute('aria-label','回到页首');const circle=add(back,'span','↑','return-top-circle');circle.setAttribute('aria-hidden','true');add(back,'span','回到页首');
 let frame=0,disposed=false,lastTop=root.scrollTop,direction=1,navigation=null,motionFrame=0,heroRunning=false,current=0,touch=null;
 let gesture={lastAt:-Infinity,startAt:0,direction:0,previous:0,peak:0,consumed:false};
 const clamp=value=>Math.max(0,Math.min(1,value));
 function positions(){const top=root.getBoundingClientRect().top;return chapters.map(chapter=>({top:chapter.stop.getBoundingClientRect().top-top+root.scrollTop,height:chapter.stop.offsetHeight}))}
 function currentIndex(){return current}
 function schedule(){if(!frame&&!disposed)frame=requestAnimationFrame(update)}
 function update(){
  frame=0;if(disposed)return;const height=root.clientHeight;root.style.setProperty('--chapter-viewport',height+'px');
  if(!height){cover?.classList.remove('hero-replay');heroRunning=false;metrics?.classList.remove('metrics-ready');return}
  const viewport=root.getBoundingClientRect(),top=root.scrollTop;if(Math.abs(top-lastTop)>1)direction=top>lastTop?1:-1;lastTop=top;root.dataset.scrollDirection=direction>0?'down':'up';
  const points=positions(),active=currentIndex(points);root.dataset.activeChapter=String(active);
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
 function cancelNavigation(){cancelAnimationFrame(motionFrame);motionFrame=0;navigation=null;root.dataset.transitioning='false'}
 function paintSelection(){
  root.dataset.activePage=String(current);root.dataset.activeChapter=String(current);
  chapters.forEach((chapter,index)=>{const active=index===current;chapter.stop.inert=!active;chapter.stop.setAttribute('aria-hidden',String(!active))});
 }
 function go(index,fromGesture=false){
  if(!chapters.length)return;
  if(!fromGesture)gesture={lastAt:-Infinity,startAt:0,direction:0,previous:0,peak:0,consumed:false};
  index=Math.max(0,Math.min(chapters.length-1,index));const origin=current;current=index;cancelNavigation();chapters[index].node.scrollTop=0;paintSelection();
  if(root.hidden||!root.clientHeight)return;
  const start=root.scrollTop,end=positions()[index].top,distance=end-start;
  if(Math.abs(distance)<.5){root.scrollTo({top:end,behavior:'instant'});schedule();return}
  navigation={origin,target:index,started:performance.now()};root.dataset.transitioning=String(!reduce.matches);hideChartTip();schedule();
  const duration=reduce.matches?0:Math.max(200,Math.min(520,200+Math.abs(distance)/root.clientHeight*320));
  function step(now){
   if(disposed||!navigation)return;
   if(root.hidden){cancelNavigation();return}
   const progress=duration?clamp((now-navigation.started)/duration):1,eased=1-Math.pow(1-progress,3);
   root.scrollTo({top:start+distance*eased,behavior:'instant'});schedule();
   if(progress<1)motionFrame=requestAnimationFrame(step);
   else{motionFrame=0;navigation=null;root.dataset.transitioning='false';schedule()}
  }
  motionFrame=requestAnimationFrame(step);
 }
 function goToNode(node){const index=chapters.findIndex(chapter=>chapter.node===node||chapter.node.contains(node));if(index<0)return;go(index);const chapter=chapters[index];if(node!==chapter.node){let top=0,part=node;while(part&&part!==chapter.node){top+=part.offsetTop;part=part.offsetParent}chapter.node.scrollTo({top,behavior:'instant'})}}
 function protectedTarget(target){return target instanceof Element&&!!target.closest('input,textarea,select,[contenteditable="true"],dialog,.diagram-viewport')}
 function onWheel(event){
  if(root.hidden||event.ctrlKey||event.metaKey||event.shiftKey||Math.abs(event.deltaX)>Math.abs(event.deltaY)||protectedTarget(event.target))return;
  const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?root.clientHeight:1),magnitude=Math.abs(delta),sign=Math.sign(delta),now=performance.now(),gap=now-gesture.lastAt;
  if(!sign)return;event.preventDefault();
  if(magnitude<.5){gesture.lastAt=now;gesture.previous=magnitude;return}
  const reverse=sign!==gesture.direction;
  const mouseStep=gap>=70&&(event.deltaMode!==0||(magnitude>=40&&Math.abs(magnitude-gesture.previous)<.01));
  const renewed=now-gesture.startAt>160&&((magnitude>=2&&gesture.previous<=1)||(magnitude>=8&&magnitude>gesture.previous*1.8&&gesture.previous<gesture.peak*.6));
  const fresh=gap>120||reverse||mouseStep||renewed;
  if(fresh)gesture={lastAt:now,startAt:now,direction:sign,previous:magnitude,peak:magnitude,consumed:false};
  else{gesture.lastAt=now;gesture.previous=magnitude;gesture.peak=Math.max(gesture.peak,magnitude)}
  if(gesture.consumed)return;
  // The very first light input selects one adjacent page. No native partial scroll.
  gesture.consumed=true;go(current+sign,true);
 }
 function onTouchStart(event){if(event.touches.length!==1||protectedTarget(event.target)){touch=null;return}touch={y:event.touches[0].clientY,total:0,direction:0,reverseDistance:0}}
 function onTouchMove(event){
  if(!touch||event.touches.length!==1)return;event.preventDefault();
  const y=event.touches[0].clientY,delta=touch.y-y;touch.y=y;touch.total+=delta;
  if(!touch.direction){if(Math.abs(touch.total)<4)return;touch.direction=Math.sign(touch.total);go(current+touch.direction);return}
  if(Math.sign(delta)===touch.direction){touch.reverseDistance=0;return}
  touch.reverseDistance+=Math.abs(delta);
  if(touch.reverseDistance>=4){touch.direction=-touch.direction;touch.reverseDistance=0;go(current+touch.direction)}
 }
 function onTouchEnd(){touch=null}
 function onKey(event){
  if(root.hidden||protectedTarget(event.target)||event.altKey||event.ctrlKey||event.metaKey)return;let target;
  if(event.key==='Home')target=0;else if(event.key==='End')target=chapters.length-1;
  else if(event.key==='PageDown'||event.key==='ArrowDown'||event.key===' '&&!event.shiftKey)target=current+1;
  else if(event.key==='PageUp'||event.key==='ArrowUp'||event.key===' '&&event.shiftKey)target=current-1;else return;
  if((event.key===' '||event.key.startsWith('Arrow'))&&event.target.closest?.('button,a,[role="button"],summary'))return;
  event.preventDefault();go(target);
 }
 function onFocus(event){const index=chapters.findIndex(chapter=>chapter.node.contains(event.target));if(index>=0&&index!==current)go(index);schedule()}
 function onScroll(){
  // Scrollbars, focus and browser defaults cannot leave the outer view between pages.
  if(!navigation&&!root.hidden&&root.clientHeight){const top=positions()[current]?.top;if(top!==undefined&&Math.abs(root.scrollTop-top)>.5)root.scrollTo({top,behavior:'instant'})}
  schedule();
 }
 function onResize(){
  cancelNavigation();if(!root.hidden&&root.clientHeight){
   root.style.setProperty('--chapter-viewport',root.clientHeight+'px');root.style.setProperty('--cover-visual-width',Math.max(230,(root.clientHeight-324)*9/8)+'px');root.dataset.pageFit='original';
   if(cover){cover.dataset.bottomTrim='false';const overflow=cover.scrollHeight-cover.clientHeight;if(root.clientWidth>760&&overflow>2&&overflow<=32)cover.dataset.bottomTrim='true'}
   if(root.clientWidth>760&&chapters.some(chapter=>chapter.node.scrollHeight>chapter.node.clientHeight+2||chapter.visual.scrollHeight>chapter.visual.clientHeight+2))root.dataset.pageFit='compact';
   root.scrollTo({top:positions()[current]?.top||0,behavior:'instant'});
  }schedule();
 }
 const resize=new ResizeObserver(onResize);resize.observe(root);
 for(const chapter of chapters)chapter.node.addEventListener('scroll',schedule,{passive:true});
 root.addEventListener('scroll',onScroll,{passive:true});root.addEventListener('wheel',onWheel,{passive:false});root.addEventListener('touchstart',onTouchStart,{passive:true});root.addEventListener('touchmove',onTouchMove,{passive:false});root.addEventListener('touchend',onTouchEnd,{passive:true});root.addEventListener('touchcancel',onTouchEnd,{passive:true});document.addEventListener('keydown',onKey);root.addEventListener('focusin',onFocus);reduce.addEventListener('change',onResize);back.onclick=()=>go(0);
 const api={goToNode,go,chapters,get current(){return current},destroy(){disposed=true;cancelAnimationFrame(frame);cancelNavigation();resize.disconnect();for(const chapter of chapters)chapter.node.removeEventListener('scroll',schedule);root.removeEventListener('scroll',onScroll);root.removeEventListener('wheel',onWheel);root.removeEventListener('touchstart',onTouchStart);root.removeEventListener('touchmove',onTouchMove);root.removeEventListener('touchend',onTouchEnd);root.removeEventListener('touchcancel',onTouchEnd);document.removeEventListener('keydown',onKey);root.removeEventListener('focusin',onFocus);reduce.removeEventListener('change',onResize);back.remove();root.classList.remove('three-stop-overview')}};
 reportMotion=api;paintSelection();onResize();return api;
}
