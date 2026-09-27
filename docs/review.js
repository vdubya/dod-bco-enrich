import {REPO,BRANCH,EVENT_DIR,validateEvent,resolveReviews,reusePendingSave,eventPath,sameReviewContent} from './review-core.mjs?v=direct-save-1';
import {createConnection} from './review-auth.mjs?v=direct-save-1';
const $ = id => document.getElementById(id);
const esc = value => String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const labels={pending:'Awaiting review',accepted:'Accepted assertion',rejected:'Rejected candidate',needs_revision:'Needs revision',deferred:'Deferred',conflict:'Conflicting reviews',unverified:'Unverified reviews'};
const key='dod-bco-review-drafts-v1';
const saveKey='dod-bco-prepared-save-v1';
let candidates=[],units={},manifest={},events=[],resolution=null,remoteReady=false,commit='',active=null,baseHeads=[],drafts={},storageOK=true;
let preparedSave=null,connection=null,saving=false,lastSave=null;
// Remove the one-use exchange code before any external repository requests.
const signInSearch=location.search,signInQuery=new URLSearchParams(signInSearch);
if(signInQuery.has('bco_code') || signInQuery.has('bco_auth_error')){
  signInQuery.delete('bco_code');signInQuery.delete('bco_auth_error');
  history.replaceState(null,'',location.pathname+(signInQuery.size?'?'+signInQuery:'')+location.hash);
}
try { drafts=JSON.parse(localStorage.getItem(key)||'{}'); if(!drafts || Array.isArray(drafts) || typeof drafts!=='object') drafts={}; } catch {storageOK=false;}
try { preparedSave=JSON.parse(localStorage.getItem(saveKey)||'null'); } catch { /* Existing drafts remain available. */ }
function storeDrafts(){try{localStorage.setItem(key,JSON.stringify(drafts));return true;}catch{storageOK=false;return false;}}
function storePrepared(){try{if(preparedSave)localStorage.setItem(saveKey,JSON.stringify(preparedSave));else localStorage.removeItem(saveKey);return true;}catch{return false;}}
function clearPrepared(){preparedSave=null;storePrepared();$('resume-save').hidden=true;}
function showSyncSummary(confirmed=false){
  $('resume-save').hidden=!preparedSave;
  $('sync-title').textContent=confirmed?'Saved to GitHub':preparedSave?'A review is ready to save':'Reviews loaded from GitHub';
  $('sync-dot').className=preparedSave?'sync-dot':'sync-dot ready';
  $('sync-detail').textContent=`${events.filter(e=>e.record_type==='definition_review').length} review events saved · version ${commit.slice(0,7)} · ${REPO}. ${preparedSave?'Choose Save pending review to finish.':'Each saved review becomes a GitHub commit.'}`;
}
function statusFor(id){return resolution?.states.get(id)||{status:'pending',history:[],heads:[],latest:null};}
function blobLink(e){return `https://github.com/${REPO}/blob/${commit}/${eventPath(e.event_id)}`;}
function sourceLink(c){try{const u=new URL(c.source.source_url);return u.protocol==='https:'&&u.hostname==='digital.wbdg.org'?u.href:'#';}catch{return '#';}}
function render(){
  const q=$('search').value.trim().toLowerCase(), source=$('source').value, kind=$('kind').value, status=$('status').value;
  const filtered=candidates.filter(c=>{
    const text=[c.label_proposed,c.source.designation,c.section_path.join(' '),c.pilot_review.review_focus,...c.evidence.map(e=>e.source_text_exact),...c.context_unit_ids.map(id=>units[id]?.text_exact||'')].join(' ').toLowerCase();
    return (!q||text.includes(q))&&(!source||source===c.source.designation)&&(!kind||kind===c.record_type)&&(!status||(status==='draft'?!!drafts[c.candidate_id]:status===statusFor(c.candidate_id).status));
  });
  $('result-count').textContent=`${filtered.length} of ${candidates.length} assertions`;
  $('cards').innerHTML=filtered.map(c=>{
    const state=statusFor(c.candidate_id), last=state.latest;
    const context=[...new Set([...c.evidence.map(e=>e.unit_id),...c.context_unit_ids])];
    const history=state.history.slice().sort((a,b)=>a.created_at.localeCompare(b.created_at));
    const saved=last?`<div class="saved-review"><strong>${esc(labels[last.status])} · ${esc(last.reviewer)}</strong>${last.rationale?`<p>${esc(last.rationale)}</p>`:''}${last.scope_note?`<p><b>Reviewed scope:</b> ${esc(last.scope_note)}</p>`:''}${last.proposed_label?`<p><b>Editorial label:</b> ${esc(last.proposed_label)}</p>`:''}${last.proposed_definition?`<p><b>Editorial definition:</b> ${esc(last.proposed_definition)}</p>`:''}<a href="${blobLink(last)}" target="_blank" rel="noopener noreferrer">View saved record ↗</a></div>`:'';
    const conflict=state.status==='conflict'?'<p class="error">Competing or incomplete review history. Inspect the saved records before recording a resolution.</p>':'';
    return `<article id="${esc(c.candidate_id)}" data-candidate="${esc(c.candidate_id)}"><div class="card-top"><div class="source-meta"><b>${String(candidates.indexOf(c)+1).padStart(2,'0')} / ${esc(c.source.designation)}</b> ${esc(c.source.version_label)}</div><span class="badge ${esc(state.status)}">${resolution?esc(labels[state.status]):'Not synced'}</span></div><h3><a href="#${esc(c.candidate_id)}">${esc(c.label_proposed)}</a></h3><span class="kind">${esc(c.record_type.replaceAll('_',' '))}</span><p class="section">${esc(c.section_path.join(' › '))}</p>${c.evidence.map(e=>`<blockquote class="quote">${esc(e.source_text_exact)}</blockquote>`).join('')}<div class="focus"><strong>Review focus</strong><p>${esc(c.pilot_review.review_focus)}</p></div><details class="evidence"><summary>Source context &amp; exact locations <span>Edition and provenance</span></summary>${context.map(id=>`<p class="quote">${esc(units[id].text_exact)}</p><p class="locator">${esc(units[id].json_pointer)}</p>`).join('')}<details><summary>Document applicability context</summary>${c.scope.source_document_scope_unit_ids.map(id=>`<p class="quote">${esc(units[id].text_exact)}</p><p class="locator">${esc(units[id].json_pointer)}</p>`).join('')}</details><p class="locator">Source SHA-256: ${esc(c.source.source_sha256)}<br>Candidate: ${esc(c.candidate_id)}</p><p class="small">Source wording is preserved. Referenced external standards have not been independently validated in this pilot.</p></details>${saved}${conflict}${history.length?`<details class="history"><summary>Review history <span>${history.length} saved events</span></summary><ol>${history.map(e=>`<li><strong>${esc(labels[e.status])}</strong> · ${esc(e.reviewer)} · ${esc(e.created_at)}<br>${esc(e.rationale)}<br><a href="${blobLink(e)}" target="_blank" rel="noopener noreferrer">Versioned record ↗</a></li>`).join('')}</ol></details>`:''}<footer class="card-footer"><a href="${esc(sourceLink(c))}" target="_blank" rel="noopener noreferrer">Open source edition ↗</a><div>${drafts[c.candidate_id]?'<span class="draft-badge">Draft on this device</span>':''}<button type="button" data-review="${esc(c.candidate_id)}">${drafts[c.candidate_id]?'Continue draft':history.length?'Review again':'Review assertion'}</button></div></footer></article>`;
  }).join('')||'<p class="empty">No assertions match these filters.</p>';
  if(resolution){
    const states=[...resolution.states.values()];
    $('reviewed').textContent=states.filter(s=>s.history.length && !['pending','conflict','unverified'].includes(s.status)).length;
    $('accepted').textContent=states.filter(s=>s.status==='accepted').length;
  }
}
async function jsonFetch(url){
  const response=await fetch(url,{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(20000)});
  if(!response.ok) throw Error(response.status===403||response.status===429?'GitHub’s public read limit was reached. Try refreshing later.':`Could not load the repository snapshot (HTTP ${response.status}).`);
  return response.json();
}
async function sync(){
  if(!candidates.length)return;
  remoteReady=false; $('refresh').disabled=true; $('sync-title').textContent='Checking GitHub…'; $('sync-dot').className='sync-dot';
  try{
    const ref=await jsonFetch(`https://api.github.com/repos/${REPO}/git/ref/heads/${BRANCH}`);
    const nextCommit=ref.object?.sha;
    if(!/^[a-f0-9]{40}$/.test(nextCommit||''))throw Error('GitHub did not return a valid branch version.');
    const listing=await jsonFetch(`https://api.github.com/repos/${REPO}/contents/${EVENT_DIR}?ref=${nextCommit}`);
    if(!Array.isArray(listing)||listing.length>=1000)throw Error('The review listing is incomplete; no current decisions have been inferred.');
    const files=listing.filter(file=>file.type==='file'&&file.name.endsWith('.json'));
    const loaded=[];
    // Pin every file to the same commit and bound concurrent downloads.
    for(let i=0;i<files.length;i+=6){
      const batch=await Promise.all(files.slice(i,i+6).map(async file=>{
        if(!/^[a-f0-9-]{36}\.json$/i.test(file.name))throw Error('A review event has an unexpected filename.');
        const r=await fetch(`https://raw.githubusercontent.com/${REPO}/${nextCommit}/${EVENT_DIR}/${file.name}`,{credentials:'omit',signal:AbortSignal.timeout(20000)});
        if(!r.ok)throw Error('A review file could not be loaded. The snapshot has not been applied.');
        const text=await r.text(); if(text.length>20000)throw Error('A review record exceeds the allowed size.');
        const e=JSON.parse(text); if(file.name!==`${e.event_id}.json`)throw Error('A review event identity does not match its filename.');
        return e;
      }));loaded.push(...batch);
    }
    const next=resolveReviews(loaded,candidates,manifest.dataset_sha256);
    events=loaded; commit=nextCommit; resolution=next;
    if(next.issues.length)throw Error(`Review validation needs attention: ${[...new Set(next.issues)].join(' ')}`);
    remoteReady=true;
    const found=preparedSave && loaded.find(e=>e.event_id===preparedSave.event_id);
    const confirmed=!!found && sameReviewContent(found,preparedSave);
    if(confirmed){
      lastSave={event:found,commit:nextCommit,url:`https://github.com/${REPO}/blob/${nextCommit}/${eventPath(found.event_id)}`};
      if(found.candidate_id)delete drafts[found.candidate_id];
      clearPrepared();storeDrafts();
      if($('save-dialog').open)showSaved();
    }
    showSyncSummary(confirmed);
    const checks=next.checks.slice().sort((a,b)=>a.created_at.localeCompare(b.created_at));
    if(checks.length){$('check-result').innerHTML=`Save verified: <a href="${blobLink(checks.at(-1))}" target="_blank" rel="noopener noreferrer">view repository receipt ↗</a>`;}
  }catch(error){
    $('sync-title').textContent='Saved reviews could not be refreshed'; $('sync-dot').className='sync-dot error';
    $('sync-detail').textContent=`${error.message} ${commit?'The display retains the last loaded snapshot.':'Saved review status is not yet known.'}`;
  }finally{ $('refresh').disabled=false; render(); }
}
const form=$('review-form');
const fields=['status','reviewer','scope_note','rationale','proposed_label','proposed_definition'];
function formValues(){return Object.fromEntries(fields.map(name=>[name,form.elements.namedItem(name).value]));}
function updateDraft(){
  if(!active)return;
  const values=formValues();
  const previous=drafts[active.candidate_id];
  const unchanged=previous && fields.every(name=>previous[name]===values[name]);
  if(preparedSave?.candidate_id===active.candidate_id && fields.some(name=>preparedSave[name]!==values[name])){clearPrepared();if(remoteReady)showSyncSummary();}
  drafts[active.candidate_id]={...values,supersedes:baseHeads};
  if(unchanged && previous.pending_event_id)drafts[active.candidate_id].pending_event_id=previous.pending_event_id;
  const saved=storeDrafts();$('draft-state').textContent=saved?'Draft saved on this device. It is not in GitHub yet.':'Browser draft storage is unavailable. Keep this window open until you save to GitHub.';
}
function openReview(id){
  if(saving){if(!$('save-dialog').open)$('save-dialog').showModal();return;}
  active=candidates.find(c=>c.candidate_id===id); if(!active)return;
  const state=statusFor(id), draft=drafts[id];
  baseHeads=draft?.supersedes || state.heads.map(e=>e.event_id);
  const values=draft||state.latest||{};
  fields.forEach(name=>{form.elements.namedItem(name).value=values[name]||(name==='reviewer'?connection?.user?.name?.slice(0,80)||'':'');});
  $('dialog-title').textContent=active.label_proposed; $('dialog-source').textContent=`${active.source.designation} · ${active.source.version_label} · ${active.section_path.at(-1)}`;
  $('form-error').textContent='';$('draft-state').textContent=draft?'Draft restored from this device.':'No new decision has been saved.';
  $('review-dialog').showModal();
}
function updateConnection(){
  $('sign-in').hidden=!!connection?.user;
  $('sign-out').hidden=!connection?.user;
  $('account-state').textContent=connection?.user?`Saving as @${connection.user.login}`:'Sign in once to save directly from this report.';
  $('save-now').textContent=connection?.user?'Save to GitHub':'Sign in and save';
  $('sign-out').disabled=saving;
  $('save-now').disabled=saving;
  $('check-save').disabled=saving;
}
function showSavePanel(message='Your draft is ready. Saving creates a versioned record in your GitHub repository.'){
  if(!preparedSave)return;
  $('save-title').textContent='Save to GitHub';
  $('save-summary').textContent=preparedSave.record_type==='persistence_check'?'Technical save check. No vocabulary decision.':`${candidates.find(c=>c.candidate_id===preparedSave.candidate_id).label_proposed} · ${labels[preparedSave.status]} · ${preparedSave.reviewer}`;
  $('save-status').textContent=message;
  $('save-receipt').hidden=true;
  $('save-now').hidden=false;
  updateConnection();
  if(!$('save-dialog').open)$('save-dialog').showModal();
}
async function prepareAndSave(event){
  preparedSave=event;
  const retained=storePrepared();
  showSyncSummary();
  showSavePanel();
  if(!retained && !connection?.user){$('save-status').textContent='Allow browser storage before signing in so this draft survives the sign-in step.';return;}
  await savePrepared();
}
async function savePrepared(){
  if(saving || !preparedSave)return;
  showSavePanel();saving=true;updateConnection();
  try{
    if(!remoteReady){await sync();if(!preparedSave){showSaved();return;}if(!remoteReady)throw Error('Saved reviews could not be checked. Refresh successfully, then retry. Your draft is retained.');}
    validateEvent(preparedSave,candidates,manifest.dataset_sha256);
    if(!connection?.user){
      if(!storePrepared())throw Error('Allow browser storage before signing in so this draft survives the sign-in step.');
      $('save-status').textContent='Opening GitHub sign-in. Your draft will be saved when you return.';
      if(!connection)throw Error('The GitHub save connection is not ready yet. Your draft is retained.');
      await connection.signIn();return;
    }
    $('save-status').textContent='Saving your review to GitHub and checking the committed file…';
    const result=await connection.save(preparedSave);
    lastSave=result;
    if(result.event.candidate_id)delete drafts[result.event.candidate_id];
    clearPrepared();storeDrafts();
    await sync();showSaved();
  }catch(error){
    $('save-status').textContent=error.name==='TimeoutError'?'Confirmation timed out. Your draft is retained. Retry to check the same review without creating a duplicate.':error.message;
  }finally{saving=false;updateConnection();render();}
}
function showSaved(){
  if(!lastSave)return;
  $('save-title').textContent='Saved to GitHub';
  $('save-status').textContent=`Your ${lastSave.event.record_type==='persistence_check'?'technical save check':'review'} is committed to ${REPO}.`;
  $('save-receipt').href=lastSave.url;$('save-receipt').textContent=`View commit record ${lastSave.commit.slice(0,7)} ↗`;$('save-receipt').hidden=false;
  $('save-now').hidden=true;
  $('sync-title').textContent='Saved to GitHub';$('sync-dot').className='sync-dot ready';
  if(!remoteReady)$('sync-detail').textContent=`Commit ${lastSave.commit.slice(0,7)} was confirmed. The review list could not refresh; try refreshing later.`;
}
form.addEventListener('input',updateDraft);
form.addEventListener('change',updateDraft);
form.addEventListener('submit',async event=>{
  event.preventDefault(); $('form-error').textContent='';
  try{
    if(!remoteReady)throw Error('Refresh saved reviews successfully before saving a decision. Your local draft is retained.');
    const e=reusePendingSave({schema_version:1,record_type:'definition_review',event_id:crypto.randomUUID(),created_at:new Date().toISOString(),candidate_id:active.candidate_id,dataset_sha256:manifest.dataset_sha256,source_sha256:active.source.source_sha256,source_version_id:active.source.version_id,supersedes:baseHeads,...formValues()},preparedSave);
    validateEvent(e,candidates,manifest.dataset_sha256);
    drafts[active.candidate_id]={...formValues(),supersedes:baseHeads,pending_event_id:e.event_id};storeDrafts();
    $('review-dialog').close();await prepareAndSave(e);render();
  }catch(error){$('form-error').textContent=error.message;}
});
$('close-dialog').addEventListener('click',()=>{$('review-dialog').close();render();});
$('review-dialog').addEventListener('close',()=>{active=null;render();});
$('discard-draft').addEventListener('click',()=>{if(preparedSave?.candidate_id===active.candidate_id){clearPrepared();if(remoteReady)showSyncSummary();}delete drafts[active.candidate_id];storeDrafts();$('review-dialog').close();});
$('cards').addEventListener('click',event=>{const button=event.target.closest('[data-review]');if(button)openReview(button.dataset.review);});
for(const id of ['search','source','kind','status'])$(id).addEventListener(id==='search'?'input':'change',render);
$('refresh').addEventListener('click',sync);
$('resume-save').addEventListener('click',()=>showSavePanel());
$('close-save').addEventListener('click',()=>$('save-dialog').close());
$('save-now').addEventListener('click',savePrepared);
$('sign-in').addEventListener('click',async()=>{try{if(!connection)throw Error('The GitHub connection is still loading.');await connection.signIn();}catch(error){$('account-state').textContent=error.message;}});
$('sign-out').addEventListener('click',async()=>{try{await connection.signOut();updateConnection();}catch(error){$('account-state').textContent=error.message;}});
$('check-save').addEventListener('click',async()=>{
  try{
    if(!remoteReady)throw Error('Refresh the repository successfully before testing saving.');
    if(preparedSave){showSavePanel();return;}
    await prepareAndSave({schema_version:1,record_type:'persistence_check',event_id:crypto.randomUUID(),created_at:new Date().toISOString(),dataset_sha256:manifest.dataset_sha256,purpose:'Technical save verification; no vocabulary decision'});
  }catch(error){$('check-result').textContent=error.message;}
});
$('export').addEventListener('click',()=>{
  if(!resolution || resolution.issues.length){$('sync-detail').textContent='Refresh a valid GitHub snapshot before exporting saved reviews.';return;}
  const blob=new Blob([JSON.stringify({repository:REPO,branch:BRANCH,commit,dataset_sha256:manifest.dataset_sha256,events},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='dod-bco-saved-reviews.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
async function start(){
  // Exchange the short-lived sign-in code immediately, while evidence loads.
  const connect=(async()=>{
    const config=await jsonFetch('save-config.json');
    connection=createConnection(config.service_url);
    const returned=await connection.finishSignIn(signInSearch);
    if(!returned)await connection.restore();
    return {returned};
  })().catch(error=>({error}));
  try{
    const [m,response,u]=await Promise.all([jsonFetch('data/site-manifest.json'),fetch('data/pilot-ledger.json'),jsonFetch('data/source-units.json')]);
    if(!response.ok)throw Error('The evidence ledger could not be loaded.');
    const bytes=await response.arrayBuffer();
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
    if(hash!==m.dataset_sha256)throw Error('The evidence ledger does not match the published snapshot.');
    candidates=JSON.parse(new TextDecoder().decode(bytes));units=u;manifest=m;
    if(preparedSave){try{validateEvent(preparedSave,candidates,manifest.dataset_sha256);}catch{clearPrepared();}}
    $('resume-save').hidden=!preparedSave;
    for(const c of candidates){for(const e of c.evidence){if(Array.from(units[e.unit_id]?.text_exact||'').slice(e.start,e.end).join('')!==e.source_text_exact)throw Error('A source quotation failed its exact-text check.');}}
    for(const [id,values] of [['source',[...new Set(candidates.map(c=>c.source.designation))]],['kind',[...new Set(candidates.map(c=>c.record_type))]]]){
      for(const value of values){const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');$(id).append(option);}
    }
    render();await sync();
    const connected=await connect;updateConnection();
    if(connected.error){$('account-state').textContent=connected.error.message;if(preparedSave)showSavePanel(connected.error.message);}
    else if(connected.returned && preparedSave)await savePrepared();
    const target=document.getElementById(location.hash.slice(1));if(target)target.scrollIntoView();
  }catch(error){$('cards').textContent=error.message;$('sync-title').textContent='The evidence could not be loaded';$('sync-detail').textContent='Reload the report. No review status has been inferred.';$('sync-dot').className='sync-dot error';}
}
start();
