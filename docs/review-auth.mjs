import {REPO,eventPath,sameReviewContent} from './review-core.mjs';
const SESSION='dod-bco-save-connection-v1';
const FLOW='dod-bco-sign-in-v1';
const opaque=value=>typeof value==='string' && /^[A-Za-z0-9_-]{43}$/.test(value);
const encode=bytes=>btoa(Array.from(new Uint8Array(bytes),n=>String.fromCharCode(n)).join('')).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');

// The browser holds only a narrow service session. GitHub access and refresh
// tokens stay encrypted on the service and are never returned to this module.
export function createConnection(serviceURL,{fetcher=fetch,storage=localStorage,flowStorage=sessionStorage,navigate=url=>location.assign(url)}={}) {
  const base=serviceURL?new URL(serviceURL):null;
  if(base && (base.protocol!=='https:' || base.pathname!=='/' || base.search || base.hash || base.username || base.password))throw Error('Invalid save service configuration.');
  let session=null;
  try{const saved=JSON.parse(storage.getItem(SESSION)||'null');if(opaque(saved?.token) && saved.expires*1000>Date.now())session=saved;}catch{}
  function forget(){session=null;try{storage.removeItem(SESSION);}catch{}}
  async function request(path,{method='GET',body,authenticated=true}={}){
    if(!base)throw Error('Direct saving is awaiting its GitHub connection. Your draft is retained.');
    const response=await fetcher(new URL(path,base).href,{method,headers:{...(body?{'Content-Type':'application/json'}:{}),...(authenticated && session?{Authorization:`Bearer ${session.token}`}:{})},...(body?{body:JSON.stringify(body)}:{}),credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(45000),redirect:'error'});
    let result;try{result=await response.json();}catch{throw Error('The save service did not return a valid response. Your draft is retained.');}
    if(!response.ok){if(response.status===401)forget();const error=Error(result.error||'The save could not be completed. Retry safely.');error.status=response.status;throw error;}
    return result;
  }
  return {
    get configured(){return !!base;},
    get user(){return session?.user||null;},
    async restore(){
      if(!session || !base)return null;
      try{const result=await request('/session');session={...session,...result};return session.user;}
      catch(error){if([401,403].includes(error.status))forget();throw error;}
    },
    async signIn(){
      if(!base)throw Error('Direct saving is awaiting its GitHub connection. Your draft is retained.');
      const verifier=encode(crypto.getRandomValues(new Uint8Array(32)));
      const challenge=encode(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier)));
      try{flowStorage.setItem(FLOW,JSON.stringify({verifier,created:Date.now()}));}
      catch{throw Error('Allow browser storage to sign in. Your current draft has not been sent.');}
      navigate(new URL(`/auth/start?challenge=${challenge}`,base).href);
    },
    async finishSignIn(search){
      const query=new URLSearchParams(search);
      if(query.has('bco_auth_error')){flowStorage.removeItem(FLOW);throw Error('GitHub sign-in was cancelled. Your draft is retained.');}
      const code=query.get('bco_code');if(!code)return false;
      let flow;try{flow=JSON.parse(flowStorage.getItem(FLOW)||'null');}catch{}
      flowStorage.removeItem(FLOW);
      if(!opaque(code) || !opaque(flow?.verifier) || Date.now()-flow.created>600000)throw Error('The sign-in session expired. Sign in again; your draft is retained.');
      const result=await request('/auth/exchange',{method:'POST',body:{code,verifier:flow.verifier},authenticated:false});
      if(!opaque(result.token) || result.user?.id!==6257997 || !(result.expires*1000>Date.now()))throw Error('The GitHub connection could not be verified.');
      session=result;
      try{storage.setItem(SESSION,JSON.stringify(session));}catch{/* An in-memory session can still save this draft. */}
      return true;
    },
    async save(event){
      if(!session){const error=Error('Sign in to GitHub to save your review.');error.status=401;throw error;}
      const result=await request('/reviews',{method:'POST',body:event});
      if(result.saved!==true || !/^[a-f0-9]{40}$/.test(result.commit||'') || !sameReviewContent(result.event,event) || result.event.authenticated_reviewer?.id!==session.user.id || result.url!==`https://github.com/${REPO}/blob/${result.commit}/${eventPath(event.event_id)}`)throw Error('The commit confirmation did not match your review. Retry to check the same record.');
      return result;
    },
    async signOut(){await request('/logout',{method:'POST'});forget();}
  };
}
