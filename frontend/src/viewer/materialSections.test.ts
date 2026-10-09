import {expect, it, vi} from 'vitest';
import * as sections from './materialSections';
import {Box3, Group, Vector3, Vector2, PerspectiveCamera} from 'three';
import {clipStateAllOff} from './clipping';
import {pickAtNormalizedCoords} from './picking';

it('maps world planes to the true noncubic full grid domain, including boundary cells', () => {
  expect(sections).toHaveProperty('sectionPlacement');
  const model = {gridShape: [2, 3, 4] as const, voxelSizeNm: 100};
  const bounds = new Box3(new Vector3(0, .1, .2), new Vector3(.1, .2, .3));
  for (const [axis, shape, size] of [['x', [4, 3], [.3, .4]], ['y', [4, 2], [.2, .4]], ['z', [3, 2], [.2, .3]]] as const) {
    const p = sections.sectionPlacement(model, bounds, axis, .5);
    expect(p.shape).toEqual(shape);
    expect(p.size[0]).toBeCloseTo(size[0]);
    expect(p.size[1]).toBeCloseTo(size[1]);
    expect(p.world).toBeCloseTo(axis === 'x' ? .05 : axis === 'y' ? .15 : .25);
  }
  expect(sections.sectionPlacement(model, new Box3(new Vector3(-.05,0,0), new Vector3(.15,0,0)), 'x', 0).index).toBe(0);
  expect(sections.sectionPlacement(model, new Box3(new Vector3(-.05,0,0), new Vector3(.15,0,0)), 'x', 1).index).toBe(1);
});

it.each([100,1e-9])('samples the retained negative cell at interfaces using ULP tolerance with voxel %s nm', voxelSizeNm => {
  const model = {gridShape:[3,2,2] as const,voxelSizeNm};
  const voxel = voxelSizeNm/1000;
  const at = (coord:number) => sections.sectionPlacement(model,new Box3(new Vector3(coord*voxel,0,0),new Vector3(coord*voxel,0,0)),'x',0);
  expect(at(-.5).inside).toBe(false);
  expect(at(2.5)).toMatchObject({inside:true,index:2});
  expect(at(.5).index).toBe(0);
  expect(at(.5+Number.EPSILON).index).toBe(0);
  expect(at(.5-Number.EPSILON).index).toBe(0);
  expect(at(.5+1e-10).index).toBe(1);
  expect(at(.49).index).toBe(0);
  expect(at(.51).index).toBe(1);
});

it.each([[1,2],[0,1],[1,0]])('requests the retained side at a material/air interface %j', async (negative,positive) => {
  const fetcher = vi.fn(async (request:{axis:'x'|'y'|'z';index:number}) => ({axis:request.axis,index:request.index,indexMax:1,shape:[1,1] as const,data:new Uint16Array([request.index === 0 ? negative : positive])}));
  const group = new Group();
  const manager = sections.createMaterialSections(group,fetcher);
  await manager.update({model:{gridShape:[2,1,1],voxelSizeNm:100},revision:1,bounds:new Box3(new Vector3(0,-.05,-.05),new Vector3(.1,.05,.05)),clip:{...clipStateAllOff(),x:{enabled:true,position:.5}},materials:new Map([[1,{color:[1,0,0],visible:true,opacity:1}],[2,{color:[0,1,0],visible:true,opacity:1}]])});
  expect(fetcher.mock.calls[0][0].index).toBe(0);
  const candidate = manager.pickCandidates()[0];
  expect(candidate.resolveHit!({uv:new Vector2(.5,.5)} as import('three').Intersection)?.matId ?? 0).toBe(negative);
  manager.dispose();
});

