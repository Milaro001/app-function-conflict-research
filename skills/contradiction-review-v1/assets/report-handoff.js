const g2Choices=[['unreviewed','暂未判断'],['approve','分析与原文一致'],['limited','基本成立，需要补充适用条件'],['supplement','材料不足，请继续补采'],['recode','理解有误，请重新分析'],['presentation','请改进页面和文字表达']];
const g3Choices=[['unreviewed','暂未选择'],['adopt','整理成具体设计任务'],['test','先做原型或验证'],['supplement','继续补采相关反馈'],['defer','先暂缓这个问题'],['rework','重新比较改法']];
const deliveryFormats={pptx:'PPT（.pptx，推荐）',docx:'Word（.docx，适合审阅）',xlsx:'表格（.xlsx，适合分工与跟踪）',html:'交互原型网页（附验证计划）'};
const platformNames={appbao:'应用宝',appstore:'App Store',xhs:'小红书',wb:'微博',zhihu:'知乎',bili:'B站',douyin:'抖音',web:'公开网页'};
const draftKey=storageKey+':drafts';let drafts={};
try{drafts=JSON.parse(localStorage.getItem(draftKey)||'{}');if(!drafts||typeof drafts!=='object'||Array.isArray(drafts))drafts={}}catch(_){}
const returnUrl=report.handoff?.conversation_url||'';
const pasteKeys=/Mac/i.test(navigator.platform)?'⌘V':'Ctrl+V';
const bridge={ready:false,token:null,canSubmit:false};let refreshHandoff=null;
let submitted={};try{submitted=JSON.parse(localStorage.getItem(storageKey+':submitted')||'{}')}catch(_){}
function resetReviewDock(){refreshHandoff=null;const dock=document.getElementById('review-dock');dock.replaceChildren();dock.hidden=true}
async function connectBridge(){
 if(!report.handoff?.local_bridge||!['127.0.0.1','localhost'].includes(location.hostname))return;
 try{const r=await fetch('/api/session',{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!r.ok)return;const d=await r.json();if(d.conversation_url===returnUrl&&typeof d.token==='string'){bridge.ready=true;bridge.token=d.token;bridge.canSubmit=d.submit_available===true;refreshHandoff?.()}}catch(_){}
}
connectBridge();
async function bridgeRequest(path,extra={}){
 if(!bridge.ready)throw new Error('bridge unavailable');
 const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:bridge.token,...extra}),signal:AbortSignal.timeout(path==='/api/submit'?35000:6000)});
 const value=await r.json();if(!r.ok){const error=new Error('local action unavailable');error.code=value.error;throw error}return value;
}
async function copyFeedback(text){
 if(bridge.ready){try{const r=await bridgeRequest('/api/clipboard',{text});if(r.copied)return 'local_clipboard'}catch(_){}}
 if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(text);return 'browser_clipboard'}catch(_){}}
 // A real copy command, rather than merely selecting text as in the old page.
 const area=el('textarea');area.value=text;area.style.cssText='position:fixed;left:-10000px;top:0';document.body.append(area);area.focus();area.select();
 let copied=false;try{copied=document.execCommand('copy')}catch(_){}area.remove();
 return copied?'copy_command':null;
}
function effectiveAction(d){return d.g3&&d.g3!=='unreviewed'?d.g3:d.g2==='supplement'?'supplement':d.g2==='presentation'?'presentation':d.g2==='recode'?'recode':null}
function nextSteps(g2,g3,details={}){
 const steps=[];const evidence={approve:'保留当前解释，并按你选择的行动继续。',limited:'根据你的说明补充适用条件，再更新结论。',supplement:'补采该议题的相关帖子、评论和缺失上下文，再更新证据。',recode:'重新阅读相关原文，修正问题归类与解释，再更新分析。',presentation:'调整信息顺序、文字与页面，再交付你复查。'};
 if(evidence[g2])steps.push(evidence[g2]);
 const fmt=details.delivery_format||'pptx';
 if(g3==='adopt')steps.push('制作'+(deliveryFormats[fmt]||'PPT')+'设计任务稿，写清问题证据、设计目标、任务拆解、依赖和验收方法。');
 if(g3==='test')steps.push(fmt==='html'?'制作可点击网页原型，并附测试任务、招募条件和评价方法。':'制作'+(deliveryFormats[fmt]||'PPT')+'原型与验证方案，展示关键流程、界面设想、测试任务和评价方法。');
 if(g3==='supplement')steps.push('按选定范围补采相关反馈，并更新来源覆盖与语义筛选结果。');
 if(g3==='defer')steps.push('将该议题保留在观察区，本轮先不推进设计。');
 if(g3==='rework')steps.push('重新比较替代方案、适用场景和代价，再给出选择建议。');
 if(details.delivery_audience)steps.push('交付面向：'+details.delivery_audience+'。');
 if(details.action_focus)steps.push('重点处理：'+details.action_focus);
 if(details.platforms?.length)steps.push('优先补采来源：'+details.platforms.map(p=>platformNames[p]||p).join('、')+'。');
 return [...new Set(steps)];
}
function feedbackText(records=decisions){
 const lines=['请继续处理这份'+report.app+'功能调研反馈。','报告编号：'+report.bundle_id];
 for(const [id,d] of Object.entries(records)){
  const issue=report.issues.find(i=>i.id===id);if(!issue)continue;
  lines.push('\n决策对象：'+issue.decision_object,'议题编号：'+id,'报告当前结论：'+issue.title,
   '我对分析的判断：'+(g2Choices.find(x=>x[0]===d.g2)?.[1]||'暂未判断'),
   '我选择的下一步：'+(g3Choices.find(x=>x[0]===d.g3)?.[1]||'暂未选择'));
  if(d.delivery_format)lines.push('我选择的交付形式：'+deliveryFormats[d.delivery_format]);
  if(d.delivery_audience)lines.push('使用对象／场合：'+d.delivery_audience);
  if(d.action_focus)lines.push('重点范围：'+d.action_focus);
  if(d.platforms?.length)lines.push('优先来源：'+d.platforms.map(p=>platformNames[p]||p).join('、'));
  if(d.reason)lines.push('我的补充说明：'+d.reason);
  lines.push(...nextSteps(d.g2,d.g3,d).map(x=>'待处理：'+x),'关联证据：'+[...new Set(issue.anchors.map(a=>a.evidence_id))].join('、'));
 }
 return lines.join('\n');
}
function drawReview(root,i){
 const portableMode=!report.handoff?.local_bridge;
 const intro=add(root,'div',undefined,'review-intro');add(intro,'strong',portableMode?'选择下一步与交付形式，导出可交给Agent继续处理的任务文件。':'选好下一步和交付形式，点击发送后我会在本次对话继续处理。');
 add(intro,'p','选择“设计任务”或“原型与验证”后，请选择交付形式。默认推荐PPT，你可以改为Word或表格。');
 add(intro,'p',portableMode?'当前网页没有配置对话接收器。导出文件后，在支持的Agent中附上文件并要求继续；导出本身不会自动制作交付物。':'发送会把当前议题、所选行动、文件形式和补充要求直接交给本次对话。你可以留在页面阅读，后续结果会在对话中交付。');
 const saved=drafts[i.id]||decisions[i.id]||{},form=add(root,'div',undefined,'form');
 const step1=add(form,'section',undefined,'review-step');add(step1,'h3','1. 你认为分析是否准确？');
 const g2Label=add(step1,'label','对当前分析的判断'),g2=add(g2Label,'select');g2.setAttribute('aria-label','分析判断');
 for(const [v,t] of g2Choices){const o=add(g2,'option',t);o.value=v}g2.value=saved.g2||'unreviewed';
 const step2=add(form,'section',undefined,'review-step');add(step2,'h3','2. 你希望下一步做什么？');
 const g3Label=add(step2,'label','下一步行动'),g3=add(g3Label,'select');g3.setAttribute('aria-label','下一步行动');
 for(const [v,t] of g3Choices){const o=add(g3,'option',t);o.value=v}g3.value=saved.g3||'unreviewed';
 const delivery=add(step2,'fieldset',undefined,'delivery-box');delivery.setAttribute('aria-label','交付形式设置');add(delivery,'legend','你希望以什么形式交付？');
 const formatLabel=add(delivery,'label','交付形式'),format=add(formatLabel,'select');format.setAttribute('aria-label','交付形式');
 for(const [v,t] of Object.entries(deliveryFormats)){const o=add(format,'option',t);o.value=v}format.value=saved.delivery_format||'pptx';
 const formatHelp=add(delivery,'p',undefined,'muted');
 const audienceLabel=add(delivery,'label','给谁看，或用于什么场合？（选填）'),audience=add(audienceLabel,'input');audience.setAttribute('aria-label','交付对象与场合');audience.placeholder='例如：向负责人汇报、设计评审、逐条审阅';audience.value=saved.delivery_audience||'';
 const focusBox=add(step2,'section',undefined,'action-box');const focusLabel=add(focusBox,'label'),focus=add(focusLabel,'textarea');focus.setAttribute('aria-label','下一步重点范围');focus.value=saved.action_focus||'';
 const platforms=add(focusBox,'div',undefined,'platform-options');platforms.setAttribute('aria-label','优先补采平台');const platformInputs=[];
 for(const [id,name] of Object.entries(platformNames)){const label=add(platforms,'label');const input=add(label,'input');input.type='checkbox';input.value=id;input.checked=(saved.platforms||[]).includes(id);label.append(document.createTextNode(name));platformInputs.push(input)}
 const reasonLabel=add(form,'label','你希望我纠正、补充或保留什么？（选填）'),reason=add(reasonLabel,'textarea');reason.setAttribute('aria-label','反馈说明');reason.placeholder='例如：保留这个设计目标，但先比较两种方案，不要直接更改默认设置。';reason.value=saved.reason||'';
 const next=add(form,'div',undefined,'next-step');
 const preview=add(form,'details');add(preview,'summary','预览本次任务内容与备份','feedback-summary');const previewText=add(preview,'textarea',undefined,'feedback-full');previewText.readOnly=true;previewText.setAttribute('aria-label','本次任务内容预览');
 const aux=add(preview,'div',undefined,'handoff-secondary');const dock=document.getElementById('review-dock');dock.hidden=false;const actions=add(dock,'div',undefined,'handoff-actions');
 const send=add(actions,'button','发送并开始后续任务','primary');
 const back=returnUrl?add(actions,'a','查看本次对话'):null;if(back){back.href=returnUrl;back.setAttribute('aria-label','查看本次对话')}
 const save=add(aux,'button','保存草稿');const copy=add(aux,'button','复制备份');const exp=add(aux,'button','导出已保存反馈');
 const status=add(dock,'div','正在连接本次对话…','copy-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 let busy=false;
 function capture(){const action=g3.value;return {g2:g2.value,g3:action,reason:reason.value.trim(),delivery_format:['adopt','test'].includes(action)?format.value:null,delivery_audience:['adopt','test'].includes(action)?audience.value.trim():'',action_focus:['supplement','rework'].includes(effectiveAction({g2:g2.value,g3:action}))?focus.value.trim():'',platforms:effectiveAction({g2:g2.value,g3:action})==='supplement'?platformInputs.filter(e=>e.checked).map(e=>e.value):[]}}
 function update(){
  const action=effectiveAction({g2:g2.value,g3:g3.value});delivery.hidden=!['adopt','test'].includes(g3.value);
  const htmlOption=format.querySelector('[value=html]');htmlOption.disabled=g3.value!=='test';htmlOption.hidden=g3.value!=='test';if(format.value==='html'&&g3.value!=='test')format.value='pptx';
  formatHelp.textContent={pptx:'适合设计评审和向负责人汇报。包含问题依据、设计目标、任务或原型方案，以及验证安排。',docx:'适合逐条审阅与批注。保留详细依据、方案说明和任务要求。',xlsx:'适合分工与跟踪。把任务、依赖、负责人待定项和验收方式整理成可编辑表格。',html:'制作可点击的网页原型，并附操作任务和验证计划。'}[format.value];
  focusBox.hidden=!['supplement','rework'].includes(action);focusLabel.firstChild?.nodeType===Node.TEXT_NODE&&focusLabel.firstChild.remove();focusLabel.prepend(document.createTextNode(action==='rework'?'重点重新比较什么？（选填）':'重点补采什么？（选填）'));
  focus.placeholder=action==='rework'?'例如：比较独立入口和混合信息流的代价':'例如：最近30天、同一功能、具体使用经历和完整回复';platforms.hidden=action!=='supplement';
  const d=capture();drafts[i.id]=d;try{localStorage.setItem(draftKey,JSON.stringify(drafts))}catch(_){}
  next.replaceChildren();add(next,'h3','我收到后会做什么');const steps=nextSteps(d.g2,d.g3,d);if(steps.length)list(next,steps);else add(next,'p','请选择一项判断或下一步行动。');add(next,'p',portableMode?'点击底部导出后续任务，附给Agent并要求继续即可沿用这些选择。':'点击底部发送后提交这些任务；后续结果将在本次对话中显示。','muted');
  previewText.value=feedbackText({[i.id]:d});applySendState();
 }
 function setStatus(text,error=false){status.textContent=text;status.classList.toggle('error-note',error)}
 function saveChoice(){
  const d=capture();if(d.g2==='unreviewed'&&d.g3==='unreviewed'&&!d.reason){setStatus('请先选择一项判断或下一步，或写一句反馈。',true);g3.focus();return null}
  d.next_steps=nextSteps(d.g2,d.g3,d);d.saved_at=new Date().toISOString();d.record_type='local_user_choice';d.external_approval=false;decisions[i.id]=d;
  try{localStorage.setItem(storageKey,JSON.stringify(decisions))}catch(_){setStatus('浏览器未能保存在本机，请复制或导出反馈。',true)}return d;
 }
 function fingerprint(){return JSON.stringify(capture())}
 function storeSubmission(value){submitted[i.id]=value;try{localStorage.setItem(storageKey+':submitted',JSON.stringify(submitted))}catch(_){}}
 function applySendState(){
  const old=submitted[i.id],same=old?.fingerprint===fingerprint();
  send.disabled=busy||(!portableMode&&(!bridge.ready||!bridge.canSubmit||(same&&old.status==='queued')));
  const d=capture(),formatName={pptx:'PPT',docx:'Word',xlsx:'表格',html:'网页原型'}[d.delivery_format];
  send.textContent=portableMode?'导出后续任务'+(formatName?'（'+formatName+'）':''):busy?'正在发送…':same&&old.status==='queued'?'已发送到本次对话':same&&old.status==='unconfirmed'?'核对提交状态':d.g3==='adopt'?'发送并制作 '+formatName:d.g3==='test'?'发送并制作 '+formatName+' 验证方案':effectiveAction(d)==='supplement'?'发送并补采':d.g3==='rework'?'发送并重新比较':d.g3==='defer'?'发送暂缓决定':'发送并开始后续任务';
  if(!busy){if(portableMode)setStatus('当前使用跨平台任务文件交接，尚未向任何对话发送。');else if(same&&old.status==='queued')setStatus('已发送到本次对话。后续结果会在对话中交付；当前有任务时会排队继续。');else if(same&&old.status==='unconfirmed')setStatus('提交结果尚未确认，请先查看本次对话；核对同一请求不会重复发送。',true);else if(bridge.canSubmit)setStatus('选好下一步后即可发送，补充说明可以留空。');else setStatus('尚未连接直接发送服务，请从本机最新报告入口打开。',true)}
 }
 async function doSubmit(){
  const d=saveChoice();if(!d)return;
  if(!bridge.ready||!bridge.canSubmit){setStatus('尚未连接本次对话，暂时不能发送。',true);return}
  const key=fingerprint(),old=submitted[i.id];const requestId=old?.fingerprint===key?old.request_id:crypto.randomUUID();
  storeSubmission({fingerprint:key,request_id:requestId,status:'submitting'});busy=true;applySendState();setStatus('正在把所选任务发送到本次对话…');
  try{const result=await bridgeRequest('/api/submit',{request_id:requestId,bundle_id:report.bundle_id,issue_id:i.id,decision:d});storeSubmission({fingerprint:key,request_id:requestId,status:result.message_queued?'queued':'unconfirmed',queue_id:result.queue_id});}
  catch(error){storeSubmission({fingerprint:key,request_id:requestId,status:'unconfirmed'});if(error.code==='report_changed_refresh_required')setStatus('报告已更新，请刷新后重新选择任务。',true)}
  finally{busy=false;applySendState()}
 }
 send.onclick=portableMode?()=>{const d=saveChoice();if(!d)return;const payload={record_type:'followup_request',app:report.app,bundle_id:report.bundle_id,issue_id:i.id,decision_object:i.decision_object,decision:d,external_approval:false,execution_status:'not_started',evidence_ids:i.anchors.map(a=>a.evidence_id)};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),a=el('a');a.href=url;a.download=report.app+'-'+i.id+'-后续任务.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus('后续任务已导出；在Agent中附上文件并要求继续。尚未自动发送或制作。')}:doSubmit;
 copy.onclick=async()=>{const d=saveChoice();if(!d)return;copy.disabled=true;try{const method=await copyFeedback(feedbackText({[i.id]:d}));if(method)setStatus('已复制备份。直接发送请使用底部的发送按钮。');else{preview.open=true;previewText.focus();previewText.select();setStatus('未能自动复制，完整任务内容已选中，可手动复制备份。',true)}}finally{copy.disabled=false}};
 if(back)back.onclick=async event=>{if(!bridge.ready)return;event.preventDefault();try{await bridgeRequest('/api/open-conversation')}catch(_){bridge.ready=false;window.location.assign(returnUrl)}};
 save.onclick=()=>{if(saveChoice())setStatus('草稿已保存在本机；点击底部发送后才会提交。')};
 exp.onclick=()=>{if(!saveChoice())return;const payload={app:report.app,bundle_id:report.bundle_id,exported_at:new Date().toISOString(),record_type:'local_review_choices',external_approval:false,decisions};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const link=el('a');link.href=url;link.download='review-decisions.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus('已导出反馈备份，尚未因此提交任务。')};
 refreshHandoff=update;
 for(const control of [g2,g3,format,audience,focus,reason,...platformInputs])control.addEventListener(control.tagName==='SELECT'||control.type==='checkbox'?'change':'input',update);
 update();
}
