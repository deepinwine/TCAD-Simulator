import {expect, it} from 'vitest';
import {processCatalog, candidateStep} from './processCatalog';
import type {StepView} from '../api/types';
const step = (name: string, params: Record<string, unknown>, instanceName = name): StepView => ({index: 3, name, instanceName, params, parameterSpecs: [], enabled: true, group: '', loop: '', runtimeStatus: 'ready'});
it('offers exactly eight process categories in approved order', () => {
  expect(processCatalog.map(item => item.id)).toEqual(['Pattern', 'Etch', 'Deposit', 'Oxidation', 'Epitaxy', 'Strip', 'Planarize', 'Doping']);
});
it('uses candidate defaults and only inherits compatible material and custom name', () => {
  const template = step('Structure Etch', {material: 'Si', depth_nm: 20});
  template.parameterSpecs = [{key: 'material', label: 'material', type: 'choice', choices: [['Si', 'Si'], ['Poly', 'Poly']]}];
  for (const source of [...processCatalog.map(item => `Structure ${item.id}`), 'Legacy process']) {
    expect(candidateStep(step(source, {material: 'Poly', thickness_nm: 500}), template)).toMatchObject({params: {material: 'Poly', depth_nm: 20}, instanceName: 'Structure Etch'});
  }
  expect(candidateStep(step('Structure Deposit', {material: 'W'}, 'contact'), template)).toMatchObject({params: {material: 'Si', depth_nm: 20}, instanceName: 'contact'});
});