it('renders oriented slices at actual planes, excludes self clipping and disposes superseded textures', async () => {
  expect(sections).toHaveProperty('createMaterialSections');
  const group = new Group();
  const manager = sections.createMaterialSections(group, async request => ({axis: request.axis, index: request.index, indexMax: 3, shape: [4,4], data: new Uint16Array(16).fill(1)}));
  const clip = clipStateAllOff(); clip.x = {enabled: true, position: .25}; clip.y = {enabled: true, position: .5};
  const input = {model: {gridShape: [4,4,4] as const, voxelSizeNm: 100}, revision: 1, bounds: new Box3(new Vector3(-.05,-.05,-.05), new Vector3(.35,.35,.35)), clip, materials: new Map([[1, {color: [1,0,0] as const, visible: true, opacity: 1}]])};
  await manager.update(input);
  expect(group.children).toHaveLength(2);
  const mesh = group.children[0] as import('three').Mesh<import('three').PlaneGeometry, import('three').MeshBasicMaterial>;
  expect(mesh.position.x).toBeCloseTo(.05);
  expect(mesh.material.clippingPlanes).toHaveLength(1);
  expect(mesh.material.clippingPlanes![0].normal.y).toBe(-1);
  let disposed = 0;
  mesh.material.map!.addEventListener('dispose', () => disposed++);
  manager.dispose();
  expect(disposed).toBe(1);
  expect(group.children).toHaveLength(0);
});

it('aborts generations and prevents late responses from restoring disabled sections', async () => {
  expect(sections).toHaveProperty('createMaterialSections');
  let resolve!: (value: import('../api/types').MaterialSliceView) => void;
  let signal!: AbortSignal;
  const group = new Group();
  const manager = sections.createMaterialSections(group, (_request, s) => {signal = s!; return new Promise(r => {resolve = r;});});
  const input = {model: {gridShape: [2,2,2] as const, voxelSizeNm: 100}, revision: 1, bounds: new Box3(new Vector3(),new Vector3(.1,.1,.1)), clip: {...clipStateAllOff(), x: {enabled: true, position: .5}}, materials: new Map()};
  const pending = manager.update(input);
  await manager.update({...input, clip: clipStateAllOff()});
  expect(signal.aborted).toBe(true);
  resolve({axis:'x', index:1,indexMax:1,shape:[2,2],data:new Uint16Array(4)});
  await pending;
  expect(group.children).toHaveLength(0);
});

it('preserves air holes and uint16 IDs and applies material visibility/opacity', () => {
  expect(sections).toHaveProperty('sectionPixels');
  const data = new Uint16Array([1, 0, 256, 2]);
  const colors = new Map([[1, {color: [1,0,0] as const, opacity: .5, visible: true}], [2, {color: [0,1,0] as const, opacity: 1, visible: false}]]);
  const result = sections.sectionPixels(data, colors);
  expect([...result.rgba]).toEqual([255,0,0,128, 0,0,0,0, 160,160,160,255, 0,0,0,0]);
  expect(result.unknownIds).toEqual([256]);
});

it.each(['x','y','z'] as const)('keeps backend row/column directions and resolves material pixels for %s picking', async axis => {
  const group = new Group();
  const manager = sections.createMaterialSections(group, async request => ({axis:request.axis,index:request.index,indexMax:1,shape:[2,2],data:new Uint16Array([1,0,256,2])}));
  const clip = {...clipStateAllOff(),[axis]:{enabled:true,position:.5}};
  await manager.update({model:{gridShape:[2,2,2],voxelSizeNm:100},revision:1,bounds:new Box3(new Vector3(),new Vector3(.1,.1,.1)),clip,materials:new Map([[1,{color:[1,0,0],visible:true,opacity:1}],[2,{color:[0,1,0],visible:false,opacity:1}]])});
  const mesh = group.children[0] as import('three').Mesh;
  mesh.updateMatrixWorld();
  const u = new Vector3(1,0,0).transformDirection(mesh.matrixWorld);
  const v = new Vector3(0,1,0).transformDirection(mesh.matrixWorld);
  const expectedU = axis === 'x' ? new Vector3(0,1,0) : new Vector3(1,0,0);
  const expectedV = axis === 'z' ? new Vector3(0,1,0) : new Vector3(0,0,1);
  expect(u.distanceTo(expectedU)).toBeLessThan(1e-8);
  expect(v.distanceTo(expectedV)).toBeLessThan(1e-8);
  expect(manager.pickCandidates).toBeTypeOf('function');
  const candidate = manager.pickCandidates()[0];
  const hit = (x:number,y:number) => candidate.resolveHit!({uv:new Vector2(x,y)} as import('three').Intersection);
  expect(hit(.25,.25)?.matId).toBe(1);
  expect(hit(.75,.25)).toBeNull();
  expect(hit(.25,.75)?.matId).toBe(256);
  expect(hit(.75,.75)).toBeNull();
  manager.dispose();
});

