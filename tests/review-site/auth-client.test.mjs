import test from 'node:test';
import assert from 'node:assert/strict';
import {createConnection} from '../../docs/review-auth.mjs';
import {sameReviewContent} from '../../docs/review-core.mjs';
const storage=()=>{const values=new Map();return {getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};};
const opaque='a'.repeat(43),code='b'.repeat(43),user={id:6257997,login:'vdubya',name:'Van Woods'};
const event={schema_version:1,record_type:'persistence_check',event_id:'00000000-0000-4000-8000-000000000001',created_at:'2026-09-26T20:00:00Z',dataset_sha256:'test',purpose:'Technical save verification; no vocabulary decision'};
const commit='a'.repeat(40),confirmed={saved:true,event:{...event,authenticated_reviewer:{id:user.id,login:user.login}},commit,url:`https://github.com/vdubya/dod-bco-enrich/blob/${commit}/docs/review-events/${event.event_id}.json`};
function fixture(){
  const local=storage(),flow=storage(),calls=[];let navigation;
  const f={response:confirmed,status:200,local,flow,calls};
  f.fetch=async(url,options)=>{
    calls.push({url,options});
    if(url.endsWith('/auth/exchange'))return Response.json({token:opaque,expires:Math.floor(Date.now()/1000)+3600,user});
    if(url.endsWith('/session'))return Response.json({user,expires:Math.floor(Date.now()/1000)+3600});
    return Response.json(f.response,{status:f.status});
  };
  f.client=()=>createConnection('https://save.example.test',{storage:local,flowStorage:flow,fetcher:f.fetch,navigate:url=>{navigation=url;}});
  f.navigate=()=>navigation;
  f.login=async client=>{await client.signIn();await client.finishSignIn(`?bco_code=${code}`);};
  return f;
}
test('sign-in redirects with a challenge, returns automatically and survives a reload',async()=>{
  const f=fixture(),client=f.client();await f.login(client);
  const target=new URL(f.navigate());assert.equal(target.pathname,'/auth/start');assert.equal(target.searchParams.get('challenge').length,43);
  assert.equal(client.user.id,user.id);assert.equal(f.calls[0].options.credentials,'omit');
  const reloaded=f.client();await reloaded.restore();assert.equal(reloaded.user.id,user.id);
  const saved=await reloaded.save(event);assert.deepEqual(saved,confirmed);
  const request=f.calls.at(-1);assert.equal(request.url,'https://save.example.test/reviews');assert.equal(request.options.headers.Authorization,`Bearer ${opaque}`);assert.deepEqual(JSON.parse(request.options.body),event);
});
test('failed saves preserve the event and expired connections require sign-in',async()=>{
  const f=fixture(),client=f.client();await f.login(client);
  f.response={error:'Sign in again'};f.status=401;
  const before=JSON.stringify(event);await assert.rejects(client.save(event),e=>e.status===401);
  assert.equal(client.user,null);assert.equal(JSON.stringify(event),before);
  await assert.rejects(client.save(event),e=>e.status===401);
});
test('a mismatched receipt, commit link or verified identity cannot be shown as saved',async()=>{
  for(const response of [{...confirmed,event:{...confirmed.event,purpose:'different'}},{...confirmed,commit:'not-a-sha'},{...confirmed,url:'https://other.example/record'},{...confirmed,event:{...confirmed.event,authenticated_reviewer:{id:7}}},{...confirmed,saved:false}]){
    const f=fixture(),client=f.client();await f.login(client);f.response=response;
    await assert.rejects(client.save(event),/confirmation did not match/);
  }
});
test('saved-content equality includes the event timestamp and every review field',()=>{
  assert.equal(sameReviewContent(confirmed.event,event),true);
  assert.equal(sameReviewContent({...confirmed.event,created_at:'2026-09-27T00:00:00Z'},event),false);
  assert.equal(sameReviewContent({...confirmed.event,unexpected:'field'},event),false);
});
test('a callback without its original browser proof is rejected without a network request',async()=>{
  const f=fixture(),client=f.client();await assert.rejects(client.finishSignIn(`?bco_code=${code}`),/session expired/);assert.equal(f.calls.length,0);
});
test('an unconfigured service retains local work without offering a copy-and-paste handoff',async()=>{
  const client=createConnection(null,{storage:storage(),flowStorage:storage(),fetcher:()=>assert.fail('No network expected'),navigate:()=>assert.fail('No navigation expected')});
  assert.equal(client.configured,false);await assert.rejects(client.signIn(),/draft is retained/);
});
