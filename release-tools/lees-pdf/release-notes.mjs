import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const versionPattern=/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const invalid=()=>{throw Error('目标版本更新说明缺失或无效');};
export function validateReleaseNotes(notes,version){
 if(!versionPattern.test(version??'')||typeof notes!=='string')invalid();
 const normalized=notes.replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n').trim();
 const heading=new RegExp(`^## ${version.replaceAll('.','\\.')}(?: \\(\\d{4}-\\d{2}-\\d{2}\\))?$`);
 if(!heading.test(normalized.split('\n')[0])||!/^[-*] \S/m.test(normalized)||
    (normalized.match(/^## /gm)??[]).length!==1||Buffer.byteLength(normalized,'utf8')>16000)invalid();
 return normalized+'\n';
}
export function extractReleaseNotes(changelog,version){
 if(!versionPattern.test(version??''))invalid();
 const text=changelog.replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n');
 const headings=[...text.matchAll(/^## (.+)$/gm)];
 const matching=headings.filter(item=>item[1]===version||new RegExp(`^${version.replaceAll('.','\\.')} \\(\\d{4}-\\d{2}-\\d{2}\\)$`).test(item[1]));
 if(matching.length!==1)invalid();
 const index=headings.indexOf(matching[0]);
 return validateReleaseNotes(text.slice(matching[0].index,headings[index+1]?.index),version);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const [source,version,output]=process.argv.slice(2);
 writeFileSync(output,extractReleaseNotes(readFileSync(join(source,'CHANGELOG.md'),'utf8'),version),'utf8');
}
