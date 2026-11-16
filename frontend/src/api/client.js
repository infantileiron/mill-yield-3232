export async function api(path,options={}) {
 const token=localStorage.getItem('mill-token');
 const res=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...options.headers}});
 if(!res.ok){let d=await res.json().catch(()=>({detail:'网络响应异常'})); if(res.status===401&&path!='/auth/login'){localStorage.removeItem('mill-token');location.reload();} const detail=d.detail; if(detail&&typeof detail==='object'&&detail.message){const err=Error(detail.message);err.payload=detail;throw err;} throw Error(typeof detail==='string'?detail:JSON.stringify(detail));}
 return res.json();
}
export const post=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data)});
export async function download(id){const r=await fetch(`/api/reviews/${id}/export`,{headers:{Authorization:'Bearer '+localStorage.getItem('mill-token')}});if(!r.ok)throw Error('报告尚不可导出');const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=`mill-yield-review-${id}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);}
