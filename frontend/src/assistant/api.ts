export class ApiError extends Error {constructor(public status:number,message:string){super(message)}}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
  const headers=new Headers(options.headers)
  if(options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json')
  const response=await fetch('/api/assistant'+path,{...options,headers,credentials:'same-origin'})
  if(!response.ok){const body=await response.json().catch(()=>({detail:'Không kết nối được máy chủ.'}));throw new ApiError(response.status,typeof body.detail==='string'?body.detail:'Dữ liệu gửi chưa hợp lệ.')}
  return response.json() as Promise<T>
}
export const json=(value:unknown)=>JSON.stringify(value)
