import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {GitHub,OWNER_ID,REPOSITORY_ID} from '../../services/review-save/github.mjs';
import {saveBatch} from '../../services/review-save/bulk.mjs';
import {validateBatch,bulkBlockReason,assertBatchHeads,batchIsSaved} from '../../docs/review-bulk.mjs';
import {resolveReviews,eventPath} from '../../docs/review-core.mjs';
import {createConnection} from '../../docs/review-auth.mjs';
const candidates=JSON.parse(readFileSync(new URL('../../docs/data/pilot-ledger.json',import.meta.url)));
const hash=JSON.parse(readFileSync(new URL('../../docs/data/site-manifest.json',import.meta.url))).dataset_sha256;
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const blob=content=>createHash('sha1').update(`blob ${Buffer.byteLength(content)}\0`).update(content).digest('hex');
const record=(n,c=candidates[n-1])=>({schema_version:1,record_type:'definition_review',event_id:id(n),created_at:'2026-09-27T02:00:00Z',candidate_id:c.candidate_id,dataset_sha256:hash,source_sha256:c.source.source_sha256,source_version_id:c.source.version_id,supersedes:[],status:'accepted',reviewer:'Test reviewer',scope_note:'',rationale:'',proposed_label:'',proposed_definition:''});
function fixture(){
 const initial='1'.repeat(40),trees=new Map([['2'.repeat(40),new Map([['README.md','keep this file\n']])]]),commits=new Map([[initial,'2'.repeat(40)]]);
 const f={head:initial,calls:[],userId:OWNER_ID,canPush:true,race:false,badReadback:false,truncate:false};let count=3;
 f.fetch=async(url,options={})=>{
  const u=new URL(url),method=options.method||'GET',body=options.body?JSON.parse(options.body):undefined;
  assert.equal(u.origin,'https://api.github.com');assert.equal(options.headers.Authorization,'Bearer fake');assert.equal(options.redirect,'manual');
  f.calls.push({path:u.pathname,method,body});
  const prefix='/repos/vdubya/dod-bco-enrich';
  if(u.pathname==='/user')return Response.json({id:f.userId,login:'vdubya'});
  if(u.pathname===prefix)return Response.json({id:REPOSITORY_ID,permissions:{push:f.canPush}});
  if(u.pathname===prefix+'/git/ref/heads/dod-bco')return Response.json({object:{sha:f.head}});
  if(u.pathname.startsWith(prefix+'/git/commits/') && method==='GET'){
   const revision=u.pathname.split('/').at(-1);return Response.json({sha:revision,tree:{sha:commits.get(revision)}});
  }
  if(u.pathname.startsWith(prefix+'/git/trees/') && method==='GET'){
   const tree=u.pathname.split('/').at(-1);const files=trees.get(tree);assert.ok(files);
   return Response.json({sha:tree,truncated:f.truncate,tree:[...files].map(([path,content])=>({path,type:'blob',mode:'100644',sha:f.badReadback && f.head!==initial && path.startsWith('docs/')?'f'.repeat(40):blob(content)}))});
  }
  if(u.pathname===prefix+'/git/trees' && method==='POST'){
   assert.ok(trees.has(body.base_tree));const next=new Map(trees.get(body.base_tree));
   for(const e of body.tree){assert.match(e.path,/^docs\/review-events\/[a-f0-9-]{36}\.json$/);assert.equal(e.mode,'100644');assert.equal(e.type,'blob');assert.equal(e.sha,undefined);assert.equal(next.has(e.path),false);next.set(e.path,e.content);}
   const sha=String(count++).padStart(40,'0');trees.set(sha,next);return Response.json({sha},{status:201});
  }
  if(u.pathname===prefix+'/git/commits' && method==='POST'){
   assert.deepEqual(body.parents,[initial]);const sha=String(count++).padStart(40,'0');commits.set(sha,body.tree);return Response.json({sha},{status:201});
  }
  if(u.pathname===prefix+'/git/refs/heads/dod-bco' && method==='PATCH'){
   assert.equal(body.force,false);
   if(f.race){f.head='a'.repeat(40);commits.set(f.head,'2'.repeat(40));return Response.json({message:'Not a fast-forward'},{status:422});}
   f.head=body.sha;return Response.json({object:{sha:body.sha}});
  }
  if(u.pathname.startsWith(prefix+'/contents/'))return Response.json({message:'Not found'},{status:404});
  throw Error(`Unexpected endpoint ${method} ${u.pathname}`);
 };
 f.github=new GitHub('fake',f.fetch);f.batch={batch_id:id(100),base_commit:initial,events:[record(1),record(2)]};
 f.files=()=>trees.get(commits.get(f.head));f.initialFiles=trees.get('2'.repeat(40));return f;
}
test('a full 50-assertion batch creates one commit, preserves other files, and verifies every Git blob',async()=>{
 const f=fixture();f.batch.events=candidates.map((c,i)=>record(i+1,c));
 const result=await saveBatch(f.github,f.batch,candidates,hash);
 assert.equal(result.saved,true);assert.equal(result.events.length,50);assert.equal(result.commit,f.head);
 assert.equal(f.files().get('README.md'),'keep this file\n');assert.equal(f.files().size,51);
 assert.equal(f.calls.filter(c=>c.method==='POST' && c.path.endsWith('/git/commits')).length,1);
 assert.equal(f.calls.filter(c=>c.method==='PATCH').length,1);
 assert.equal(f.calls.length,10);
 for(const event of result.events){assert.equal(event.authenticated_reviewer.id,OWNER_ID);assert.equal(JSON.parse(f.files().get(eventPath(event.event_id))).rationale,'');}
});
test('an uncertain successful batch can be retried without a second commit',async()=>{
 const f=fixture();const first=await saveBatch(f.github,f.batch,candidates,hash);const retry=await saveBatch(f.github,f.batch,candidates,hash);
 assert.deepEqual(retry,first);assert.equal(f.calls.filter(c=>c.method==='PATCH').length,1);
});
test('all records are validated before any write, including duplicates, paths and batch size',async()=>{
 const cases=[b=>b.events[1].dataset_sha256='wrong',b=>b.events[1].status='rejected',b=>b.events[1].path='README.md',b=>b.events.push(b.events[0]),b=>b.events[1].candidate_id=b.events[0].candidate_id,b=>b.events=Array.from({length:51},()=>b.events[0]),b=>b.repository='elsewhere'];
 for(const mutate of cases){const f=fixture();mutate(f.batch);await assert.rejects(saveBatch(f.github,f.batch,candidates,hash),e=>e.status===400);assert.equal(f.calls.filter(c=>c.method!=='GET').length,0);}
});
test('owner, permission, source-history and stale-snapshot boundaries reject the whole batch',async()=>{
 for(const mutate of [f=>f.userId=8,f=>f.canPush=false,f=>f.batch.base_commit='0'.repeat(40),f=>f.batch.events[0].supersedes=[id(90)]]){
  const f=fixture();mutate(f);await assert.rejects(saveBatch(f.github,f.batch,candidates,hash));assert.equal(f.calls.filter(c=>c.method!=='GET').length,0);
 }
});
test('partial or colliding existing files never get overwritten',async()=>{
 const f=fixture();f.initialFiles.set(eventPath(f.batch.events[0].event_id),'different');
 await assert.rejects(saveBatch(f.github,f.batch,candidates,hash),e=>e.status===409);
 assert.equal(f.calls.filter(c=>c.method!=='GET').length,0);
});
test('a concurrent commit is not overwritten and mismatched read-back never reports success',async()=>{
 const raced=fixture();raced.race=true;await assert.rejects(saveBatch(raced.github,raced.batch,candidates,hash),e=>e.status===409);assert.equal(raced.files().size,1);
 const bad=fixture();bad.badReadback=true;await assert.rejects(saveBatch(bad.github,bad.batch,candidates,hash),e=>e.status===502);
 const truncated=fixture();truncated.truncate=true;await assert.rejects(saveBatch(truncated.github,truncated.batch,candidates,hash),e=>e.status===502);assert.equal(truncated.calls.filter(c=>c.method!=='GET').length,0);
});
test('two technical receipts exercise atomic saving without approving an assertion',async()=>{
 const f=fixture();f.batch.events=[1,2].map(n=>({schema_version:1,record_type:'persistence_check',event_id:id(n),created_at:'2026-09-27T02:00:00Z',dataset_sha256:hash,purpose:'Technical save verification; no vocabulary decision'}));
 const result=await saveBatch(f.github,f.batch,candidates,hash);assert.equal(resolveReviews(result.events,candidates,hash).states.get(candidates[0].candidate_id).status,'pending');
});
test('changed review heads and editorial drafts require individual attention',()=>{
 const f=fixture(),empty=resolveReviews([],candidates,hash);assert.doesNotThrow(()=>assertBatchHeads(f.batch,empty));
 assert.ok(bulkBlockReason(empty.states.get(candidates[0].candidate_id),true));
 assert.ok(bulkBlockReason({status:'needs_revision',latest:{proposed_definition:'Edit'}},false));
 const changed=resolveReviews([{...record(90,candidates[0]),status:'deferred'}],candidates,hash);
 assert.throws(()=>assertBatchHeads(f.batch,changed),/changed/);
 assert.equal(batchIsSaved(f.batch,f.batch.events),false);
 assert.equal(batchIsSaved(f.batch,f.batch.events.map(e=>({...e,authenticated_reviewer:{id:OWNER_ID}}))),true);
 assert.throws(()=>validateBatch({...f.batch,events:[]},candidates,hash));
});
test('the browser accepts a receipt only when every batch event, identity and commit matches',async()=>{
 const f=fixture(),result=await saveBatch(f.github,f.batch,candidates,hash);
 const values=new Map([['dod-bco-save-connection-v1',JSON.stringify({token:'a'.repeat(43),expires:Math.floor(Date.now()/1000)+1000,user:{id:OWNER_ID}})]]);
 const storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 for(const returned of [result,{...result,events:result.events.slice(0,1)},{...result,events:[result.events[0],result.events[0]]},{...result,url:'https://other.example'}, {...result,events:result.events.map(e=>({...e,authenticated_reviewer:{id:8}}))}]){
  const client=createConnection('https://save.example',{storage,flowStorage:storage,fetcher:async(url,options)=>{assert.equal(url,'https://save.example/reviews/batch');assert.deepEqual(JSON.parse(options.body),f.batch);return Response.json(returned);}});
  if(returned===result)assert.deepEqual(await client.saveBatch(f.batch),result);else await assert.rejects(client.saveBatch(f.batch),/confirmation did not match/);
 }
});