it.each(['x','y','z'] as const)('raycasts exact world texel centers with the STL coordinate convention for %s', async axis => {
  const group = new Group();
  const manager = sections.createMaterialSections(group, async request => ({axis:request.axis,index:request.index,indexMax:1,shape:[2,2],data:new Uint16Array([1,0,256,1])}));
  const input = {...sectionInput(),clip:{...clipStateAllOff(),[axis]:{enabled:true,position:.5}}};
  await manager.update(input);
  const camera = new PerspectiveCamera(45,1,.001,10);
  const center = new Vector3(.05,.05,.05);
  const normal = axis === 'x' ? new Vector3(1,0,0) : axis === 'y' ? new Vector3(0,1,0) : new Vector3(0,0,1);
  const u = axis === 'x' ? new Vector3(0,1,0) : new Vector3(1,0,0);
  const v = axis === 'z' ? new Vector3(0,1,0) : new Vector3(0,0,1);
  camera.up.copy(v); camera.position.copy(center).add(normal); camera.lookAt(center); camera.updateMatrixWorld();
  const pick = (du:number,dv:number) => {
    const point = center.clone().addScaledVector(u,du).addScaledVector(v,dv).project(camera);
    return pickAtNormalizedCoords(manager.pickCandidates(),camera,point.x,point.y);
  };
  expect(pick(-.05,-.05)?.matId).toBe(1);
  expect(pick(.05,-.05)).toBeNull();
  expect(pick(-.05,.05)?.matId).toBe(256);
  manager.dispose();
});

const sectionInput = () => ({model:{gridShape:[2,2,2] as const,voxelSizeNm:100},revision:1,bounds:new Box3(new Vector3(),new Vector3(.1,.1,.1)),clip:{...clipStateAllOff(),z:{enabled:true,position:.5}},materials:new Map([[1,{color:[1,0,0] as const,visible:true,opacity:1}]])});
const sliceResponse = (axis:'x'|'y'|'z'='z') => ({axis,index:0,indexMax:1,shape:[2,2] as const,data:new Uint16Array([1,0,0,1])});

it.each(['x','y','z'] as const)('clears every cap when enabled %s retains zero volume', async axis => {
  const fetcher = vi.fn(async request => ({...sliceResponse(request.axis),index:request.index}));
  const verifyRevision = vi.fn(async () => true);
  const group = new Group();
  const manager = sections.createMaterialSections(group,fetcher,verifyRevision);
  const input = {...sectionInput(),clip:{x:{enabled:true,position:.5},y:{enabled:true,position:.5},z:{enabled:true,position:.5}}};
  await manager.update(input);
  expect(group.children).toHaveLength(3);
  await manager.update({...input,clip:{...input.clip,[axis]:{enabled:true,position:0}}});
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(verifyRevision).toHaveBeenCalledTimes(1);
  expect(group.children).toHaveLength(0);
  expect(manager.pickCandidates()).toHaveLength(0);
  manager.dispose();
});

it('recolors cached material IDs without refetching and invalidates cache when mesh revision changes', async () => {
  const fetcher = vi.fn(async () => sliceResponse());
  const group = new Group();
  const manager = sections.createMaterialSections(group,fetcher);
  const input = sectionInput();
  await manager.update(input);
  await manager.update({...input,materials:new Map([[1,{color:[0,1,0],visible:true,opacity:.5}]])});
  expect(fetcher).toHaveBeenCalledTimes(1);
  const texture = (group.children[0] as import('three').Mesh<import('three').PlaneGeometry,import('three').MeshBasicMaterial>).material.map as import('three').DataTexture;
  expect([...texture.image.data as Uint8Array].slice(0,4)).toEqual([0,255,0,128]);
  await manager.update({...input,revision:2});
  expect(fetcher).toHaveBeenCalledTimes(2);
  manager.dispose();
});

