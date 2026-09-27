const encoder = new TextEncoder();
export const now = () => Math.floor(Date.now() / 1000);
export const bytes = text => encoder.encode(text);
export const base64 = data => btoa(Array.from(new Uint8Array(data), n => String.fromCharCode(n)).join(''));
export const unbase64 = text => Uint8Array.from(atob(text), c => c.charCodeAt(0));
export const base64url = data => base64(data).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
export const random = () => base64url(crypto.getRandomValues(new Uint8Array(32)));
export const digest = async text => base64url(await crypto.subtle.digest('SHA-256',bytes(text)));
export const validChallenge = value => typeof value === 'string' && /^[A-Za-z0-9_-]{43}$/.test(value);

async function key(secret) {
  if (typeof secret !== 'string' || unbase64(secret).length !== 32) throw Error('Service encryption is not configured.');
  return crypto.subtle.importKey('raw',unbase64(secret),'AES-GCM',false,['encrypt','decrypt']);
}
export async function seal(value,secret) {
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv},await key(secret),bytes(JSON.stringify(value)));
  return `${base64(iv)}.${base64(encrypted)}`;
}
export async function unseal(value,secret) {
  const [iv,data]=value.split('.');
  return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:unbase64(iv)},await key(secret),unbase64(data))));
}
export class Problem extends Error {
  constructor(status,message) { super(message); this.status=status; }
}
export function requireValue(condition,status,message) {
  if (!condition) throw new Problem(status,message);
}
export async function readJSON(request,max=20000) {
  requireValue(request.headers.get('content-type')?.split(';')[0] === 'application/json',415,'Send an application/json request.');
  const reader=request.body?.getReader();
  requireValue(reader,400,'A request body is required.');
  const chunks=[]; let total=0;
  while (true) {
    const {done,value}=await reader.read(); if(done)break;
    total+=value.byteLength;
    if(total>max){await reader.cancel();throw new Problem(413,'The review exceeds the allowed size.');}
    chunks.push(value);
  }
  const content=new Uint8Array(total);let offset=0;
  for(const chunk of chunks){content.set(chunk,offset);offset+=chunk.length;}
  try{return JSON.parse(new TextDecoder().decode(content));}
  catch{throw new Problem(400,'The request is not valid JSON.');}
}
export function cookie(request,name) {
  return request.headers.get('cookie')?.split(';').map(v=>v.trim()).find(v=>v.startsWith(name+'='))?.slice(name.length+1);
}
export const flowCookie = (value,maxAge=600) => `__Host-bco-flow=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
