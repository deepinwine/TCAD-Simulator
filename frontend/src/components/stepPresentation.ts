import type {MaterialView, StepView} from '../api/types';
import type {Locale} from '../i18n/catalogs';
const operations: Record<string, [string, string, string, string]> = {
  Wafer: ['晶圆', 'Wafer', '创建指定材料与厚度的基础晶圆。', 'Create the base wafer with the selected material and thickness.'],
  Deposit: ['沉积', 'Deposit', '在表面添加指定材料；厚度为新增膜厚。', 'Add material to the surface; thickness is the added film thickness.'],
  Etch: ['刻蚀', 'Etch', '移除指定材料；深度为向下移除的距离。', 'Remove the selected material downward by the specified depth.'],
  Pattern: ['图形', 'Pattern', '定义后续结构操作使用的掩膜开口。', 'Define mask openings for subsequent structure operations.'],
  Fill: ['填充', 'Fill', '将开口填充至指定的绝对高度。', 'Fill openings up to the specified absolute height.'],
  Planarize: ['平坦化', 'Planarize', '移除指定绝对高度以上的材料。', 'Remove material above the specified absolute height.'],
};
export function materialLabel(value: unknown, materials: MaterialView[]): string {
  const name = typeof value === 'number' ? materials.find(material => material.id === value)?.name ?? String(value) : typeof value === 'string' ? value : '';
  return ({'Silicon Dioxide': 'SiO₂', SiO2: 'SiO₂', Silicon: 'Si', 'Silicon Nitride': 'Si₃N₄', Si3N4: 'Si₃N₄'} as Record<string, string>)[name] ?? name;
}
export function presentStep(step: StepView, materials: MaterialView[], locale: Locale) {
  const operation = step.name.startsWith('Structure ') ? step.name.slice(10) : step.name === 'Deposition' ? 'Deposit' : step.name;
  const copy = operations[operation];
  if (!copy) return {title: step.instanceName, type: step.name, description: ''};
  const english = locale === 'en';
  const label = copy[english ? 1 : 0];
  const material = materialLabel(step.params.material, materials);
  const key = operation === 'Etch' ? 'depth_nm' : operation === 'Fill' || operation === 'Planarize' ? 'height_nm' : operation === 'Pattern' ? 'critical_dimension' : 'thickness_nm';
  const value = step.params[key] ?? (operation === 'Deposit' ? step.params.thickness : undefined);
  const prefix = operation === 'Etch' ? (english ? 'Depth ' : '深度 ') : operation === 'Fill' || operation === 'Planarize' ? (english ? 'Height ' : '高度 ') : operation === 'Pattern' ? 'CD ' : '';
  const summary = [label, material, typeof value === 'number' ? `${prefix}${value} nm` : ''].filter(Boolean).join(' · ');
  return {title: step.instanceName && step.instanceName !== step.name ? step.instanceName : summary, type: `${label} / ${copy[1]}`, description: copy[english ? 3 : 2]};
}
