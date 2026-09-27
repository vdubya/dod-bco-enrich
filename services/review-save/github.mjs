import {REPO,BRANCH,validateEvent,eventPath,sameReviewContent} from '../../docs/review-core.mjs';
import {Problem,requireValue,base64,bytes} from './security.mjs';

export const REPOSITORY_ID=1389728130;
export const OWNER_ID=6257997;
export const API='https://api.github.com';
const common=['schema_version','record_type','event_id','created_at','dataset_sha256'];
const review=[...common,'candidate_id','source_sha256','source_version_id','supersedes','status','reviewer','scope_note','rationale','proposed_label','proposed_definition'];
const check=[...common,'purpose'];

export class GitHub {
  constructor(token,fetcher=(...args)=>globalThis.fetch(...args)){this.token=token;this.fetcher=fetcher;}
  async request(path,method='GET',body) {
    const response=await this.fetcher(API+path,{method,headers:{
      'Authorization':`Bearer ${this.token}`,'Accept':'application/vnd.github+json',
      'X-GitHub-Api-Version':'2022-11-28','User-Agent':'DoD-BCO-Review-Save',
      ...(body?{'Content-Type':'application/json'}:{})
    },...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(20000),redirect:'manual'});
    let data;try{data=await response.json();}catch{data=null;}
    return {status:response.status,ok:response.ok,data};
  }
  async identity() {
    const user=await this.request('/user');
    requireValue(user.ok,401,'Your GitHub connection expired. Sign in again.');
    requireValue(user.data?.id===OWNER_ID,403,'Only the repository owner can save reviews in this pilot.');
    const repo=await this.request(`/repos/${REPO}`);
    requireValue(repo.ok && repo.data?.id===REPOSITORY_ID && repo.data?.permissions?.push===true,403,'This GitHub connection does not have write access to the review repository.');
    return {id:user.data.id,login:user.data.login,name:user.data.name||user.data.login};
  }
  async getEvent(id,ref=BRANCH) {
    const r=await this.request(`/repos/${REPO}/contents/${eventPath(id)}?ref=${encodeURIComponent(ref)}`);
    if(r.status===404)return null;
    requireValue(r.ok && r.data?.type==='file' && r.data.encoding==='base64' && r.data.size<=20000,502,'GitHub could not verify the saved review. Retry the same save.');
    try{
      const event=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(r.data.content.replace(/\s/g,'')),c=>c.charCodeAt(0))));
      if(event.event_id!==id)throw Error('Mismatched identity.');
      return event;
    }
    catch{throw new Problem(409,'The existing review file is invalid. It has not been overwritten.');}
  }
}

export function normalizeReview(input,candidates,datasetHash) {
  requireValue(input && typeof input==='object' && !Array.isArray(input),400,'A review record is required.');
  const allowed=input.record_type==='persistence_check'?check:review;
  requireValue(Object.keys(input).every(k=>allowed.includes(k)),400,'Unexpected review fields. Repository paths and authenticated identity are set by the service.');
  try{validateEvent(input,candidates,datasetHash);}catch(error){throw new Problem(400,error.message);}
  return Object.fromEntries(allowed.filter(k=>Object.hasOwn(input,k)).map(k=>[k,input[k]]));
}
function sameReview(a,b,identity) {
  if(a?.authenticated_reviewer?.id!==identity.id)return false;
  return sameReviewContent(a,b);
}

// Creates only UUID-named review events. No supplied path, ref, existing-file SHA,
// deletion, workflow change, or arbitrary GitHub API call can pass this boundary.
export async function saveReview(github,input,candidates,datasetHash) {
  const review=normalizeReview(input,candidates,datasetHash);
  const identity=await github.identity();
  const ref=await github.request(`/repos/${REPO}/git/ref/heads/${BRANCH}`);
  const before=ref.data?.object?.sha;
  requireValue(ref.ok && /^[a-f0-9]{40}$/.test(before||''),502,'GitHub could not read the review branch. Your draft is retained.');
  const receipt=(commit,event)=>({saved:true,event,commit,url:`https://github.com/${REPO}/blob/${commit}/${eventPath(review.event_id)}`});
  const existing=await github.getEvent(review.event_id,before);
  if(existing){
    requireValue(sameReview(existing,review,identity),409,'This event ID is already used by a different review. The existing file has not been changed.');
    return receipt(before,existing);
  }
  for(const id of review.supersedes||[]) {
    const parent=await github.getEvent(id,before);
    requireValue(parent?.record_type==='definition_review' && parent.candidate_id===review.candidate_id,409,'A referenced earlier review is missing or belongs to another assertion. Refresh before saving.');
    try{validateEvent(parent,candidates,datasetHash);}catch{throw new Problem(409,'An earlier review does not match this evidence snapshot.');}
  }
  const record={...review,authenticated_reviewer:{id:identity.id,login:identity.login}};
  const content=base64(bytes(JSON.stringify(record,null,2)+'\n'));
  const message=review.record_type==='persistence_check'?'Verify direct BCO review saving':`Review ${review.candidate_id}: ${review.status}`;
  for(let attempt=0;attempt<2;attempt++) {
    const saved=await github.request(`/repos/${REPO}/contents/${eventPath(review.event_id)}`,'PUT',{message,content,branch:BRANCH});
    const commit=saved.data?.commit?.sha;
    if(saved.ok && /^[a-f0-9]{40}$/.test(commit||'')){
      const readback=await github.getEvent(review.event_id,commit);
      requireValue(readback && sameReview(readback,review,identity),502,'GitHub received the save but confirmation is incomplete. Retry to check the same record.');
      return receipt(commit,readback);
    }
    if([409,422].includes(saved.status)) {
      const current=await github.getEvent(review.event_id);
      if(current){
        requireValue(sameReview(current,review,identity),409,'This event ID is already used. The existing review has not been overwritten.');
        const head=await github.request(`/repos/${REPO}/git/ref/heads/${BRANCH}`);
        const sha=head.data?.object?.sha;
        requireValue(/^[a-f0-9]{40}$/.test(sha||''),502,'The saved review could not be confirmed. Retry the same save.');
        const confirmed=await github.getEvent(review.event_id,sha);
        requireValue(confirmed && sameReview(confirmed,review,identity),502,'The saved review could not be confirmed. Retry the same save.');
        return receipt(sha,confirmed);
      }
      if(attempt===0)continue;
    }
    if(saved.status===401)throw new Problem(401,'Your GitHub connection expired. Sign in again.');
    if(saved.status===403)throw new Problem(403,'GitHub did not permit this save. Check the app installation and repository write access.');
    throw new Problem(502,'GitHub could not complete the save. Your draft is retained; retry safely.');
  }
}
