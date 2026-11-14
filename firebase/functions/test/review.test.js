import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makePayload, parseResponse, validateInput } from '../review.js';
const image={id:1,data:'data:image/jpeg;base64,/9j/2Q=='};
test('never forwards filename or private metadata to model',()=>{
  const payload=makePayload({criteria:'Tự nhiên',images:[{...image,path:'private.jpg',note:'private note'}]});
  assert.equal(payload.store,false);assert.equal(payload.model,'gpt-4.1-mini');assert.ok(!JSON.stringify(payload).includes('private'));
});
test('rejects URL inputs, oversized data, duplicate IDs and large batches',()=>{
  for(const images of [[{id:1,data:'https://example.com/a.jpg'}],[{...image,data:image.data+'a'.repeat(1000000)}],[image,image],Array(13).fill(image)])assert.throws(()=>validateInput({criteria:'',images}));
});
test('validates full model output and refuses duplicates or incomplete responses',()=>{
  const result={summary:'Ổn',photos:[{id:1,score:0,reason:'Ánh sáng',editing_note:''}]};
  const response={status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(result)}]}]};
  assert.equal(parseResponse(response,1).photos[0].score,0);
  assert.throws(()=>parseResponse({...response,status:'incomplete'},1));assert.throws(()=>parseResponse(response,2));
  const duplicate={...result,photos:[result.photos[0],result.photos[0]]};assert.throws(()=>parseResponse({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(duplicate)}]}]},2));
});
