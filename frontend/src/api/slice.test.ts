import {describe, expect, it} from 'vitest';
import * as schemas from './schemas';

const payload = (patch = {}) => ({ok: true, result: {axis: 'X', index: 1, index_max: 3, shape: [2, 2], dtype: 'u16', data_b64: 'AAABAP//AAE=', ...patch}});
describe('material slice contract', () => {
  it('decodes row-major little-endian uint16 without losing high material IDs', () => {
    expect(schemas).toHaveProperty('parseMaterialSliceEnvelope');
    const slice = schemas.parseMaterialSliceEnvelope(payload());
    expect([...slice.data]).toEqual([0, 1, 65535, 256]);
    expect(slice).toMatchObject({axis: 'x', index: 1, indexMax: 3, shape: [2, 2]});
  });
  it.each([{axis: 'Q'}, {index: -1}, {index: 4}, {index_max: 1.5}, {shape: [0, 2]}, {shape: [2, 2, 1]}, {shape: [4097, 4097]}, {dtype: 'f32'}, {data_b64: 'AA=='}, {data_b64: '%%%='}])('rejects malformed or over-budget responses %j', patch => {
    expect(schemas).toHaveProperty('parseMaterialSliceEnvelope');
    expect(() => schemas.parseMaterialSliceEnvelope(payload(patch))).toThrow();
  });
  it.each([
    {index_max:1e20}, {shape:[1,1],data_b64:'AAB='},
    {shape:[1,4097],data_b64:btoa('\0'.repeat(8194))},
  ])('rejects unsafe indices/noncanonical padding/texture dimensions before allocation', patch => {
    expect(() => schemas.parseMaterialSliceEnvelope(payload(patch))).toThrow();
  });
});
