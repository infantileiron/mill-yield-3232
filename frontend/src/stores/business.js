import {batches,inspections,reviews,calibrations} from '../api/business.js';
export const state={user:null,batches:[],inspections:[],reviews:[],calibrations:null,calibrationPreview:null,selected:null};
export async function refresh(){[state.batches,state.inspections,state.reviews,state.calibrations]=await Promise.all([batches.list(),inspections.list(),reviews.list(),calibrations.list()]);if(state.selected)state.selected=await reviews.get(state.selected.id);}
