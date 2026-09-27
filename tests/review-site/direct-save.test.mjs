import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {GitHub,saveReview,OWNER_ID,REPOSITORY_ID} from '../../services/review-save/github.mjs';
import {createService,REPORT,REPORT_ORIGIN} from '../../services/review-save/service.mjs';
import {Store} from '../../services/review-save/store.mjs';
import {base64,bytes,random,digest,now} from '../../services/review-save/security.mjs';
const candidates=JSON.parse(readFileSync(new URL('../../docs/data/pilot-ledger.json',import.meta.url)));
const {dataset_sha256:hash}=JSON.parse(readFileSync(new URL('../../docs/data/site-manifest.json',import.meta.url)));
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const c=candidates[0];
const event=(n=1,extra={})=>({schema_version:1,record_type:'definition_review',event_id:id(n),created_at:'2026-09-26T20:00:00.000Z',candidate_id:c.candidate_id,dataset_sha256:hash,source_sha256:c.source.source_sha256,source_version_id:c.source.version_id,supersedes:[],status:'accepted',reviewer:'Local test only',rationale:'',scope_note:'',proposed_label:'',proposed_definition:'',...extra});
const receipt=(n=1)=>({schema_version:1,record_type:'persistence_check',event_id:id(n),created_at:'2026-09-26T20:00:00Z',dataset_sha256:hash,purpose:'Technical save verification; no vocabulary decision'});

function githubMock(){
  const files=new Map(),snapshots=new Map(),calls=[];
  let count=1,sha=String(count).padStart(40,'0');
  snapshots.set(sha,new Map());
  const mock={files,calls,userId:OWNER_ID,canPush:true,putStatus:null,breakReadback:false};
  mock.fetch=async (url,options={})=>{
    const u=new URL(url),method=options.method||'GET',body=options.body?JSON.parse(options.body):null;
    calls.push({url:u.href,method,body});
    assert.equal(u.origin,'https://api.github.com');
    assert.equal(options.headers.Authorization,'Bearer fake-access');
    if(u.pathname==='/user')return Response.json({id:mock.userId,login:'vdubya',name:'Van Woods'});
    if(u.pathname==='/repos/vdubya/dod-bco-enrich')return Response.json({id:REPOSITORY_ID,permissions:{push:mock.canPush}});
    if(u.pathname.endsWith('/git/ref/heads/dod-bco'))return Response.json({object:{sha}});
    const match=u.pathname.match(/^\/repos\/vdubya\/dod-bco-enrich\/contents\/(docs\/review-events\/[a-f0-9-]{36}\.json)$/);
    assert.ok(match,`Unexpected API path ${u.pathname}`);
    const path=match[1];
    if(method==='GET'){
      const ref=u.searchParams.get('ref'),snapshot=ref==='dod-bco'?files:snapshots.get(ref);
      let text=snapshot?.get(path);
      if(mock.breakReadback && count>1)text=JSON.stringify({...JSON.parse(text),purpose:'changed'});
      return text?Response.json({type:'file',size:bytes(text).length,encoding:'base64',content:base64(bytes(text))}):Response.json({message:'Not Found'},{status:404});
    }
    assert.equal(method,'PUT');assert.equal(body.branch,'dod-bco');assert.equal(body.sha,undefined);
    if(mock.putStatus)return Response.json({message:'Rejected'},{status:mock.putStatus});
    if(files.has(path))return Response.json({message:'sha is required'},{status:422});
    files.set(path,new TextDecoder().decode(Uint8Array.from(atob(body.content),ch=>ch.charCodeAt(0))));
    sha=String(++count).padStart(40,'0');snapshots.set(sha,new Map(files));
    return Response.json({commit:{sha}},{status:201});
  };
  mock.github=new GitHub('fake-access',mock.fetch);
  return mock;
}

