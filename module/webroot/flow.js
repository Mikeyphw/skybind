// Skybind native/WebUI contract helpers. No generic execution or authority escalation.
export function eligibleNamespaceGroups(snapshot) {
 if (!snapshot || snapshot.complete !== true || !Array.isArray(snapshot.groups)) return [];
 return snapshot.groups.filter(g => typeof g.namespace==='string' && g.namespace.length>0 && g.complete===true && g.protected===false && g.visibility==='not_visible' && Array.isArray(g.members) && g.members.length>0 && g.members.every(m=>m.class==='app'));
}
export function validateNamespaceSelection(snapshot, selected) {
 const allow=new Set(eligibleNamespaceGroups(snapshot).map(g=>g.namespace));
 if (!Array.isArray(selected) || !selected.length || selected.length>512 || new Set(selected).size!==selected.length || selected.some(n=>!allow.has(n))) throw new Error('Explicit selection must contain only eligible app namespace groups');
 return [...selected].sort();
}
export function nativeCachePreview(preview,name,action) {
 if (!preview || preview.action!==action || preview.snapshot?.name!==name || typeof preview.proof!=='string' || !preview.proof) throw new Error('Cache preview identity or proof missing');
 return {proof:preview.proof,delete_files:preview.snapshot?.count||0,bytes_to_remove:preview.bytes_to_remove||0};
}
export function presentJobStatus(status) {
 const jobs=status?.registry?.jobs||[], runs=status?.runs||[];
 if(!Array.isArray(jobs)||!Array.isArray(runs)) throw new Error('Invalid durable jobs status');
 return jobs.map(job=>{
   const related=runs.filter(r=>r.name===job.name).sort((a,b)=>Number(b.started_unix||0)-Number(a.started_unix||0));
   const last=related.find(r=>r.id===job.last_run_id)||related[0];
   return {name:job.name,last_state:last?.state||(job.enabled?'SCHEDULED':'DISABLED'),last_run_id:last?.id||'',run_count:related.length,
    bytes:last?.bytes||0,speed_bytes_per_second:last?.speed_bytes_per_second||0,eta_seconds:last?.eta_seconds||0,
    next_run_unix_ms:Number(job.next_unix||0)*1000,reason:last?.reason||'',finished_unix_ms:Number(last?.finished_unix||0)*1000};
 });
}
export function presentActivity(records, status) {
 const runs=new Map((status?.runs||[]).map(run=>[run.id,run]));
 return (records||[]).map(record=>{
   const linked=record.run_id?runs.get(record.run_id):null;
   const state=(linked?.state||(record.state||'UNKNOWN')).toUpperCase();
   const moment=record.finished||record.started;
   return {request_id:linked?.state==='RUNNING'?record.run_id:(record.request_id||record.id),operation:record.action,state:state==='COMPLETED'?'SUCCEEDED':state,
     cancellable:Boolean(linked?.state==='RUNNING' && record.action==='job.run'),run_id:record.run_id||'',updated_unix_ms:linked?.finished_unix?linked.finished_unix*1000:Date.parse(moment||'')||0,
     events:[{event:record.stage||'recorded',message:linked?.reason|| (linked?.state==='RUNNING'?`Transferred ${linked.bytes||0} bytes`:'')}],error:record.error_code?{message:record.error_code}:null};
 });
}
