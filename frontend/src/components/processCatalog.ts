import type {MaterialView, StepView} from '../api/types';
import type {TranslationKey} from '../i18n/catalogs';
export const processCatalog: readonly {id: string; key: TranslationKey}[] = [
  {id: 'Pattern', key: 'processType.pattern'}, {id: 'Etch', key: 'processType.etch'}, {id: 'Deposit', key: 'processType.deposit'},
  {id: 'Oxidation', key: 'processType.oxidation'}, {id: 'Epitaxy', key: 'processType.epitaxy'}, {id: 'Strip', key: 'processType.strip'},
  {id: 'Planarize', key: 'processType.cmp'}, {id: 'Doping', key: 'processType.doping'},
];
export function isInitializer(step: StepView): boolean {return step.index === 0 && ['Structure Wafer', 'Initialize Wafer'].includes(step.name);}
export function isStructureFlow(recipe: readonly StepView[]): boolean {return recipe.length > 0 && recipe.every(step => step.name.startsWith('Structure ') || isInitializer(step));}
export function visibleSteps(recipe: StepView[]): StepView[] {return isStructureFlow(recipe) ? recipe.filter(step => !isInitializer(step)) : recipe;}
export function candidateStep(source: StepView, template: StepView, materials: MaterialView[] = []): StepView {
  const params = {...template.params};
  const material = template.parameterSpecs.find(spec => spec.key === 'material');
  const sourceMaterial = typeof source.params.material === 'number' ? materials.find(item => item.id === source.params.material)?.name ?? source.params.material : source.params.material;
  if (material?.choices?.some(([value]) => Object.is(value, sourceMaterial))) params.material = sourceMaterial;
  return {...template, params, instanceName: source.instanceName !== source.name && source.instanceName ? source.instanceName : template.name};
}