class D1SQLite {
  constructor(){this.db=new DatabaseSync(':memory:');}
  async exec(sql){this.db.exec(sql);}
  prepare(sql){
    const stmt=this.db.prepare(sql);
    const build=params=>({bind:(...values)=>build(values),first:async()=>stmt.get(...params)||null,run:async()=>({success:true,meta:stmt.run(...params)})});
    return build([]);
  }
  async batch(statements){this.db.exec('BEGIN');try{const result=[];for(const s of statements)result.push(await s.run());this.db.exec('COMMIT');return result;}catch(e){this.db.exec('ROLLBACK');throw e;}}
}
async function serviceFixture({configured=true}={}){
  const db=new D1SQLite();
  const env={DB:db,SESSION_KEY:base64(crypto.getRandomValues(new Uint8Array(32))),SETUP_KEY:random(),SERVICE_URL:'https://save.example.test'};
  const store=new Store(db,env.SESSION_KEY);
  await db.exec(readFileSync(new URL('../../services/review-save/drizzle/0000_auth.sql',import.meta.url),'utf8'));
  if(configured)await store.configure({id:1,client_id:'fake-client',client_secret:'fake-secret',html_url:'https://github.com/apps/test-bco'});
  const github=githubMock();let oauthCalls=[];
  const service=createService({candidates,datasetHash:hash,fetcher:async(url,options)=>{
    if(url==='https://github.com/login/oauth/access_token'){
      oauthCalls.push(JSON.parse(options.body));
      return Response.json({access_token:'fake-access',expires_in:28800,refresh_token:'fake-refresh',refresh_token_expires_in:15552000});
    }
    return github.fetch(url,options);
  }});
  const request=(path,{method='GET',body,token,origin=REPORT_ORIGIN,cookie,headers={}}={})=>service.fetch(new Request(env.SERVICE_URL+path,{method,headers:{...(origin?{Origin:origin}:{}),...(body?{'Content-Type':'application/json'}:{}),...(token?{Authorization:`Bearer ${token}`} : {}),...(cookie?{Cookie:cookie}:{}),...headers},...(body?{body:JSON.stringify(body)}:{})}),env);
  async function login(){
    const verifier=random(),start=await request(`/auth/start?challenge=${await digest(verifier)}`);
    assert.equal(start.status,303);
    const authorization=new URL(start.headers.get('location'));
    const state=authorization.searchParams.get('state');
    const binding=start.headers.get('set-cookie').split(';')[0];
    const callback=await request(`/auth/callback?state=${state}&code=fake-github-code`,{cookie:binding});
    assert.equal(callback.status,303);
    const target=new URL(callback.headers.get('location'));
    assert.equal(target.origin,new URL(REPORT).origin);assert.equal(target.pathname,new URL(REPORT).pathname);
    const code=target.searchParams.get('bco_code');
    const exchange=await request('/auth/exchange',{method:'POST',body:{code,verifier}});
    assert.equal(exchange.status,200);const session=await exchange.json();
    return {...session,code,verifier,state,binding,authorization};
  }
  return {env,store,github,oauthCalls,request,login,db};
}

