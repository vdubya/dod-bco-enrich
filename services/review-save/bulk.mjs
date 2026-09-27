import {validateBatch} from '../../docs/review-bulk.mjs';
import {REPO,BRANCH,eventPath,validateEvent} from '../../docs/review-core.mjs';
import {normalizeReview} from './github.mjs';
import {requireValue,Problem,bytes} from './security.mjs';

const sha=value=>/^[a-f0-9]{40}$/.test(value||'');
// Git identifies file contents with SHA-1 over the blob header and UTF-8 bytes.
// This is a Git object identity check, not password or signature protection.
export async function blobSHA(content){
  const data=bytes(content),header=bytes(`blob ${data.length}\0`),blob=new Uint8Array(header.length+data.length);
  blob.set(header);blob.set(data,header.length);
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-1',blob)),n=>n.toString(16).padStart(2,'0')).join('');
}
async function snapshot(github,commit){
  const c=await github.request(`/repos/${REPO}/git/commits/${commit}`);
  requireValue(c.ok && sha(c.data?.tree?.sha),502,'GitHub could not read the review snapshot. Retry this batch.');
  const t=await github.request(`/repos/${REPO}/git/trees/${c.data.tree.sha}?recursive=1`);
  requireValue(t.ok && t.data?.sha===c.data.tree.sha && t.data.truncated===false && Array.isArray(t.data.tree),502,'GitHub returned an incomplete review tree. No approval was inferred.');
  return {tree:c.data.tree.sha,files:new Map(t.data.tree.map(file=>[file.path,file]))};
}

// Adds all individual review files in one commit. The branch moves only after
// validation; non-forced updates refuse to overwrite a concurrent commit.
export async function saveBatch(github,input,candidates,hash){
  try{validateBatch(input,candidates,hash);}catch(error){throw new Problem(400,error.message);}
  const normalized=input.events.map(event=>normalizeReview(event,candidates,hash));
  const identity=await github.identity();
  const records=normalized.map(event=>({...event,authenticated_reviewer:{id:identity.id,login:identity.login}}));
  const files=await Promise.all(records.map(async event=>{
    const content=JSON.stringify(event,null,2)+'\n';
    return {path:eventPath(event.event_id),content,hash:await blobSHA(content)};
  }));
  const ref=await github.request(`/repos/${REPO}/git/ref/heads/${BRANCH}`),before=ref.data?.object?.sha;
  requireValue(ref.ok && sha(before),502,'GitHub could not read the review branch. Retry this batch.');
  const base=await snapshot(github,before);
  const matches=(view,file)=>view.files.get(file.path)?.type==='blob' && view.files.get(file.path)?.mode==='100644' && view.files.get(file.path)?.sha===file.hash;
  const receipt=commit=>({saved:true,batch_id:input.batch_id,events:records,commit,url:`https://github.com/${REPO}/commit/${commit}`});
  if(files.every(file=>matches(base,file)))return receipt(before);
  requireValue(files.every(file=>!base.files.has(file.path)),409,'Some batch event IDs already exist with different or incomplete contents. Nothing was overwritten.');
  requireValue(before===input.base_commit,409,'GitHub changed while this batch was being prepared. Retry to refresh and recheck the selected assertions.');
  for(const event of normalized)for(const id of event.supersedes||[]){
    const parent=await github.getEvent(id,before);
    requireValue(parent?.record_type==='definition_review' && parent.candidate_id===event.candidate_id,409,'An earlier review is missing or belongs to another assertion. Refresh before approving.');
    try{validateEvent(parent,candidates,hash);}catch{throw new Problem(409,'An earlier review does not match this evidence snapshot.');}
  }
  const tree=await github.request(`/repos/${REPO}/git/trees`,'POST',{base_tree:base.tree,tree:files.map(({path,content})=>({path,mode:'100644',type:'blob',content}))});
  requireValue(tree.ok && sha(tree.data?.sha),502,'GitHub could not prepare the batch. Your pending approvals are retained.');
  const made=await github.request(`/repos/${REPO}/git/commits`,'POST',{message:normalized[0].record_type==='persistence_check'?'Verify atomic BCO batch saving':`Approve ${records.length} BCO assertions`,tree:tree.data.sha,parents:[before]});
  requireValue(made.ok && sha(made.data?.sha),502,'GitHub could not prepare the approval commit. Retry this batch.');
  const commit=made.data.sha;
  const updated=await github.request(`/repos/${REPO}/git/refs/heads/${BRANCH}`,'PATCH',{sha:commit,force:false});
  requireValue(updated.ok && updated.data?.object?.sha===commit,updated.status===403?403:409,'The batch was not confirmed. Retry to check for a concurrent change without overwriting it.');
  const confirmed=await snapshot(github,commit);
  requireValue(confirmed.tree===tree.data.sha && files.every(file=>matches(confirmed,file)),502,'GitHub received the batch but its exact files could not be confirmed. Retry the same batch.');
  return receipt(commit);
}
