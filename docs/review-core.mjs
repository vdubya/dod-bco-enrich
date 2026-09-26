export const REPO = 'vdubya/dod-bco-enrich';
export const BRANCH = 'dod-bco';
export const EVENT_DIR = 'docs/review-events';
export const STATUSES = Object.freeze({accepted:'Accept assertion', rejected:'Reject candidate', needs_revision:'Needs revision', deferred:'Defer', pending:'Reopen review'});
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
const textOK = (v, max, required=false) => typeof v === 'string' && v.length <= max && (!required || v.trim().length > 0);

export function validateEvent(e, candidates, datasetHash) {
  if (!e || e.schema_version !== 1 || !uuid.test(e.event_id || '') || !Number.isFinite(Date.parse(e.created_at))) throw Error('Invalid review event identity.');
  if (e.dataset_sha256 !== datasetHash) throw Error('Review belongs to a different evidence snapshot.');
  if (e.record_type === 'persistence_check') {
    if (e.candidate_id != null || e.status != null || e.purpose !== 'Technical save verification; no vocabulary decision') throw Error('A save check cannot adjudicate a candidate.');
    return e;
  }
  if (e.record_type !== 'definition_review') throw Error('Unknown review record type.');
  const c = candidates.find(c => c.candidate_id === e.candidate_id);
  if (!c || e.source_sha256 !== c.source.source_sha256 || e.source_version_id !== c.source.version_id) throw Error('Review does not match the source evidence.');
  if (!Object.hasOwn(STATUSES, e.status)) throw Error('Unknown decision.');
  if (!Array.isArray(e.supersedes) || e.supersedes.length > 100 || new Set(e.supersedes).size !== e.supersedes.length || e.supersedes.some(id => !uuid.test(id) || id === e.event_id)) throw Error('Invalid review history.');
  if (!textOK(e.reviewer,80,true) || !textOK(e.rationale,600,true) || !textOK(e.scope_note,500,e.status==='accepted') || !textOK(e.proposed_label,150) || !textOK(e.proposed_definition,1000)) throw Error('Complete the required review fields within their limits.');
  return e;
}

export function resolveReviews(events, candidates, datasetHash) {
  const valid = [], issues = [], checks = [], states = new Map();
  const ids = new Set();
  for (const e of events) {
    try {
      validateEvent(e,candidates,datasetHash);
      if(ids.has(e.event_id)) throw Error('Duplicate event ID.');
      ids.add(e.event_id);
      (e.record_type === 'persistence_check' ? checks : valid).push(e);
    } catch(error) { issues.push(error.message); }
  }
  for (const c of candidates) {
    const history = valid.filter(e => e.candidate_id===c.candidate_id);
    const byId = new Map(history.map(e => [e.event_id,e]));
    let malformed = history.some(e => e.supersedes.some(id => !byId.has(id)));
    const visiting = new Set(), visited = new Set();
    function cycle(id) {
      if(visiting.has(id)) return true;
      if(visited.has(id) || !byId.has(id)) return false;
      visiting.add(id);
      for(const p of byId.get(id).supersedes) if(cycle(p)) return true;
      visiting.delete(id); visited.add(id); return false;
    }
    malformed ||= history.some(e => cycle(e.event_id));
    const replaced = new Set(history.flatMap(e=>e.supersedes));
    const heads = history.filter(e=>!replaced.has(e.event_id));
    const status = malformed || heads.length>1 ? 'conflict' : heads[0]?.status || 'pending';
    if(malformed) issues.push(`Incomplete or cyclic review history for ${c.candidate_id}.`);
    states.set(c.candidate_id,{status,heads,history,latest:status==='conflict'?null:heads[0]||null});
  }
  // An invalid record could supersede a valid one. Do not show any final outcome
  // as current when the repository snapshot failed validation.
  if(issues.length) for(const state of states.values()) { state.status='unverified'; state.latest=null; }
  return {states,checks,issues};
}

export function githubSaveURL(event) {
  if(!uuid.test(event.event_id||'')) throw Error('Invalid event ID.');
  const path = `${EVENT_DIR}/${event.event_id}.json`;
  const url = new URL(`https://github.com/${REPO}/new/${BRANCH}`);
  url.searchParams.set('filename',path);
  url.searchParams.set('value',JSON.stringify(event,null,2)+'\n');
  url.searchParams.set('message',event.record_type==='persistence_check'?'Verify BCO review persistence':`Review ${event.candidate_id}: ${event.status}`);
  if(url.href.length>8000) throw Error('This review is too long for GitHub’s editor link. Shorten the notes before saving.');
  return url.href;
}

export function eventPath(id) {
  if(!uuid.test(id)) throw Error('Invalid event ID.');
  return `${EVENT_DIR}/${id}.json`;
}
