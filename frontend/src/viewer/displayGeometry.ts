import {BufferGeometry, BufferAttribute} from 'three';

/** Decode the existing backend TCADGEOM v1 protocol; coordinates stay in µm. */
export function parseDisplayGeometry(buffer: ArrayBuffer): BufferGeometry {
  const view = new DataView(buffer);
  if (buffer.byteLength < 24
    || String.fromCharCode(...new Uint8Array(buffer, 0, 8)) !== 'TCADGEOM'
    || view.getUint32(8, true) !== 1) throw new Error('Invalid TCADGEOM v1 header');
  const flags = view.getUint32(12, true);
  const vertices = view.getUint32(16, true);
  const indices = view.getUint32(20, true);
  const size = 24 + vertices * 12 + ((flags & 2) ? vertices * 12 : 0) + indices * 4;
  if ((flags & ~7) !== 0 || vertices > 3_000_000 || indices > 3_000_000
    || indices % 3 || size !== buffer.byteLength) throw new Error('Invalid TCADGEOM payload');
  let offset = 24;
  const positions = new Float32Array(buffer, offset, vertices * 3);
  offset += vertices * 12;
  if (positions.some(value => !Number.isFinite(value))) throw new Error('Invalid TCADGEOM position');
  let normals: Float32Array | null = null;
  if (flags & 2) {
    normals = new Float32Array(buffer, offset, vertices * 3);
    offset += vertices * 12;
  }
  const index = new Uint32Array(buffer, offset, indices);
  if (index.some(value => value >= vertices)) throw new Error('Invalid TCADGEOM index');
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  if (normals) geometry.setAttribute('normal', new BufferAttribute(normals, 3));
  if (indices) geometry.setIndex(new BufferAttribute(index, 1));
  if (!normals) geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}
