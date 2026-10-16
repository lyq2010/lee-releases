import {readFileSync} from 'node:fs';
import {join} from 'node:path';
const root=process.argv[2];
const rows=['cos','r2'].map(source=>JSON.parse(readFileSync(join(root,`readiness-${source}.json`),'utf8')));
if(rows.some((r,i)=>r.source!==['cos','r2'][i]||!r.verified||r.verification!=='head-metadata-only'||r.runId!==process.env.GITHUB_RUN_ID)||rows[0].payloadSha256!==rows[1].payloadSha256||rows[0].version!==rows[1].version)throw Error('双源就绪证据不一致');
console.log('双源发行资产 HEAD 元数据已核对（未下载对象正文）');
