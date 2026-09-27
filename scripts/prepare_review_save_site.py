#!/usr/bin/env python3
"""Export the GitHub-owned save-service source into its separate Sites checkout."""
import argparse
import json
import shutil
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('checkout',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
target=args.checkout.resolve()
manifest=target/'.openai/hosting.json'
if not manifest.is_file():
    raise SystemExit('Initialize and register the separate Sites checkout first.')
hosting=json.loads(manifest.read_text())
if not hosting.get('project_id'):
    raise SystemExit('Register this Site before exporting source.')
source=root/'services/review-save'
destination=target/'services/review-save'
destination.mkdir(parents=True,exist_ok=True)
for item in source.iterdir():
    if item.name in {'.gitignore','node_modules','dist','.wrangler','.dev.vars'}:
        continue
    if item.is_file():
        shutil.copy2(item,destination/item.name)
    elif item.name in {'db','drizzle'}:
        shutil.copytree(item,destination/item.name,dirs_exist_ok=True)
for name in ['docs/review-core.mjs','docs/review-bulk.mjs','docs/data/pilot-ledger.json','docs/data/site-manifest.json']:
    path=target/name
    path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/name,path)
package=json.loads((source/'package.json').read_text())
package['scripts']={'build':'node services/review-save/build-sites.mjs'}
(target/'package.json').write_text(json.dumps(package,indent=2)+'\n')
# The root install uses the same exact dependency tree as the canonical service.
shutil.copy2(source/'package-lock.json',target/'package-lock.json')
hosting['d1']='DB'
hosting['r2']=None
manifest.write_text(json.dumps(hosting,indent=2)+'\n')
(target/'.env.example').write_text('SERVICE_URL=\nSESSION_KEY=\nSETUP_KEY=\n')
(target/'.gitignore').write_text('node_modules/\ndist/\n.env\n.env.*\n!.env.example\n.dev.vars\n.sites-runtime/\n.DS_Store\n')
(target/'README.md').write_text('# DoD BCO GitHub connection\n\nCanonical source: https://github.com/vdubya/dod-bco-enrich/tree/dod-bco/services/review-save\n\nThis checkout is a deployment export. The report, corpus, saved reviews, and service source are maintained in GitHub. Re-export with `scripts/prepare_review_save_site.py` after a service source change. Runtime secrets belong only in Sites protected environment settings.\n')
# Remove only the known unused starter entrypoint and starter build script.
for name in ['worker/index.js','scripts/build.sh']:
    path=target/name
    if path.is_file():path.unlink()
print(f'Exported the GitHub service source to {target}')
