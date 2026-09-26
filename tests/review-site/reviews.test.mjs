import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {validateEvent,resolveReviews,githubSaveURL} from '../../docs/review-core.mjs';
const candidates=JSON.parse(readFileSync(new URL('../../docs/data/pilot-ledger.json',import.meta.url)));
const manifest=JSON.parse(readFileSync(new URL('../../docs/data/site-manifest.json',import.meta.url)));
const units=JSON.parse(readFileSync(new URL('../../docs/data/source-units.json',import.meta.url)));
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const c=candidates[0];
const event=(n,extra={})=>({schema_version:1,record_type:'definition_review',event_id:id(n),created_at:'2026-09-26T20:00:00.000Z',candidate_id:c.candidate_id,dataset_sha256:manifest.dataset_sha256,source_sha256:c.source.source_sha256,source_version_id:c.source.version_id,supersedes:[],status:'accepted',reviewer:'Test reviewer',rationale:'Test rationale',scope_note:'Only within the quoted scope.',proposed_label:'',proposed_definition:'',...extra});
const resolved=events=>resolveReviews(events,candidates,manifest.dataset_sha256);
test('frozen 50-entry evidence and all quoted spans round trip',()=>{
 assert.equal(candidates.length,50);
 assert.equal(createHash('sha256').update(readFileSync(new URL('../../docs/data/pilot-ledger.json',import.meta.url))).digest('hex'),manifest.dataset_sha256);
 for(const candidate of candidates){
  for(const e of [...candidate.evidence,...candidate.label_evidence])assert.equal(Array.from(units[e.unit_id].text_exact).slice(e.start,e.end).join(''),e.source_text_exact);
  for(const id of [...candidate.context_unit_ids,...candidate.scope.source_document_scope_unit_ids])assert.ok(units[id]);
 }
});
test('an empty repository means pending, never accepted',()=>{for(const state of resolved([]).states.values())assert.equal(state.status,'pending');});
test('a saved review can be superseded and reopened without losing history',()=>{
 const state=resolved([event(1),event(2,{status:'pending',supersedes:[id(1)]})]).states.get(c.candidate_id);
 assert.equal(state.status,'pending');assert.equal(state.history.length,2);assert.equal(state.latest.event_id,id(2));
});
test('concurrent decisions stay in conflict until explicitly reconciled',()=>{
 const a=event(1),b=event(2,{status:'rejected'});
 assert.equal(resolved([a,b]).states.get(c.candidate_id).status,'conflict');
 const state=resolved([a,b,event(3,{status:'deferred',supersedes:[id(1),id(2)]})]).states.get(c.candidate_id);
 assert.equal(state.status,'deferred');assert.equal(state.history.length,3);
});
test('missing parents and cycles fail closed',()=>{
 assert.equal(resolved([event(2,{supersedes:[id(1)]})]).states.get(c.candidate_id).status,'unverified');
 assert.equal(resolved([event(1,{supersedes:[id(2)]}),event(2,{supersedes:[id(1)]})]).states.get(c.candidate_id).status,'unverified');
});
test('stale evidence, unknown candidates and duplicate identities are not accepted',()=>{
 for(const bad of [event(1,{dataset_sha256:'changed'}),event(1,{source_sha256:'changed'}),event(1,{candidate_id:'unknown'})]){
  assert.throws(()=>validateEvent(bad,candidates,manifest.dataset_sha256));
  assert.equal(resolved([bad]).states.get(c.candidate_id).status,'unverified');
 }
 assert.equal(resolved([event(1),event(1)]).states.get(c.candidate_id).status,'unverified');
});
test('every decision permits blank scope and rationale while requiring a reviewer',()=>{
 for(const status of ['accepted','rejected','needs_revision','deferred','pending']){
  for(const notes of ['', '  ']){
   const review=event(1,{status,scope_note:notes,rationale:notes});
   const prepared=JSON.parse(new URL(githubSaveURL(review)).searchParams.get('value'));
   const result=resolved([prepared]);
   assert.deepEqual(result.issues,[]);
   assert.equal(result.states.get(c.candidate_id).status,status);
   assert.equal(result.states.get(c.candidate_id).latest.scope_note,notes);
   assert.equal(result.states.get(c.candidate_id).latest.rationale,notes);
  }
 }
 assert.throws(()=>validateEvent(event(1,{reviewer:'  '}),candidates,manifest.dataset_sha256));
 for(const extra of [{scope_note:'x'.repeat(501)},{rationale:'x'.repeat(601)},{scope_note:42},{rationale:[]}])assert.throws(()=>validateEvent(event(1,extra),candidates,manifest.dataset_sha256));
});
test('technical save checks cannot adjudicate vocabulary',()=>{
 const check={schema_version:1,event_id:id(1),created_at:'2026-09-26T20:00:00Z',record_type:'persistence_check',dataset_sha256:manifest.dataset_sha256,purpose:'Technical save verification; no vocabulary decision'};
 const r=resolved([check]);assert.equal(r.checks.length,1);assert.equal(r.states.get(c.candidate_id).status,'pending');
 assert.throws(()=>validateEvent({...check,status:'accepted'},candidates,manifest.dataset_sha256));
});
test('GitHub handoff preserves Unicode and punctuation without executable content',()=>{
 const e=event(1,{rationale:'Café & “Owner” <script> is plain review text.'});
 const url=new URL(githubSaveURL(e));
 assert.equal(url.origin,'https://github.com');assert.equal(url.pathname,'/vdubya/dod-bco-enrich/new/dod-bco');
 assert.equal(url.searchParams.get('filename'),`docs/review-events/${id(1)}.json`);
 assert.deepEqual(JSON.parse(url.searchParams.get('value')),e);
 assert.throws(()=>githubSaveURL({...e,event_id:'../../other'}));
 assert.throws(()=>githubSaveURL({...e,rationale:'界'.repeat(3000)}));
});
