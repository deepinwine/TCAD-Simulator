import {afterEach, describe, expect, it, vi} from 'vitest';
import {createTcadApi} from './client';
import {parseDisplayManifestEnvelope, parseDisplaySliceEnvelope, parseStepEnvelope} from './schemas';
const identity = '346fd6b5-0811-4933-b2c6-f7d7c684843d';
afterEach(() => vi.unstubAllGlobals());
const wire = {ok:true,result:{revision:3,available:true,domain:{bounds_um:{min:[-.5,-.5,-.5],max:[2,2,2]}},owner_step_ids:{'1':identity},groups:[{owner_id:1,mat_id:2,step_id:identity,voxel_count:3,tri_count:12,bytes:100,bbox:{min:[0,0,0],max:[1,1,1]}}],step_entities:[{step_id:identity,owner_id:1,voxel_count:3,hideable:true,unavailable_reason:null}],unavailable_reasons:[]}};
describe('read-only display API', () => {
  it.each(['registry', 'group', 'entity'])('rejects invalid UUID in %s source identities', location => {
    const payload = structuredClone(wire);
    if (location === 'registry') payload.result.owner_step_ids['1'] = 'index-1';
    if (location === 'group') payload.result.groups[0].step_id = 'index-1';
    if (location === 'entity') payload.result.step_entities[0].step_id = 'index-1';
    expect(() => parseDisplayManifestEnvelope(payload)).toThrow('persisted UUID step identity');
  });
  it('rejects entity owner overflow, registry mismatch and duplicate entity identities', () => {
    const overflow = structuredClone(wire); overflow.result.step_entities[0].owner_id = 0x100000000;
    expect(() => parseDisplayManifestEnvelope(overflow)).toThrow();
    const mismatch = structuredClone(wire); mismatch.result.step_entities[0].owner_id = 2;
    expect(() => parseDisplayManifestEnvelope(mismatch)).toThrow();
    const duplicate = structuredClone(wire); duplicate.result.step_entities.push({...duplicate.result.step_entities[0]});
    expect(() => parseDisplayManifestEnvelope(duplicate)).toThrow();
    const duplicateRegistry = structuredClone(wire);
    Object.assign(duplicateRegistry.result.owner_step_ids, {'2': identity});
    expect(() => parseDisplayManifestEnvelope(duplicateRegistry)).toThrow();
  });
  it('preserves unknown owner zero groups and null entity owners', () => {
    const payload = structuredClone(wire);
    Object.assign(payload.result.groups[0], {owner_id: 0, step_id: null});
    Object.assign(payload.result.step_entities[0], {owner_id: null, hideable: false, unavailable_reason: 'unknown_provenance'});
    const parsed = parseDisplayManifestEnvelope(payload);
    expect(parsed.groups[0]).toMatchObject({ownerId: 0, stepId: null});
    expect(parsed.stepEntities[0]).toMatchObject({ownerId: null, hideable: false});
  });
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
