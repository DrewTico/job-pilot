import contracts from './contracts.json';
import type { Reader } from './types';

type Schema = { $ref?: string; $defs?: Record<string, Schema>; anyOf?: Schema[]; type?: string;
  enum?: unknown[]; const?: unknown; properties?: Record<string, Schema>; required?: string[];
  additionalProperties?: boolean; items?: Schema; pattern?: string; minimum?: number; maximum?: number };

// Snapshot generated from the protected Pydantic read DTOs. No permissive casts
// of unknown API data into positive-looking status. Invalid responses fail closed.
export function valid(value: unknown, schema: Schema, root = schema): boolean {
  if (schema.$ref) {
    const reference = root.$defs?.[schema.$ref.split('/').at(-1)!];
    return Boolean(reference && valid(value, reference, root));
  }
  if (schema.anyOf) return schema.anyOf.some(item => valid(value, item, root));
  if (schema.enum && !schema.enum.includes(value)) return false;
  if ('const' in schema && value !== schema.const) return false;
  if (schema.type === 'null') return value === null;
  if (schema.type === 'boolean') return typeof value === 'boolean';
  if (schema.type === 'string') return typeof value === 'string' && (!schema.pattern || new RegExp(schema.pattern).test(value));
  if (schema.type === 'integer' || schema.type === 'number') return typeof value === 'number' && Number.isFinite(value) &&
    (schema.type !== 'integer' || Number.isInteger(value)) && (schema.minimum === undefined || value >= schema.minimum) && (schema.maximum === undefined || value <= schema.maximum);
  if (schema.type === 'array') return Array.isArray(value) && value.every(item => valid(item, schema.items ?? {}, root));
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const object = value as Record<string, unknown>;
    if (schema.required?.some(key => !Object.hasOwn(object, key))) return false;
    const properties = schema.properties ?? {};
    return Object.entries(object).every(([key, item]) => Object.hasOwn(properties, key) ? valid(item, properties[key], root) : schema.additionalProperties !== false);
  }
  return true;
}
export function packetId(id: string) { if (!/^[0-9a-f]{32}$/.test(id)) throw new Error('invalid_request'); return id; }
async function read<T>(path: string, contract: keyof typeof contracts, signal: AbortSignal): Promise<T> {
  if (!/^\/api\/(?:queue\?section=(?:needs-review|processing|needs-attention|history)&limit=25&offset=\d+|packets\/[0-9a-f]{32}(?:\/decision-detail|\/diff\/(?:resume|cover)\/[0-9a-f]{32})?)$/.test(path)) throw new Error('invalid_request');
  const response = await fetch(path, { method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal, headers: { Accept: 'application/json' } });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const code: unknown = data?.error?.code;
    const allowed = ['authentication_required', 'unauthorized_identity', 'stale_packet', 'stale_approval_view', 'approval_not_current', 'packet_integrity_failed'];
    const fallback: Record<number, string> = {401: 'authentication_required', 403: 'unauthorized_identity'};
    throw new Error(typeof code === 'string' && allowed.includes(code) ? code : fallback[response.status] ?? 'unavailable');
  }
  if (!response.headers.get('content-type')?.startsWith('application/json')) throw new Error('unavailable');
  const data: unknown = await response.json();
  if (!valid(data, contracts[contract] as Schema)) throw new Error('unavailable');
  return data as T;
}
export const api: Reader = {
  queue: (section, offset, signal) => read(`/api/queue?section=${section}&limit=25&offset=${offset}`, 'QueueResponse', signal),
  packet: (id, signal) => read(`/api/packets/${packetId(id)}`, 'PacketDetail', signal),
  decision: (id, signal) => read(`/api/packets/${packetId(id)}/decision-detail`, 'DecisionDetail', signal),
  diff: (left, right, kind, signal) => read(`/api/packets/${packetId(left)}/diff/${kind}/${packetId(right)}`, 'PacketDiffResult', signal),
};
