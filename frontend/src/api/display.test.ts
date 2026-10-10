import {afterEach, describe, expect, it, vi} from 'vitest';
import {createTcadApi} from './client';
import {parseDisplayManifestEnvelope, parseDisplaySliceEnvelope, parseStepEnvelope} from './schemas';
const identity = '346fd6b5-0811-4933-b2c6-f7d7c684843d';
afterEach(() => vi.unstubAllGlobals());
const wire = {ok:true,result:{revision:3,available:true,domain:{bounds_um:{min:[-.5,-.5,-.5],max:[2,2,2]}},owner_step_ids:{'1':identity},groups:[{owner_id:1,mat_id:2,step_id:identity,voxel_count:3,tri_count:12,bytes:100,bbox:{min:[0,0,0],max:[1,1,1]}}],step_entities:[{step_id:identity,owner_id:1,voxel_count:3,hideable:true,unavailable_reason:null}],unavailable_reasons:[]}};
describe('read-only display API', () => {
  it('preserves persisted step IDs and owner/material identity', () => {
    expect(parseStepEnvelope({ok:true,result:{step_id:identity,name:'Structure Deposit',instance_name:'Deposit',enabled:true,params:{},parameter_specs:[]}},4).stepId).toBe(identity);
    expect(parseDisplayManifestEnvelope(wire).groups[0]).toMatchObject({ownerId:1,materialId:2,stepId:identity});
    expect(()=>parseStepEnvelope({ok:true,result:{step_id:'index-4',name:'Structure Deposit',instance_name:'Deposit',enabled:true,params:{},parameter_specs:[]}},4)).toThrow();
  });
  it('decodes paired row-major little-endian arrays without losing uint32 owners', () => {
    const slice = {ok:true,result:{revision:3,axis:'Z',index:0,index_max:1,shape:[1,2],material:{dtype:'u16',data_b64:'AgADAA=='},owner:{dtype:'u32',data_b64:'AQAAAP////8='}}};
    const parsed = parseDisplaySliceEnvelope(slice);
    expect([...parsed.data]).toEqual([2,3]); expect([...parsed.owners]).toEqual([1,4294967295]);
    expect(() => parseDisplaySliceEnvelope({...slice,result:{...slice.result,owner:{dtype:'u32',data_b64:'AQAA'}}})).toThrow();
  });
  it('uses only GET endpoints with revision, owner and material query parameters', async () => {
    const fetcher = vi.fn(async (url: unknown, _options?: RequestInit) => String(url).includes('/mesh?') ? new Response(new ArrayBuffer(24),{headers:{'content-type':'application/octet-stream'}}) : new Response(JSON.stringify(wire),{headers:{'content-type':'application/json'}}));
    vi.stubGlobal('fetch', fetcher);
    const api = createTcadApi();
    await api.getDisplayManifest!(); await api.getDisplayMesh!({revision:3,ownerId:1,materialId:2});
    expect(fetcher.mock.calls.map(call => String(call[0]))).toEqual(['/api/structure/display/manifest','/api/structure/display/mesh?revision=3&owner_id=1&mat_id=2']);
    expect(fetcher.mock.calls.every(call => (call[1] as RequestInit).method === 'GET')).toBe(true);
  });
});
