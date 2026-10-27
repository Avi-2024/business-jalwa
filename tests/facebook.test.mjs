import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const script = new URL('../scripts/publish_facebook.mjs', import.meta.url).pathname;
for (const mode of ['success','wrong-page','lost-response']) test('Facebook ' + mode, async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(),'fb-test-'));
  try {
    const queue = path.join(dir,'posts.json');
    await fs.writeFile(queue,JSON.stringify([{id:'test',manual_approved:true,verified_at:'2026-01-01',instagram_media_id:'ig1',publish_at:'2026-01-01',caption:'example',image_urls:['https://example.com/assets/approved/one.jpg']} ]));
    const mock = path.join(dir,'mock.mjs');
    await fs.writeFile(mock,`globalThis.fetch = async (url, options) => {
      const endpoint = new URL(url).pathname.split('/').pop();
      if (endpoint === 'feed' && process.env.MODE === 'lost-response') throw new Error('response lost');
      const data = endpoint === 'me' ? {id:process.env.MODE === 'wrong-page' ? '999' : '123',name:'Business Jalwa'} : {id:endpoint === 'feed' ? '123_post' : 'photo1'};
      return {ok:true,json:async()=>data};
    };`);
    const run = () => spawnSync(process.execPath,['--import',mock,script],{encoding:'utf8',env:{...process.env,POSTS_FILE:queue,FACEBOOK_PAGE_ID:'123',FACEBOOK_PAGE_ACCESS_TOKEN:'test',MODE:mode}});
    const result = run();
    const saved = JSON.parse(await fs.readFile(queue,'utf8'))[0];
    if(mode === 'success') {assert.equal(result.status,0,result.stderr);assert.equal(saved.facebook_post_id,'123_post');assert.equal(run().status,0);}
    else {assert.notEqual(result.status,0);assert.equal(saved.facebook_post_id,undefined);}
    if(mode === 'wrong-page') assert.equal(saved.facebook_attempt,undefined);
    if(mode === 'lost-response') {assert.ok(saved.facebook_attempt.publish_requested_at);assert.match(run().stderr,/Uncertain Facebook/);}
  } finally {await fs.rm(dir,{recursive:true,force:true});}
});
