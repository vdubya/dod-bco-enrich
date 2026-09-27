import candidates from '../../docs/data/pilot-ledger.json' with {type:'json'};
import manifest from '../../docs/data/site-manifest.json' with {type:'json'};
import {createService} from './service.mjs';

export default createService({candidates,datasetHash:manifest.dataset_sha256});
