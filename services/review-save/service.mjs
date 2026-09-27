import {Store} from './store.mjs';
import {GitHub,API,REPOSITORY_ID,OWNER_ID,saveReview} from './github.mjs';
import {Problem,requireValue,now,random,digest,validChallenge,readJSON,cookie,flowCookie} from './security.mjs';

export const REPORT='https://vdubya.github.io/dod-bco-enrich/';
export const REPORT_ORIGIN=new URL(REPORT).origin;
const SESSION_AGE=30*86400;
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const json=(data,status=200)=>Response.json(data,{status});
const redirect=(url,headers={})=>new Response(null,{status:303,headers:{Location:url,...headers}});
function page(title,text,extra=''){
  const favicon="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%232d5651'/%3E%3Ctext x='16' y='23' text-anchor='middle' fill='white' font-family='sans-serif' font-weight='bold' font-size='23'%3EB%3C/text%3E%3C/svg%3E";
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>${escape(title)} | DoD BCO</title><link rel="icon" href="${favicon}"><style>body{margin:0;background:#f4f6f5;color:#142e2b;font:17px/1.65 system-ui,sans-serif}main{max-width:620px;margin:12vh auto;padding:32px;background:white;border:1px solid #d8e0dc;border-radius:16px}h1{font-size:2rem;line-height:1.2}small{font-size:.8rem;letter-spacing:.14em;font-weight:700}a{color:#285c52}button{background:#2d5651;color:white;border:0;border-radius:8px;padding:15px 20px;font:inherit;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid #a58525;outline-offset:4px}@media(max-width:700px){main{margin:24px 12px;padding:24px}}</style></head><body><main><small>DOD BCO / GITHUB CONNECTION</small><h1>${escape(title)}</h1><p>${escape(text)}</p>${extra}<p><a href="${REPORT}">Return to the review report</a></p></main></body></html>`,{headers:{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action https://github.com; base-uri 'none'; frame-ancestors 'none'"}});
}
function safeHeaders(response,origin){
  const result=new Response(response.body,response);
  result.headers.set('Cache-Control','no-store');
  result.headers.set('Referrer-Policy','no-referrer');
  result.headers.set('X-Content-Type-Options','nosniff');
  result.headers.set('X-Frame-Options','DENY');
  result.headers.set('Vary','Origin');
  if(origin===REPORT_ORIGIN){
    result.headers.set('Access-Control-Allow-Origin',REPORT_ORIGIN);
    result.headers.set('Access-Control-Allow-Methods','GET, POST, OPTIONS');
    result.headers.set('Access-Control-Allow-Headers','Authorization, Content-Type');
  }
  return result;
}

// All application content and review receipts remain in GitHub. This store holds
// only encrypted authentication material and short-lived sign-in exchanges.
export function createService({candidates,datasetHash,fetcher=(...args)=>globalThis.fetch(...args)}){
  async function tokenExchange(app,parameters){
    const r=await fetcher('https://github.com/login/oauth/access_token',{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({client_id:app.client_id,client_secret:app.client_secret,...parameters}),signal:AbortSignal.timeout(20000),redirect:'manual'});
    let data;try{data=await r.json();}catch{data=null;}
    requireValue(r.ok && data?.access_token && !data.error,401,'GitHub sign-in could not be completed. Please sign in again.');
    return {access_token:data.access_token,refresh_token:data.refresh_token||null,token_expires:now()+(data.expires_in||8*3600),refresh_expires:now()+(data.refresh_token_expires_in||0)};
  }
  async function sessionFor(request,store,app){
    const token=request.headers.get('authorization')?.match(/^Bearer ([A-Za-z0-9_-]{43})$/)?.[1];
    requireValue(token,401,'Sign in to GitHub to save your review.');
    const id=await digest(token),stored=await store.get('bco_sessions',id);
    requireValue(stored,401,'Your connection expired. Sign in again; your draft is retained.');
    let value=stored.value;
    if(value.token_expires<=now()+60){
      requireValue(value.refresh_token && value.refresh_expires>now(),401,'Your GitHub connection expired. Sign in again.');
      const refreshed=await tokenExchange(app,{grant_type:'refresh_token',refresh_token:value.refresh_token});
      const identity=await new GitHub(refreshed.access_token,fetcher).identity();
      requireValue(identity.id===value.user.id,401,'The GitHub account changed. Sign in again.');
      value={...value,...refreshed,user:identity};
      await store.put('bco_sessions',id,value,stored.expires);
    }
    return {id,...value,expires:stored.expires};
  }
  async function route(request,env,diagnostic){
    const url=new URL(request.url),origin=request.headers.get('origin');
    requireValue(env.SERVICE_URL && new URL(env.SERVICE_URL).protocol==='https:',503,'The direct-save service is not configured.');
    const base=new URL(env.SERVICE_URL).origin;
    requireValue(url.origin===base,400,'Unexpected service address.');
    requireValue(!origin || origin===REPORT_ORIGIN || origin===base,403,'This origin is not allowed.');
    if(request.method==='OPTIONS')return new Response(null,{status:204});
    const store=new Store(env.DB,env.SESSION_KEY);
    const app=await store.config();

    if(url.pathname==='/' && request.method==='GET')return page('Save your reviews to GitHub','This connection serves the DoD BCO review report. Your report and saved review records are kept in vdubya/dod-bco-enrich.');
    if(url.pathname==='/health' && request.method==='GET')return json({service:'DoD BCO review saves',ready:!!app,repository:'vdubya/dod-bco-enrich',branch:'dod-bco'});
    if(url.pathname==='/setup' && request.method==='GET'){
      requireValue(!app,409,'The GitHub connection is already configured.');
      const ticket=url.searchParams.get('ticket');
      requireValue(validChallenge(ticket) && validChallenge(env.SETUP_KEY) && await digest(ticket)===await digest(env.SETUP_KEY),403,'This setup link is not valid.');
      const state=random(),binding=random();
      await store.put('bco_flows',await digest(state),{type:'setup',binding:await digest(binding)},now()+3600);
      const manifest={name:'DoD BCO Reviews vdubya',url:REPORT,description:'Save source-linked DoD BCO review decisions to vdubya/dod-bco-enrich.',public:false,redirect_url:`${base}/setup/callback`,callback_urls:[`${base}/auth/callback`],setup_url:`${base}/setup/installed`,hook_attributes:{url:`${base}/webhook`,active:false},default_permissions:{contents:'write',metadata:'read'},default_events:[],request_oauth_on_install:false};
      const response=page('Connect GitHub saving','Create a private GitHub App, then install it only on vdubya/dod-bco-enrich. The app requests repository contents read and write access. The service permits only new review-event files.',`<form method="post" action="https://github.com/settings/apps/new?state=${state}"><input type="hidden" name="manifest" value="${escape(JSON.stringify(manifest))}"><button type="submit">Review GitHub App permissions</button></form><details><summary>Resume an app already created</summary><p>If the final connection step failed, use the code from its callback within one hour. This does not create another app.</p><form method="get" action="/setup/callback"><input type="hidden" name="state" value="${state}"><label>GitHub setup code <input name="code" required minlength="8" maxlength="200" autocomplete="off"></label><button type="submit">Finish existing app connection</button></form></details>`);
      response.headers.set('Content-Security-Policy',response.headers.get('Content-Security-Policy').replace('form-action https://github.com',"form-action 'self' https://github.com"));
      response.headers.set('Set-Cookie',flowCookie(binding,3600));return response;
    }
    if(url.pathname==='/setup/callback' && request.method==='GET'){
      requireValue(!app,409,'The GitHub connection is already configured.');
      const state=url.searchParams.get('state'),code=url.searchParams.get('code');
      requireValue(validChallenge(state) && /^[a-zA-Z0-9_\-]{8,200}$/.test(code||''),400,'The setup callback is invalid.');
      diagnostic.step='setup-flow';
      const flow=await store.get('bco_flows',await digest(state),true);
      requireValue(flow?.value.type==='setup' && flow.value.binding===await digest(cookie(request,'__Host-bco-flow')||''),400,'The setup session expired. Start again from the setup link.');
      diagnostic.step='manifest-conversion';
      const r=await fetcher(`${API}/app-manifests/${code}/conversions`,{method:'POST',headers:{Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'DoD-BCO-Review-Save'},signal:AbortSignal.timeout(20000),redirect:'manual'});
      let data;try{data=await r.json();}catch{throw new Problem(502,'GitHub did not return a valid app response. Resume the existing app connection.');}
      requireValue(r.ok && data.owner?.id===OWNER_ID && data.client_id && data.client_secret && /^https:\/\/github\.com\/apps\/[a-z0-9-]+$/.test(data.html_url||''),403,'The app must be created by the vdubya repository owner.');
      requireValue(data.permissions?.contents==='write' && Object.keys(data.permissions).every(k=>['contents','metadata'].includes(k)),403,'The app permissions do not match this service.');
      // The manifest also returns a PEM key and webhook secret. Neither is used
      // or retained: writes use the signed-in user's repository-limited grant.
      diagnostic.step='app-storage';
      await store.configure({id:data.id,slug:data.slug,client_id:data.client_id,client_secret:data.client_secret,html_url:data.html_url});
      return redirect(`${data.html_url}/installations/new`,{'Set-Cookie':flowCookie('',0)});
    }
    if(url.pathname==='/setup/installed' && request.method==='GET')return page('GitHub connection installed','Return to the report and sign in to begin saving directly.');
    requireValue(app,503,'Direct saving is being connected. Your draft stays on this device.');

    if(url.pathname==='/auth/start' && request.method==='GET'){
      const challenge=url.searchParams.get('challenge');
      requireValue(validChallenge(challenge),400,'A valid sign-in challenge is required.');
      const state=random(),binding=random(),verifier=random();
      await store.cleanup();
      await store.put('bco_flows',await digest(state),{type:'auth',binding:await digest(binding),verifier,challenge},now()+600);
      const target=new URL('https://github.com/login/oauth/authorize');
      for(const [k,v] of Object.entries({client_id:app.client_id,redirect_uri:`${base}/auth/callback`,state,code_challenge:await digest(verifier),code_challenge_method:'S256'}))target.searchParams.set(k,v);
      return redirect(target.href,{'Set-Cookie':flowCookie(binding)});
    }
    if(url.pathname==='/auth/callback' && request.method==='GET'){
      const state=url.searchParams.get('state');
      requireValue(validChallenge(state),400,'The sign-in callback is invalid.');
      const flow=await store.get('bco_flows',await digest(state),true);
      requireValue(flow?.value.type==='auth' && flow.value.binding===await digest(cookie(request,'__Host-bco-flow')||''),400,'The sign-in session expired. Return to the report and try again.');
      if(url.searchParams.has('error'))return redirect(`${REPORT}?bco_auth_error=cancelled`,{'Set-Cookie':flowCookie('',0)});
      const code=url.searchParams.get('code');
      requireValue(/^[a-zA-Z0-9_\-]{8,200}$/.test(code||''),400,'The sign-in code is invalid.');
      const tokens=await tokenExchange(app,{code,redirect_uri:`${base}/auth/callback`,code_verifier:flow.value.verifier,repository_id:REPOSITORY_ID});
      const user=await new GitHub(tokens.access_token,fetcher).identity();
      const token=random(),exchange=random(),expires=now()+SESSION_AGE;
      await store.put('bco_sessions',await digest(token),{...tokens,user},expires);
      await store.put('bco_exchanges',await digest(exchange),{token,expires,user,challenge:flow.value.challenge},now()+60);
      return redirect(`${REPORT}?bco_code=${exchange}`,{'Set-Cookie':flowCookie('',0)});
    }
    if(url.pathname==='/auth/exchange' && request.method==='POST'){
      const body=await readJSON(request,2000);
      requireValue(validChallenge(body.code) && validChallenge(body.verifier),400,'The sign-in exchange is invalid.');
      const exchange=await store.get('bco_exchanges',await digest(body.code),true);
      requireValue(exchange && exchange.value.challenge===await digest(body.verifier),401,'The sign-in link expired or belongs to another browser. Sign in again.');
      const {token,expires,user}=exchange.value;
      return json({token,expires,user});
    }
    if(url.pathname==='/session' && request.method==='GET'){
      const session=await sessionFor(request,store,app);
      // Read-back catches revocation even while the service session is unexpired.
      const user=await new GitHub(session.access_token,fetcher).identity();
      return json({user,expires:session.expires});
    }
    if(url.pathname==='/logout' && request.method==='POST'){
      const token=request.headers.get('authorization')?.match(/^Bearer ([A-Za-z0-9_-]{43})$/)?.[1];
      if(token)await store.remove('bco_sessions',await digest(token));
      return json({signed_out:true});
    }
    if(url.pathname==='/reviews' && request.method==='POST'){
      const session=await sessionFor(request,store,app);
      const input=await readJSON(request);
      return json(await saveReview(new GitHub(session.access_token,fetcher),input,candidates,datasetHash));
    }
    throw new Problem(404,'This service endpoint does not exist.');
  }
  return {async fetch(request,env){
    const origin=request.headers.get('origin');let response;
    const diagnostic={step:'request'};
    try{response=await route(request,env,diagnostic);}
    catch(error){
      if(!(error instanceof Problem))console.error('bco-runtime-failure',{step:diagnostic.step,name:error.name,detail:String(error.message).replace(/https?:\/\/\S+/g,'[url]').replace(/[A-Za-z0-9_\-+/=]{16,}/g,'[redacted]').slice(0,240)});
      const status=error instanceof Problem?error.status:503;
      const message=error instanceof Problem?error.message:'The save service is temporarily unavailable. Your draft is retained; retry safely.';
      const html=request.headers.get('accept')?.includes('text/html');
      response=html?page('Connection needs attention',message):json({error:message},status);
      if(html)response=new Response(response.body,{status,headers:response.headers});
    }
    return safeHeaders(response,origin);
  }};
}
