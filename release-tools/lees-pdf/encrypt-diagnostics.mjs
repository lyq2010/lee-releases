import {readFileSync,writeFileSync} from 'node:fs';
import {randomBytes,createCipheriv,publicEncrypt,constants} from 'node:crypto';
const key=randomBytes(32),iv=randomBytes(12);
const aad=Buffer.from(JSON.stringify({product:'lees-pdf',release:process.env.PUBLIC_TAG,target:process.env.RELEASE_TARGET,run:process.env.GITHUB_RUN_ID}));
const cipher=createCipheriv('aes-256-gcm',key,iv);cipher.setAAD(aad);
const encrypted=Buffer.concat([cipher.update(readFileSync(process.argv[2])),cipher.final()]);
const wrapped=publicEncrypt({key:process.env.LEESPDF_DIAGNOSTICS_PUBLIC_KEY,padding:constants.RSA_PKCS1_OAEP_PADDING,oaepHash:'sha256'},key);
writeFileSync(process.argv[3],JSON.stringify({schemaVersion:1,aad:aad.toString('base64'),iv:iv.toString('base64'),key:wrapped.toString('base64'),tag:cipher.getAuthTag().toString('base64'),ciphertext:encrypted.toString('base64')})+'\n');
