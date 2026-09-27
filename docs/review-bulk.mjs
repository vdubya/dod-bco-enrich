import {validateEvent,sameReviewContent} from './review-core.mjs?v=bulk-1';

export const MAX_BATCH=50;
export function validateBatch(batch,candidates,hash){
  if(!batch || Object.keys(batch).some(k=>!['batch_id','base_commit','events'].includes(k)) || !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(batch.batch_id||'') || !/^[a-f0-9]{40}$/.test(batch.base_commit||''))throw Error('Invalid approval batch.');
  if(!Array.isArray(batch.events) || !batch.events.length || batch.events.length>MAX_BATCH)throw Error(`Select between 1 and ${MAX_BATCH} assertions.`);
  const ids=new Set(),assertions=new Set(),kind=batch.events[0]?.record_type;
  for(const event of batch.events){
    validateEvent(event,candidates,hash);
    if(ids.has(event.event_id) || event.record_type!==kind)throw Error('A batch must contain distinct records of one type.');
    ids.add(event.event_id);
    if(kind==='definition_review'){
      if(event.status!=='accepted' || assertions.has(event.candidate_id))throw Error('Bulk approval needs one approval per assertion.');
      assertions.add(event.candidate_id);
    }
  }
  return batch;
}
export function bulkBlockReason(state,hasDraft){
  if(hasDraft)return 'Finish the local draft first';
  if(!state || ['conflict','unverified'].includes(state.status))return 'Review this history individually';
  if(state.status==='accepted')return 'Already approved';
  if(state.latest?.proposed_label || state.latest?.proposed_definition)return 'Review proposed wording individually';
  return '';
}
export function assertBatchHeads(batch,resolution){
  for(const event of batch.events){
    if(event.record_type!=='definition_review')continue;
    const state=resolution?.states.get(event.candidate_id);
    if(bulkBlockReason(state,false) || JSON.stringify(state.heads.map(e=>e.event_id).sort())!==JSON.stringify([...event.supersedes].sort()))throw Error('A selected assertion changed after this batch was prepared. Clear the pending batch and review the updated rows.');
  }
}
export function batchIsSaved(batch,events){
  return !!batch && batch.events.every(expected=>events.some(saved=>saved.authenticated_reviewer?.id===6257997 && sameReviewContent(saved,expected)));
}
