import type {StepView} from '../api/types';
import type {TranslationKey} from '../i18n/catalogs';
export const processCatalog: readonly {id: string; key: TranslationKey}[] = [
  {id: 'Pattern', key: 'processType.pattern'}, {id: 'Etch', key: 'processType.etch'}, {id: 'Deposit', key: 'processType.deposit'},
  {id: 'Oxidation', key: 'processType.oxidation'}, {id: 'Epitaxy', key: 'processType.epitaxy'}, {id: 'Strip', key: 'processType.strip'},
  {id: 'Planarize', key: 'processType.cmp'}, {id: 'Doping', key: 'processType.doping'},
];
export function isInitializer(step: StepView): boolean {return step.index === 0 && ['Structure Wafer', 'Initialize Wafer'].includes(step.name);}
export function candidateStep(source: StepView, template: StepView): StepView {
  const params = {...template.params};
  const material = template.parameterSpecs.find(spec => spec.key === 'material');
  if (material?.choices?.some(([value]) => Object.is(value, source.params.material))) params.material = source.params.material;
  return {...template, params, instanceName: source.instanceName !== source.name && source.instanceName ? source.instanceName : template.name};
}
