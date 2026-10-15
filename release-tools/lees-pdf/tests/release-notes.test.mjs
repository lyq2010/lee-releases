import {test} from 'node:test';
import assert from 'node:assert/strict';
import {extractReleaseNotes,validateReleaseNotes} from '../release-notes.mjs';

test('exports only target version with concise bullets and emoji',()=>{
 const target='## 1.0.1 (2026-10-15)\n\n- 🔄 更新更顺畅。\n- 🛠 修复设置卡死。\n';
 const input='# 更新日志\n\n## 未发布\n\n- private future sentinel\n\n'+target+'\n## 1.0.0\n\n- private historical sentinel\n';
 assert.equal(extractReleaseNotes(input,'1.0.1'),target);
 assert.equal(extractReleaseNotes('\uFEFF'+input.replaceAll('\n','\r\n'),'1.0.1'),target);
});
test('missing, duplicate, empty and unrelated versions are rejected',()=>{
 for(const input of ['## 1.0.0\n\n- older\n','## 1.0.1\n\n## 1.0.1\n\n- duplicate\n','## 1.0.1\n\n']){
  assert.throws(()=>extractReleaseNotes(input,'1.0.1'),/更新说明/);
 }
 assert.throws(()=>validateReleaseNotes('## 1.0.2\n\n- wrong version\n','1.0.1'),/更新说明/);
});
test('oversized notes and an entire private changelog cannot pass as a version section',()=>{
 assert.throws(()=>validateReleaseNotes('## 1.0.1\n\n- '+'长'.repeat(6000),'1.0.1'),/更新说明/);
 assert.throws(()=>validateReleaseNotes('## 1.0.1\n\n- current\n\n## 未发布\n\n- private\n','1.0.1'),/更新说明/);
});