test('direct saving writes only the fixed review path and confirms the immutable commit',async()=>{
  const m=githubMock();
  const result=await saveReview(m.github,event(),candidates,hash);
  assert.equal(result.saved,true);assert.equal(result.event.rationale,'');assert.equal(result.event.scope_note,'');
  assert.deepEqual(result.event.authenticated_reviewer,{id:OWNER_ID,login:'vdubya'});
  assert.equal(m.files.size,1);
  assert.ok(result.url.includes(`/blob/${result.commit}/docs/review-events/${id(1)}.json`));
  assert.ok(m.calls.at(-1).url.endsWith(`?ref=${result.commit}`));
});
test('an unchanged retry confirms the existing commit without a second write',async()=>{
  const m=githubMock();
  const first=await saveReview(m.github,receipt(),candidates,hash);
  const second=await saveReview(m.github,receipt(),candidates,hash);
  assert.deepEqual(second,first);assert.equal(m.calls.filter(c=>c.method==='PUT').length,1);
});
test('an event ID collision never overwrites the previous review',async()=>{
  const m=githubMock();await saveReview(m.github,event(),candidates,hash);
  await assert.rejects(saveReview(m.github,event(1,{status:'rejected'}),candidates,hash),e=>e.status===409);
  assert.equal(m.calls.filter(c=>c.method==='PUT').length,1);
});
test('untrusted paths, branches, identities, stale evidence and oversized notes are rejected before GitHub writes',async()=>{
  for(const changed of [{path:'.github/workflows/change.yml'},{branch:'main'},{authenticated_reviewer:{id:OWNER_ID}},{dataset_sha256:'stale'},{source_sha256:'stale'},{event_id:'../../other'},{rationale:'x'.repeat(601)}]){
    const m=githubMock();await assert.rejects(saveReview(m.github,event(1,changed),candidates,hash),e=>e.status===400);
    assert.equal(m.calls.length,0);
  }
});
test('another account or revoked repository write access cannot commit',async()=>{
  for(const changed of [{userId:7},{canPush:false}]){
    const m=Object.assign(githubMock(),changed);await assert.rejects(saveReview(m.github,event(),candidates,hash),e=>e.status===403);
    assert.equal(m.files.size,0);
  }
});
test('missing and cross-assertion parents cannot enter the review history',async()=>{
  const m=githubMock();await saveReview(m.github,event(),candidates,hash);
  await assert.rejects(saveReview(m.github,event(2,{supersedes:[id(3)]}),candidates,hash),e=>e.status===409);
  const other=candidates[1];
  await assert.rejects(saveReview(m.github,event(2,{candidate_id:other.candidate_id,source_sha256:other.source.source_sha256,source_version_id:other.source.version_id,supersedes:[id(1)]}),candidates,hash),e=>e.status===409);
  const good=await saveReview(m.github,event(2,{supersedes:[id(1)],status:'pending'}),candidates,hash);assert.equal(good.saved,true);
});
test('failed or different read-back is never reported as a successful save',async()=>{
  const m=githubMock();m.breakReadback=true;
  await assert.rejects(saveReview(m.github,receipt(),candidates,hash),e=>e.status===502);
});
test('GitHub rejection keeps the event uncommitted and reports an actionable error',async()=>{
  const m=githubMock();m.putStatus=403;
  await assert.rejects(saveReview(m.github,receipt(),candidates,hash),e=>e.status===403);
  assert.equal(m.files.size,0);
});
test('sign-in uses PKCE, restricts the GitHub repository, and never returns GitHub credentials to the browser',async()=>{
  const f=await serviceFixture(),login=await f.login();
  assert.equal(login.authorization.searchParams.get('code_challenge_method'),'S256');
  assert.equal(f.oauthCalls[0].repository_id,REPOSITORY_ID);
  assert.equal(await digest(f.oauthCalls[0].code_verifier),login.authorization.searchParams.get('code_challenge'));
  assert.equal(login.user.id,OWNER_ID);assert.equal(login.access_token,undefined);assert.equal(login.refresh_token,undefined);
  const stored=f.db.db.prepare('SELECT value FROM bco_sessions').get().value;
  assert.equal(stored.includes('fake-access'),false);assert.equal(stored.includes('fake-refresh'),false);
  const config=f.db.db.prepare('SELECT value FROM bco_config').get().value;assert.equal(config.includes('fake-secret'),false);
  const saved=await f.request('/reviews',{method:'POST',body:receipt(),token:login.token});
  assert.equal(saved.status,200);assert.equal((await saved.json()).saved,true);
});
test('the callback and browser exchange are single-use and bound to the initiating browser',async()=>{
  const f=await serviceFixture(),login=await f.login();
  assert.equal((await f.request(`/auth/callback?state=${login.state}&code=fake-github-code`,{cookie:login.binding})).status,400);
  assert.equal((await f.request('/auth/exchange',{method:'POST',body:{code:login.code,verifier:login.verifier}})).status,401);
  const start=await f.request(`/auth/start?challenge=${await digest(random())}`),state=new URL(start.headers.get('location')).searchParams.get('state');
  assert.equal((await f.request(`/auth/callback?state=${state}&code=fake-github-code`,{cookie:'__Host-bco-flow=wrong'})).status,400);
  assert.equal(f.oauthCalls.length,1);
});
test('a copied callback code cannot be exchanged without its original proof',async()=>{
  const f=await serviceFixture(),verifier=random();
  const start=await f.request(`/auth/start?challenge=${await digest(verifier)}`),state=new URL(start.headers.get('location')).searchParams.get('state');
  const callback=await f.request(`/auth/callback?state=${state}&code=fake-github-code`,{cookie:start.headers.get('set-cookie').split(';')[0]});
  const code=new URL(callback.headers.get('location')).searchParams.get('bco_code');
  assert.equal((await f.request('/auth/exchange',{method:'POST',body:{code,verifier:random()}})).status,401);
});
test('unauthenticated writes, disallowed origins and sign-out cannot access the save API',async()=>{
  const f=await serviceFixture();
  assert.equal((await f.request('/reviews',{method:'POST',body:receipt()})).status,401);
  const login=await f.login();
  const foreign=await f.request('/reviews',{method:'POST',body:receipt(),token:login.token,origin:'https://other.example'});
  assert.equal(foreign.status,403);assert.equal(foreign.headers.get('access-control-allow-origin'),null);
  const preflight=await f.request('/reviews',{method:'OPTIONS'});assert.equal(preflight.headers.get('access-control-allow-origin'),REPORT_ORIGIN);
  await f.request('/logout',{method:'POST',token:login.token});
  assert.equal((await f.request('/reviews',{method:'POST',body:receipt(),token:login.token})).status,401);
  assert.equal(f.github.files.size,0);
});
test('expired sessions and oversized requests cannot write; revocation is checked on session read',async()=>{
  const f=await serviceFixture(),login=await f.login();
  const big=await f.request('/reviews',{method:'POST',body:{padding:'x'.repeat(20001)},token:login.token});assert.equal(big.status,413);
  f.github.canPush=false;assert.equal((await f.request('/session',{token:login.token})).status,403);f.github.canPush=true;
  await f.store.put('bco_sessions',await digest(login.token),{user:login.user},now()-1);
  assert.equal((await f.request('/reviews',{method:'POST',body:receipt(),token:login.token})).status,401);
  assert.equal(f.github.files.size,0);
});
test('refresh keeps GitHub tokens server-side and rechecks the account',async()=>{
  const f=await serviceFixture(),login=await f.login(),sessionId=await digest(login.token);
  const stored=await f.store.get('bco_sessions',sessionId);stored.value.token_expires=now()-1;
  await f.store.put('bco_sessions',sessionId,stored.value,stored.expires);
  const result=await f.request('/session',{token:login.token});assert.equal(result.status,200);
  assert.equal(f.oauthCalls[1].grant_type,'refresh_token');assert.equal(f.oauthCalls[1].refresh_token,'fake-refresh');
  assert.equal(JSON.stringify(await result.json()).includes('fake-access'),false);
});
test('setup is protected, shows exact permissions, and is disabled after configuration',async()=>{
  const fresh=await serviceFixture({configured:false});
  assert.equal((await fresh.request('/setup')).status,403);
  const allowed=await fresh.request(`/setup?ticket=${fresh.env.SETUP_KEY}`);assert.equal(allowed.status,200);
  const html=await allowed.text();assert.ok(html.includes('contents'));assert.ok(html.includes('vdubya/dod-bco-enrich'));assert.equal(html.includes(fresh.env.SETUP_KEY),false);
  assert.equal((await fresh.request('/reviews',{method:'POST',body:receipt()})).status,503);
  const configured=await serviceFixture();assert.equal((await configured.request(`/setup?ticket=${configured.env.SETUP_KEY}`)).status,409);
});
