import {api,post,download} from './client.js';
export const batches={list:()=>api('/batches'),create:d=>post('/batches',d)};
export const inspections={list:()=>api('/inspections'),create:d=>post('/inspections',d)};
export const reviews={list:()=>api('/reviews'),get:id=>api('/reviews/'+id),create:d=>post('/reviews',d),approve:(id,note)=>post(`/reviews/${id}/approve`,{note}),download};
export const calibrations={list:()=>api('/calibrations'),create:d=>post('/calibrations',d),publish:id=>post(`/calibrations/${id}/publish`,{}),preview:id=>api(`/calibrations/${id}/preview`)};
