import {expect, it} from 'vitest';
import {sourceVisible, stepVisibilityReason, validHiddenSteps} from './stepVisibility';
import type {DisplayManifestView, StepView} from '../api/types';
const step = {index:1,name:'Structure Deposit',stepId:'a'} as StepView;
const manifest: DisplayManifestView = {revision:1,available:true,bounds:{min:[0,0,0],max:[1,1,1]},ownerStepIds:{'1':'a'},groups:[{ownerId:1,materialId:2,stepId:'a',voxelCount:4,triangleCount:12,bytes:100,boundingBox:{min:[0,0,0],max:[1,1,1]}}],stepEntities:[{stepId:'a',ownerId:1,voxelCount:4,hideable:true,unavailableReason:null}],unavailableReasons:[]};
it('only permits prepared, known remaining entities and preserves owner zero', () => {
  expect(stepVisibilityReason(step,manifest,true)).toBeNull();
  expect(stepVisibilityReason(step,manifest,false)).toBe('loading');
  expect(stepVisibilityReason({...step,stepId:undefined},manifest,true)).toBe('unknown');
  for(const name of ['Structure Pattern','Structure Doping','Structure Etch','Structure Planarize']) expect(stepVisibilityReason({...step,name},manifest,true)).toBe('operation');
  expect(validHiddenSteps(['a','removed','a'],[step],manifest,true)).toEqual(['a']);
  expect(sourceVisible(0,null,new Set(['a']))).toBe(true);
  expect(sourceVisible(1,'a',new Set(['a']))).toBe(false);
});
