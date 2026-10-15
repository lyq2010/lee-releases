import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdirSync,mkdtempSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {generateKeyPairSync,createHash,verify} from 'node:crypto';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';

// Generated test keys and fixtures stay local; gh is intercepted before the real module runs.
const parent=process.env.LEES_TEST_OUTPUT??join(tmpdir(),'lees-pdf-manifest-tests');
mkdirSync(parent,{recursive:true});
let sequence=0;
function fixture(){
 const root=mkdtempSync(join(parent,'manifest-'));
 const {privateKey,publicKey}=generateKeyPairSync('ed25519');
 const config={keyId:'local-test-key',releasePublicKey:publicKey.export({format:'der',type:'spki'}).subarray(-32).toString('base64'),windowsCertificateSha256:'c'.repeat(64)};
 for(const target of ['darwin-aarch64','windows-x86_64']){
  const updater=`lees-pdf-1.0.1-${target}.bin`,material=`lees-pdf-1.0.1-${target}-NOTICES.txt`;
  writeFileSync(join(root,updater),'synthetic installer');writeFileSync(join(root,material),'synthetic notices');
  writeFileSync(join(root,`${target}.json`),JSON.stringify({target,version:'1.0.1',sourceRevision:'a'.repeat(40),bundleId:'app.lees.pdf',updater,installer:updater,updaterSignature:'synthetic updater signature',runtimeManifestSha256:'b'.repeat(64),releaseNotes:'## 1.0.1 (2026-10-15)\n\n- 更新流程改进。\n- 设置修复。\n',signerCertificateSha256:target.startsWith('windows')?config.windowsCertificateSha256:null,materials:[material]}));
  writeFileSync(join(root,`${target}-public-config.json`),JSON.stringify(config));
 }
 writeFileSync(join(root,'private-source.ts'),'private sentinel; must never be uploaded');
 return {root,privateKey,publicKey};
}
async function assemble(f){
 const original=childProcess.execFileSync,argv=process.argv,env={...process.env},calls=[];
 childProcess.execFileSync=(command,args)=>{assert.equal(command,'gh');calls.push(args);};syncBuiltinESMExports();
 process.argv=['node','manifest.mjs',f.root];
 Object.assign(process.env,{RELEASE_VERSION:'1.0.1',PUBLIC_TAG:'lees-pdf-v1.0.1',COS_PUBLIC_BASE_URL:'https://cos.example/',LEESPDF_RELEASE_PRIVATE_KEY:f.privateKey.export({format:'pem',type:'pkcs8'})});
 try{await import(new URL(`../manifest.mjs?test=${++sequence}`,import.meta.url));return calls;}
 finally{childProcess.execFileSync=original;syncBuiltinESMExports();process.argv=argv;process.env=env;}
}
test('assemble hashes all existing packages and signs metadata; upload only newly generated files',async()=>{
 const f=fixture(),calls=await assemble(f);
 const uploads=calls.find(a=>a[1]==='upload');
 assert.deepEqual(uploads.slice(6),['release-manifest.json','SHA256SUMS','release-notes.txt'].map(name=>join(f.root,name)));
 const outer=JSON.parse(readFileSync(join(f.root,'release-manifest.json')));
 const bytes=Buffer.from(outer.release.payloadBase64,'base64');
 assert.ok(verify(null,bytes,f.publicKey,Buffer.from(outer.release.signatureBase64,'base64')));
 const payload=JSON.parse(bytes);
 for(const platform of Object.values(payload.platforms)){
  const file=join(f.root,platform.updaterArtifact.path.split('/').at(-1));
  assert.equal(createHash('sha256').update(readFileSync(file)).digest('hex'),platform.updaterArtifact.sha256);
 }
 assert.equal(readFileSync(join(f.root,'SHA256SUMS'),'utf8').trim().split('\n').length,4);
 assert.ok(!JSON.stringify(calls).includes('private-source.ts'));
});
test('different source revisions cannot be assembled',async()=>{
 const f=fixture(),path=join(f.root,'windows-x86_64.json'),row=JSON.parse(readFileSync(path));
 row.sourceRevision='d'.repeat(40);writeFileSync(path,JSON.stringify(row));
 await assert.rejects(assemble(f),/发行资产或签名身份不一致/);
});
test('wrong signing identity cannot be assembled',async()=>{
 const f=fixture();f.privateKey=generateKeyPairSync('ed25519').privateKey;
 await assert.rejects(assemble(f),/发行资产或签名身份不一致/);
});

test('GitHub release body uses version changelog while signed updater summary stays concise',async()=>{
 const f=fixture();await assemble(f);
 const releaseNotes=readFileSync(join(f.root,'release-notes.txt'),'utf8');
 assert.match(releaseNotes,/更新流程改进/);assert.match(releaseNotes,/设置修复/);
 assert.ok(!releaseNotes.includes('private sentinel'));
 const outer=JSON.parse(readFileSync(join(f.root,'release-manifest.json')));
 assert.ok(!outer.notes.includes('设置修复'));
});
test('different platform changelogs cannot be published together',async()=>{
 const f=fixture(),path=join(f.root,'windows-x86_64.json'),row=JSON.parse(readFileSync(path));
 row.releaseNotes='## 1.0.1\n\n- Different changes.\n';writeFileSync(path,JSON.stringify(row));
 await assert.rejects(assemble(f),/发行资产或签名身份不一致/);
});
