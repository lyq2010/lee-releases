import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {createHash,createPrivateKey,createPublicKey,sign,verify} from 'node:crypto';
import {join,basename} from 'node:path';
import {execFileSync} from 'node:child_process';
const root=process.argv[2],version=process.env.RELEASE_VERSION,tag=process.env.PUBLIC_TAG;
const fail=()=>{throw new Error('发行资产或签名身份不一致');};
if(!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version??'')||tag!==`lees-pdf-v${version}`)fail();
const read=name=>JSON.parse(readFileSync(join(root,name),'utf8'));
const targets=['darwin-aarch64','windows-x86_64'];
const rows=targets.map(target=>read(`${target}.json`));
const config=read('darwin-aarch64-public-config.json');
if(JSON.stringify(config)!==JSON.stringify(read('windows-x86_64-public-config.json')))fail();
const key=createPrivateKey(process.env.LEESPDF_RELEASE_PRIVATE_KEY);
const pub=createPublicKey(key).export({format:'der',type:'spki'}).subarray(-32).toString('base64');
if(pub!==config.releasePublicKey)fail();
const files=new Map();
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function artifact(name,signature){
 if(basename(name)!==name||!/^lees-pdf-[\w.-]+$/.test(name))fail();
 const bytes=readFileSync(join(root,name));if(!bytes.length||bytes.length>768*1024*1024)fail();
 const result={path:`lees-pdf/releases/${version}/${name}`,size:bytes.length,sha256:sha(bytes),signature:signature??null};
 files.set(name,result);return result;
}
const platforms={};
for(const [index,row] of rows.entries()){
 const target=targets[index];
 if(row.version!==version||row.target!==target||row.sourceRevision!==rows[0].sourceRevision||!/^[a-f0-9]{40}$/.test(row.sourceRevision)||row.bundleId!=='app.lees.pdf'||!row.updaterSignature||!/^[a-f0-9]{64}$/.test(row.runtimeManifestSha256))fail();
 if(target==='windows-x86_64'&&row.signerCertificateSha256!==config.windowsCertificateSha256)fail();
 platforms[target]={minOs:target.startsWith('darwin')?'26.0':'10.0.26100',arch:target.split('-')[1],bundleId:row.bundleId,protocol:1,schema:1,runtimeManifestSha256:row.runtimeManifestSha256,signerCertificateSha256:row.signerCertificateSha256??null,updaterArtifact:artifact(row.updater,row.updaterSignature),installerArtifact:artifact(row.installer,null)};
 for(const name of row.materials)artifact(name,null);
}
const publishedAt=new Date().toISOString().replace(/\.\d{3}Z$/,'Z');
const notes=`Lee’s PDF ${version}（Windows x64 / macOS Apple Silicon）。安装前请保存并关闭文档。`;
const payload={schemaVersion:1,product:'lees-pdf',channel:'stable',releaseId:tag,version,sourceRevision:rows[0].sourceRevision,publishedAt,notes,platforms};
const bytes=Buffer.from(JSON.stringify(payload));const signature=sign(null,bytes,key);
if(!verify(null,bytes,createPublicKey(key),signature))fail();
const release={keyId:config.keyId,payloadBase64:bytes.toString('base64'),signatureBase64:signature.toString('base64')};
let cosBase=(process.env.COS_PUBLIC_BASE_URL??'').trim().replace(/\/+$/,'');
if(!cosBase.includes('://'))cosBase='https://'+cosBase;
const cos=new URL(cosBase+'/');
if(cos.protocol!=='https:'||cos.username||cos.password||cos.search||cos.hash)fail();
const outer={version,notes,pub_date:publishedAt,platforms:Object.fromEntries(Object.entries(platforms).map(([target,p])=>[target,{url:new URL(p.updaterArtifact.path,cos).href,signature:p.updaterArtifact.signature}])),release};
writeFileSync(join(root,'release-manifest.json'),JSON.stringify(outer,null,2)+'\n');
writeFileSync(join(root,'SHA256SUMS'),[...files].map(([name,a])=>`${a.sha256}  ${name}`).join('\n')+'\n');
writeFileSync(join(root,'release-notes.txt'),notes+'\n');
// Strict allowlist: never glob private checkout, diagnostics, PDB, maps or source archives.
const assets=[...files.keys(),'release-manifest.json','SHA256SUMS','release-notes.txt'].map(name=>join(root,name));
execFileSync('gh',['release','upload',tag,'--repo','lyq2010/lee-releases','--clobber',...assets],{stdio:'inherit'});
execFileSync('gh',['release','edit',tag,'--repo','lyq2010/lee-releases','--title',`Lee’s PDF ${version}`,'--notes-file',join(root,'release-notes.txt')],{stdio:'inherit'});