it('rejects a changed server revision, retries errors and clears invalid or empty/disposed models', async () => {
  const group = new Group();
  const fetcher = vi.fn(async () => sliceResponse());
  const verifyRevision = vi.fn(async () => false);
  const manager = sections.createMaterialSections(group,fetcher,verifyRevision);
  const input = sectionInput();
  await expect(manager.update(input)).rejects.toThrow(/revision/i);
  expect(group.children).toHaveLength(0);
  verifyRevision.mockResolvedValue(true);
  fetcher.mockRejectedValueOnce(new Error('offline'));
  await expect(manager.update(input)).rejects.toThrow('offline');
  await manager.update(input);
  expect(group.children).toHaveLength(1);
  await manager.update({...input,model:null});
  expect(group.children).toHaveLength(0);
  await manager.update({...input,bounds:new Box3()});
  expect(group.children).toHaveLength(0);
  manager.dispose();
  const calls = fetcher.mock.calls.length;
  await manager.update(input);
  expect(fetcher).toHaveBeenCalledTimes(calls);
});

it.each([{axis:'x'}, {index:1}, {indexMax:2}, {shape:[1,4]}, {data:new Uint16Array(3)}])('rejects a slice inconsistent with the model %j', async patch => {
  const group = new Group();
  const manager = sections.createMaterialSections(group,async () => ({...sliceResponse(),...patch}) as import('../api/types').MaterialSliceView);
  await expect(manager.update(sectionInput())).rejects.toThrow(/domain/i);
  expect(group.children).toHaveLength(0);
  manager.dispose();
});

it('keeps the new revision when an aborted older request later resolves or rejects', async () => {
  const pending: {resolve:(slice:import('../api/types').MaterialSliceView)=>void; reject:(error:Error)=>void}[] = [];
  const group = new Group();
  const manager = sections.createMaterialSections(group, () => new Promise((resolve,reject) => pending.push({resolve,reject})));
  const input = sectionInput();
  const old = manager.update(input);
  const next = manager.update({...input,revision:2});
  pending[1].resolve({...sliceResponse(),data:new Uint16Array([256,0,0,256])});
  await next;
  const mesh = group.children[0];
  pending[0].reject(new Error('old request offline'));
  await old;
  expect(group.children).toEqual([mesh]);
  manager.dispose();
});

it('rejects slices larger than the renderer texture budget before fetching', async () => {
  const fetcher = vi.fn(async () => sliceResponse());
  const group = new Group();
  const manager = sections.createMaterialSections(group,fetcher,undefined,()=>1);
  await expect(manager.update(sectionInput())).rejects.toThrow(/texture/i);
  expect(fetcher).not.toHaveBeenCalled();
  expect(group.children).toHaveLength(0);
  manager.dispose();
});

it('does not paint clamped material outside the full voxel domain at slider boundaries', async () => {
  const fetcher = vi.fn(async (request:{axis:'x'|'y'|'z';index:number}) => ({...sliceResponse(),index:request.index}));
  const group = new Group();
  const manager = sections.createMaterialSections(group,fetcher);
  const input = sectionInput();
  await manager.update({...input,bounds:new Box3(new Vector3(-1,-1,-1),new Vector3(1,1,1)),clip:{...clipStateAllOff(),z:{enabled:true,position:0}}});
  expect(fetcher).not.toHaveBeenCalled();
  await manager.update({...input,bounds:new Box3(new Vector3(-1,-1,-1),new Vector3(1,1,1)),clip:{...clipStateAllOff(),z:{enabled:true,position:1}}});
  expect(fetcher).not.toHaveBeenCalled();
  expect(group.children).toHaveLength(0);
  manager.dispose();
});

