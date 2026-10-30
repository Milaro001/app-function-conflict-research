function drawReview(root,i){
 const intro=add(root,'div',undefined,'review-intro');add(intro,'strong','离线阅读反馈');
 add(intro,'p','本副本不会连接作者对话或发送任务。选择仅保存在当前浏览器；你可以导出文件后自行转交。');
 const saved=drafts[i.id]||decisions[i.id]||{},form=add(root,'div',undefined,'form');
 const g2Label=add(form,'label','你对分析的判断（选填）'),g2=add(g2Label,'select');g2.setAttribute('aria-label','分析判断');
 for(const [v,t] of g2Choices){const o=add(g2,'option',t);o.value=v}g2.value=saved.g2||'unreviewed';
 const g3Label=add(form,'label','建议的下一步'),g3=add(g3Label,'select');g3.setAttribute('aria-label','下一步行动');
 for(const [v,t] of g3Choices){const o=add(g3,'option',t);o.value=v}g3.value=saved.g3||'unreviewed';
 const formatLabel=add(form,'label','建议交付形式'),format=add(formatLabel,'select');format.setAttribute('aria-label','交付形式');
 for(const [v,t] of Object.entries(deliveryFormats)){const o=add(format,'option',t);o.value=v}format.value=saved.delivery_format||'pptx';
 const reasonLabel=add(form,'label','阅读意见（选填）'),reason=add(reasonLabel,'textarea');reason.setAttribute('aria-label','反馈说明');reason.value=saved.reason||'';
 add(form,'p','原报告的样本、证据和复核状态保持原样；本页新选择只作为阅读者的独立反馈。','muted');
 const dock=document.getElementById('review-dock');dock.hidden=false;dock.setAttribute('aria-label','导出离线反馈');
 const actions=add(dock,'div',undefined,'handoff-actions');const exp=add(actions,'button','导出本议题反馈','primary');const save=add(actions,'button','保存本机草稿');
 const home=add(actions,'a','离线交付首页');home.href='../打开这里.html';
 const status=add(dock,'div',undefined,'copy-status');status.setAttribute('role','status');
 function capture(){return {g2:g2.value,g3:g3.value,reason:reason.value.trim(),delivery_format:['adopt','test'].includes(g3.value)?format.value:null,external_approval:false}}
 function remember(){const d=capture();drafts[i.id]=d;try{localStorage.setItem(draftKey,JSON.stringify(drafts))}catch(_){}return d}
 function update(){remember();formatLabel.hidden=!['adopt','test'].includes(g3.value);exp.disabled=g3.value==='unreviewed';status.textContent=exp.disabled?'如需导出行动建议，请先选择下一步。':'可导出反馈文件；不会自动发送，也不会启动后续制作。';status.classList.toggle('error-note',exp.disabled)}
 save.onclick=()=>{remember();status.textContent='草稿已保存在当前浏览器；未发送到任何对话。'};
 exp.onclick=()=>{if(g3.value==='unreviewed')return;const payload={record_type:'offline_reader_feedback',app:report.app,bundle_id:report.bundle_id,issue_id:i.id,decision_object:i.decision_object,decision:remember(),exported_at:new Date().toISOString(),automatically_submitted:false,external_approval:false};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=report.app+'-离线阅读反馈.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='反馈文件已导出，需由你自行转交；没有自动发送。'};
 for(const control of [g2,g3,format,reason])control.addEventListener(control===reason?'input':'change',update);update();
}
