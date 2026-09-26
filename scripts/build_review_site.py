"""Freeze the selected UFC evidence for the static GitHub Pages reviewer."""
from pathlib import Path
import argparse, hashlib, json, shutil

ROOT = Path(__file__).resolve().parents[1]

def build(source: Path):
    destination = ROOT / 'docs/data'
    destination.mkdir(parents=True, exist_ok=True)
    raw = (source / 'pilot-ledger.json').read_bytes()
    candidates = json.loads(raw)
    units = {u['unit_id']: u for u in map(json.loads, (source / 'source-evidence-units.jsonl').read_text().splitlines())}
    required = set()
    for candidate in candidates:
        required.update(candidate['context_unit_ids'])
        required.update(candidate['scope']['source_document_scope_unit_ids'])
        for evidence in candidate['evidence'] + candidate['label_evidence']:
            required.add(evidence['unit_id'])
            text = units[evidence['unit_id']]['text_exact']
            assert text[evidence['start']:evidence['end']] == evidence['source_text_exact']
    assert len({c['candidate_id'] for c in candidates}) == len(candidates)
    assert required <= units.keys()
    (destination / 'pilot-ledger.json').write_bytes(raw)
    (destination / 'source-units.json').write_text(json.dumps({key: units[key] for key in sorted(required)},ensure_ascii=False,indent=2)+'\n')
    for filename in ['manifest.json','validation.json','pilot-selection.json','corpus-policy-snapshot.json']:
        shutil.copyfile(source / filename, destination / filename)
    manifest = {'schema_version':1,'snapshot_date':'2026-09-26','dataset_sha256':hashlib.sha256(raw).hexdigest(),'candidate_count':len(candidates),'source_count':len({c['source']['designation'] for c in candidates}),'context_unit_count':len(required),'extraction_scope':'Headings and sentence fields; tables, media, commentary and content-only leaves are excluded.','accepted_ontology_concepts':0}
    (destination/'site-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT.parent/'research/reports/ufc-vocabulary-pilot-2026-09-26')
    build(parser.parse_args().source)
