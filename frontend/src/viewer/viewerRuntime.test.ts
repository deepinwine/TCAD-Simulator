import {afterEach, expect, it, vi} from 'vitest';
import type {TcadApi} from '../api/types';
import {createThreeViewerRuntime} from './viewerRuntime';
const rendered = vi.hoisted(() => ({scene:null as import('three').Scene | null,camera:null as import('three').Camera | null}));
vi.mock('three',async importOriginal => {
  const actual=await importOriginal<typeof import('three')>();
  return {...actual,WebGLRenderer:class {
    domElement:HTMLCanvasElement; capabilities={maxTextureSize:4096}; localClippingEnabled=false;
    constructor(options:{canvas:HTMLCanvasElement}) {this.domElement=options.canvas;}
    getContext(){return {VERSION:1,getParameter:()=> 'WebGL 2'};}
    setSize(){} render(scene:import('three').Scene,camera:import('three').Camera){rendered.scene=scene;rendered.camera=camera;} dispose(){}
  }};
});
afterEach(() => vi.unstubAllGlobals());
function binary(){const buffer=new ArrayBuffer(108),view=new DataView(buffer);[...'TCADGEOM'].forEach((char,i)=>view.setUint8(i,char.charCodeAt(0)));view.setUint32(8,1,true);view.setUint32(12,7,true);view.setUint32(16,3,true);view.setUint32(20,3,true);new Float32Array(buffer,24,9).set([0,0,0,1,0,0,0,1,0]);new Float32Array(buffer,60,9).set([0,0,1,0,0,1,0,0,1]);new Uint32Array(buffer,96,3).set([0,1,2]);return buffer;}
it('owner meshes, material opacity, cached caps and picking share visibility with zero API calls on eyes',async()=>{
  vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
  const visual={materialId:2,displayName:'Oxide',color:[1,0,0] as const,opacity:1,metallic:0,roughness:.5,visible:true};
  const bounds={min:[-.05,-.05,-.05] as const,max:[.25,.05,.15] as const};
  const display={revision:4,available:true,bounds,ownerStepIds:{'1':'a','2':'b'},groups:[1,2,0].map(ownerId=>({ownerId,materialId:2,stepId:ownerId===1?'a':ownerId===2?'b':null,voxelCount:1,triangleCount:1,bytes:108,boundingBox:bounds})),stepEntities:[],unavailableReasons:[]};
  const api={getPreviewManifest:vi.fn(async()=>({revision:4,meshes:[{materialId:2,name:'Oxide',triangleCount:3,boundingBox:bounds,visual}]})),getMaterialStl:vi.fn(),getDisplayManifest:vi.fn(async()=>display),getDisplayMesh:vi.fn(async()=>binary()),getDisplaySlice:vi.fn(async request=>({revision:4,axis:request.axis,index:request.index,indexMax:1,shape:[1,3] as const,data:new Uint16Array([2,2,2]),owners:new Uint32Array([1,2,0])})),runAll:vi.fn(),runStep:vi.fn(),runTo:vi.fn(),setStep:vi.fn(),importRecipe:vi.fn(),saveRecipe:vi.fn()} as unknown as TcadApi;
  const runtime=createThreeViewerRuntime(api);runtime.mount(document.createElement('div'));
  runtime.setSectionContext!({gridShape:[3,1,2],voxelSizeNm:100},()=>{});
  const result=await runtime.loadMeshes(1);expect(result.materials).toHaveLength(1);expect(result.display?.available).toBe(true);
  runtime.setClipping({x:{enabled:false,position:.5},y:{enabled:false,position:.5},z:{enabled:true,position:.5}});
  await vi.waitFor(()=>expect(api.getDisplaySlice).toHaveBeenCalledTimes(1));
  await new Promise(resolve=>setTimeout(resolve,30));
  const camera=rendered.camera;const position=camera!.position.clone();
  const snapshots=[api.getPreviewManifest,api.getMaterialStl,api.getDisplayManifest,api.getDisplayMesh,api.getDisplaySlice,api.runAll,api.runStep,api.runTo,api.setStep,api.importRecipe,api.saveRecipe].map(fn=>vi.mocked(fn!).mock.calls.length);
  runtime.setHiddenStepIds!(['a']); runtime.setMaterialDisplay(2,{opacity:.4});
  await new Promise(resolve=>setTimeout(resolve,30));
  const ownerMeshes:import('three').Mesh[]=[];rendered.scene!.traverse(object=>{if(object.userData.matId===2)ownerMeshes.push(object as import('three').Mesh);});
  expect(ownerMeshes).toHaveLength(3);expect(ownerMeshes.map(mesh=>[mesh.userData.ownerId,mesh.visible])).toEqual([[1,false],[2,true],[0,true]]);
  expect(ownerMeshes.every(mesh=>(mesh.material as import('three').Material).opacity===.4)).toBe(true);
  runtime.setMaterialDisplay(2,{visible:false});runtime.setHiddenStepIds!([]);expect(ownerMeshes.every(mesh=>!mesh.visible)).toBe(true);
  runtime.setMaterialDisplay(2,{visible:true});runtime.setHiddenStepIds!(['a']);expect(ownerMeshes[0].visible).toBe(false);
  const after=[api.getPreviewManifest,api.getMaterialStl,api.getDisplayManifest,api.getDisplayMesh,api.getDisplaySlice,api.runAll,api.runStep,api.runTo,api.setStep,api.importRecipe,api.saveRecipe].map(fn=>vi.mocked(fn!).mock.calls.length);
  expect(after).toEqual(snapshots);expect(rendered.camera).toBe(camera);expect(camera!.position.equals(position)).toBe(true);
  runtime.dispose();
});
