import {describe, expect, it} from 'vitest';
import {Buffer} from 'node:buffer';
import * as schemas from './schemas';

const payload = (patch = {}) => ({ok: true, result: {axis: 'X', index: 1, index_max: 3, shape: [2, 2], dtype: 'u16', data_b64: 'AAABAP//AAE=', ...patch}});
describe('material slice contract', () => {
  it.each([0, 65535])('decodes a budget-sized rectangular slice with material ID %i', materialId => {
    const bytes = Buffer.alloc(1024 * 2048 * 2, materialId === 0 ? 0 : 255);
    const slice = schemas.parseMaterialSliceEnvelope(payload({shape: [1024, 2048], data_b64: bytes.toString('base64')}));
    expect(slice.shape).toEqual([1024, 2048]);
    expect(slice.data.length).toBe(1024 * 2048);
    expect(slice.data.every(value => value === materialId)).toBe(true);
  });
  it.each(['illegal character', 'interior padding', 'missing padding', 'noncanonical tail', 'truncated'])('rejects a large slice with %s as a contract error', corruption => {
    const encoded = Buffer.alloc(1024 * 2048 * 2).toString('base64');
    const data_b64 = corruption === 'illegal character' ? encoded.slice(0, -3) + '!=='
      : corruption === 'interior padding' ? encoded.slice(0, -8) + '=' + encoded.slice(-7)
      : corruption === 'missing padding' ? encoded.slice(0, -2) + 'AA'
      : corruption === 'noncanonical tail' ? encoded.slice(0, -3) + 'B=='
      : encoded.slice(0, -4);
    expect(() => schemas.parseMaterialSliceEnvelope(payload({shape: [1024, 2048], data_b64}))).toThrow(schemas.ApiContractError);
  });
  it.each(['X', 'Y', 'Z'])('normalizes valid string axis %s', axis => {
    expect(schemas.parseMaterialSliceEnvelope(payload({axis})).axis).toBe(axis.toLowerCase());
  });
  it.each([['X'], ['Y'], ['Z'], [], {}, null, 0, true, undefined].map(axis => ({axis})))('rejects non-string axis %j', ({axis}) => {
    expect(() => schemas.parseMaterialSliceEnvelope(payload({axis}))).toThrow(/result.axis/);
  });
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
