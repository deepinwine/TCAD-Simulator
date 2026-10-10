import {expect, it} from 'vitest';
import {parseDisplayGeometry} from './displayGeometry';
it('reads TCADGEOM v1 micron positions, normals and indices', () => {
  const buffer = new ArrayBuffer(108); const view = new DataView(buffer);
  [...'TCADGEOM'].forEach((char,i) => view.setUint8(i,char.charCodeAt(0)));
  view.setUint32(8,1,true); view.setUint32(12,7,true); view.setUint32(16,3,true); view.setUint32(20,3,true);
  new Float32Array(buffer,24,9).set([0,0,0,1,0,0,0,1,0]); new Float32Array(buffer,60,9).set([0,0,1,0,0,1,0,0,1]);new Uint32Array(buffer,96,3).set([0,1,2]);
  const geometry = parseDisplayGeometry(buffer); expect(geometry.getAttribute('position').getX(1)).toBe(1);expect(geometry.index?.count).toBe(3); geometry.dispose();
  view.setUint32(20,30,true); expect(() => parseDisplayGeometry(buffer)).toThrow();
});
