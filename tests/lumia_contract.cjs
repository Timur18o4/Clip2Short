const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../lumia/clip2short.js'),'utf8');
async function run(stage, overrides={}) {
  const calls=[], posts=[], actionsCalled=[]; let doneCount=0;
  const variables={originType:'api',clip2short_stage:stage,clip2short_clip_id:'NewClip123',clip2short_service_url:'http://127.0.0.1:39242',clip2short_bridge_key:'x'.repeat(40),clip2short_stream_title:'Aktueller Titel',...overrides.variables};
  const clip={id:'NewClip123',game_id:'509658',broadcaster_id:'123',video_id:'999',title:'Ein neuer Moment',created_at:'2026-10-31T18:00:00Z'};
  const ctx={AbortSignal,URL,done:()=>doneCount++,log:()=>{},delay:async()=>{},getVariable:async n=>variables[n],getToken:async()=> 'fixture',getClientId:async()=> 'fixture-client',resolveVariables:async()=>stage==='editorial'?JSON.stringify({title:'Feiertag? Jetzt bin ich raus',chat_id:null,reply_excerpt:''}):'Wieder schnell geantwortet.\n\n#Humor #Reaktion #Streaming #JustChatting',actions:async a=>{actionsCalled.push(a);if(overrides.actionThrows)throw Error('Upload unterbrochen');},fetch:async(url,options)=>{
    calls.push(url);let data={};const body=options.body?JSON.parse(options.body):{}; if(options.body)posts.push([new URL(url).pathname,body]);
    if(url.includes('/helix/clips?')) data={data:[clip]};
    else if(url.includes('/helix/games?'))data={data:[{name:'Just Chatting'}]};
    else if(url.includes('/helix/videos?'))data={data:[{title:'Titel des ursprünglichen Streams'}]};
    else if(url.endsWith('/api/eligible'))data={eligible:overrides.eligible!==false,reason:'vor Aktivierung erstellt'};
    else if(url.includes('/api/jobs/'))data={state:'ready',prompt:'Kategorie=Just Chatting. Untertitel: Reaktion.',editorial_context:{key:'nonce'},editorial_prompt:'Erzeuge einen eigenen Titel.'};
    else if(url.endsWith('/api/claim'))data={claimed:overrides.claimed!==false,media:'C:/fixture.mp4',caption:body.caption,privacy:'SELF_ONLY'};
    return {ok:true,status:200,json:async()=>data};
  }};
  await vm.runInNewContext('('+source+')',ctx)();
  assert.equal(doneCount,1);return {calls,posts,actionsCalled};
}
(async()=>{
  let x=await run('resolve',{eligible:false});assert(!x.calls.some(u=>u.includes('/helix/games')));assert(!x.posts.some(([p])=>p==='/api/resolved'));
  x=await run('resolve');let resolved=x.posts.find(([p])=>p==='/api/resolved')[1];assert.equal(resolved.clip.id,'NewClip123');assert.equal(resolved.category,'Just Chatting');assert.equal(resolved.stream_title,'Titel des ursprünglichen Streams');assert(!x.calls.some(u=>u.includes('clips/downloads')));
  x=await run('publish');assert.equal(x.actionsCalled.length,1);assert.equal(x.actionsCalled[0][0].type,'uploadAndPublishVideo');assert.equal(x.actionsCalled[0][0].value.privacy_level,'SELF_ONLY');assert(x.posts.some(([p])=>p==='/api/result'));
  x=await run('publish',{claimed:false});assert.equal(x.actionsCalled.length,0);
  x=await run('publish',{actionThrows:true});assert.equal(x.posts.find(([p])=>p==='/api/result')[1].error,'Upload unterbrochen');
  x=await run('publish',{variables:{originType:'chat'}});assert.equal(x.calls.length,0);assert.equal(x.actionsCalled.length,0);
  x=await run('editorial');assert.equal(x.actionsCalled.length,0);let editorial=x.posts.find(([p])=>p==='/api/editorial')[1];assert.equal(editorial.analysis_key,'nonce');assert.equal(JSON.parse(editorial.result).title,'Feiertag? Jetzt bin ich raus');
  console.log('7 Lumia-Vertragstests bestanden. Keine echten Netzwerk- oder Uploadaktionen.');
})().catch(e=>{console.error(e);process.exitCode=1});
