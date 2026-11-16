/** @typedef {{id:number,code:string,line:string,supplier:string,tonnes:number,received_date:string,samples:number}} Batch */
/** @typedef {{sample_code:string,batch_id:number,flour_yield:number,moisture:number,inspector:string,source:'manual'|'instrument',sampled_at:string|null}} Inspection */
/** @typedef {{reading:number,standard:number}} CalibrationPoint */
/** @typedef {{id:number,code:string,status:'draft'|'published',version:number,effective_from:string,effective_to:string,points:CalibrationPoint[],note:string}} CalibrationSheet */
/** @typedef {{version:number,release_id:number|null,sheets:CalibrationSheet[]}} CalibrationRelease */
/** @typedef {{id:number,title:string,line:string,status:string,result:object,note:string,calibration:CalibrationRelease&{applied_count?:number,manual_count?:number}}} Review */
export const API_VERSION='1';
