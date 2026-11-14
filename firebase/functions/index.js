import { onCall, HttpsError } from 'firebase-functions/v2/https';
import { defineSecret, defineString, defineInt } from 'firebase-functions/params';
import { initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';
import { makePayload, parseResponse, validateInput } from './review.js';

initializeApp();
const apiKey=defineSecret('OPENAI_API_KEY');
const allowedUids=defineString('AI_ALLOWED_UIDS',{default:'',description:'UID Firebase được dùng AI, phân cách dấu phẩy. Bỏ trống: tắt AI.'});
const dailyLimit=defineInt('AI_DAILY_BATCH_LIMIT',{default:20});

export const reviewPhotos=onCall({region:'asia-southeast1',timeoutSeconds:75,memory:'512MiB',maxInstances:1,concurrency:4,secrets:[apiKey]},async request=>{
  if(!request.auth)throw new HttpsError('unauthenticated','Đăng nhập Google qua Firebase trước khi đánh giá ảnh.');
  if(!allowedUids.value().split(',').map(s=>s.trim()).filter(Boolean).includes(request.auth.uid))throw new HttpsError('permission-denied','UID tài khoản chưa được cho phép dùng AI. Nhờ chủ dự án thêm UID vào AI_ALLOWED_UIDS.');
  let input;try{input=validateInput(request.data);}catch(e){throw new HttpsError('invalid-argument',e.message);}
  const usage=getFirestore().doc('_aiUsage/'+request.auth.uid),day=new Date().toISOString().slice(0,10);
  await getFirestore().runTransaction(async tx=>{
    const snapshot=await tx.get(usage),previous=snapshot.data()||{},count=previous.day===day?previous.count:0;
    if(count>=dailyLimit.value())throw new HttpsError('resource-exhausted','Đã hết số nhóm đánh giá cho hôm nay.');
    if(previous.at&&Date.now()-previous.at<3000)throw new HttpsError('resource-exhausted','Đợi vài giây trước nhóm tiếp theo.');
    tx.set(usage,{day,count:count+1,at:Date.now()});
  });
  let response;
  try{
    response=await fetch('https://api.openai.com/v1/responses',{method:'POST',headers:{Authorization:'Bearer '+apiKey.value(),'Content-Type':'application/json'},body:JSON.stringify(makePayload(input)),signal:AbortSignal.timeout(60000)});
  }catch{throw new HttpsError('deadline-exceeded','Không kết nối được OpenAI hoặc đã quá 60 giây. Yêu cầu không tự gửi lại.');}
  if(!response.ok){const messages={400:'Model hoặc ảnh không được hỗ trợ.',401:'Khóa OpenAI của chủ dự án không hợp lệ.',403:'Chưa có quyền dùng model.',404:'Không tìm thấy model.',429:'OpenAI hết hạn mức hoặc vượt giới hạn yêu cầu.'};throw new HttpsError('failed-precondition',messages[response.status]||'OpenAI trả lỗi HTTP '+response.status+'.');}
  // Never log request images, tokens, upstream bodies or API keys.
  try{return parseResponse(await response.json(),input.images.length);}catch{throw new HttpsError('data-loss','Kết quả AI không đầy đủ hoặc không hợp lệ. Lựa chọn trước đó được giữ nguyên.');}
});