it.each(['x','y','z'] as const)('avoids duplicate caps at Float32 noncubic bbox endpoints for %s while preserving interior cuts', async axis => {
  const model = {gridShape:[3,5,7] as const,voxelSizeNm:5};
  const a = {x:0,y:1,z:2}[axis];
  const [u,v] = axis === 'x' ? [1,2] : axis === 'y' ? [0,2] : [0,1];
  const shape = [model.gridShape[v],model.gridShape[u]] as const;
  const fetcher = vi.fn(async (request:{axis:'x'|'y'|'z';index:number}) => ({
    ...request,indexMax:model.gridShape[a]-1,shape,data:new Uint16Array(shape[0]*shape[1]).fill(1),
  }));
  const verifyRevision = vi.fn(async () => true);
  const group = new Group();
  const manager = sections.createMaterialSections(group,fetcher,verifyRevision);
  const bounds = new Box3(
    new Vector3(...model.gridShape.map(() => Math.fround(-.0025)) as [number,number,number]),
    new Vector3(...model.gridShape.map(n => Math.fround((n-.5)*.005)) as [number,number,number]),
  );
  const input = {...sectionInput(),model,bounds};
  const updateAt = (position:number) => manager.update({...input,clip:{...clipStateAllOff(),[axis]:{enabled:true,position}}});
  for (const position of [0,1]) {
    await updateAt(position);
    expect(fetcher).not.toHaveBeenCalled();
    expect(verifyRevision).not.toHaveBeenCalled();
    expect(group.children).toHaveLength(0);
    expect(manager.pickCandidates()).toHaveLength(0);
  }
  await updateAt(.5);
  expect(fetcher.mock.calls[0][0]).toEqual({axis,index:Math.floor(model.gridShape[a]/2)});
  expect(group.children).toHaveLength(1);
  expect(manager.pickCandidates()).toHaveLength(1);
  const geometry = (group.children[0] as import('three').Mesh).geometry;
  const disposed = vi.fn();
  geometry.addEventListener('dispose',disposed);
  for (const position of [1,0]) {
    await updateAt(position);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(verifyRevision).toHaveBeenCalledTimes(1);
    expect(group.children).toHaveLength(0);
    expect(manager.pickCandidates()).toHaveLength(0);
  }
  expect(disposed).toHaveBeenCalledTimes(1);
  // A positive interior fraction remains legal; do not widen the endpoint exclusion with epsilon.
  await updateAt(1e-10);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(group.children).toHaveLength(1);
  expect(manager.pickCandidates()).toHaveLength(1);
  manager.dispose();
});

// Golden generated with ProcessModel.get_cross_section and the worker's Z .T.
// grid[0,0,0]=1; grid[1,2,3]=256; grid[0,1,2]=2; grid[1,0,1]=1.
// Actual padded marching_cubes(.1µm) for [1,2,3] gives bbox
// [.05,.15,.25]..[.15,.25,.35], hence the sample centre is [.1,.2,.3].
it.each([
  {axis:'x' as const,index:1,indexMax:1,shape:[4,3] as const,data:[0,0,0,1,0,0,0,0,0,0,0,256]},
  {axis:'y' as const,index:1,indexMax:2,shape:[4,2] as const,data:[0,0,0,0,2,0,0,0]},
  {axis:'z' as const,index:3,indexMax:3,shape:[3,2] as const,data:[0,0,0,0,0,256]},
])('renders sparse noncubic backend golden %j in full domain rather than partial mesh bounds', async fixture => {
  const group = new Group();
  const fetcher = vi.fn(async (_request:{axis:'x'|'y'|'z';index:number}) => ({...fixture,data:new Uint16Array(fixture.data)}));
  const manager = sections.createMaterialSections(group,fetcher);
  const axisIndex = {x:0,y:1,z:2}[fixture.axis];
  const [u,v] = fixture.axis === 'x' ? [1,2] : fixture.axis === 'y' ? [0,2] : [0,1];
  const world = fixture.index*.1;
  const min = new Vector3(0,.1,.2), max = new Vector3(.1,.2,.3);
  min.setComponent(axisIndex,world-.025); max.setComponent(axisIndex,world+.025);
  const clip = {...clipStateAllOff(),[fixture.axis]:{enabled:true,position:.5}};
  await manager.update({model:{gridShape:[2,3,4],voxelSizeNm:100},revision:1,bounds:new Box3(min,max),clip,materials:new Map([1,2,256].map(id => [id,{color:[1,0,0] as const,visible:true,opacity:1}]))});
  expect(fetcher.mock.calls[0][0]).toEqual({axis:fixture.axis,index:fixture.index});
  const center = new Vector3(.05,.1,.15).setComponent(axisIndex,world);
  const normal = new Vector3().setComponent(axisIndex,1);
  const camera = new PerspectiveCamera(45,1,.001,10);
  camera.up.set(0,0,0).setComponent(v,1); camera.position.copy(center).add(normal); camera.lookAt(center); camera.updateMatrixWorld();
  fixture.data.forEach((id,pixel) => {
    const point = new Vector3().setComponent(axisIndex,world).setComponent(u,(pixel%fixture.shape[1])*.1).setComponent(v,Math.floor(pixel/fixture.shape[1])*.1).project(camera);
    const hit = pickAtNormalizedCoords(manager.pickCandidates(),camera,point.x,point.y);
    expect(hit?.matId ?? 0).toBe(id);
  });
  manager.dispose();
});
