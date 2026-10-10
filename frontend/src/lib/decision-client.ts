import contracts from './contracts.json';
import { packetId, valid } from './api';
import type { DecisionResult } from './types';

export class DecisionFailure extends Error {
  constructor(public code: string) { super(code); }
}
export const failureCodes = ['invalid_host', 'authentication_required', 'local_only', 'authorization_failed',
  'unauthorized_identity', 'csrf_failed', 'not_found', 'stale_packet', 'stale_approval_view', 'decision_conflict',
  'packet_integrity_failed', 'approval_not_current', 'invalid_request', 'packet_busy', 'storage_unavailable'];

async function responseData(response: Response): Promise<unknown> {
  if (!response.ok && response.status < 500) {
    const data = await response.json().catch(() => null);
    const code = data?.error?.code;
    throw new DecisionFailure(typeof code === 'string' && failureCodes.includes(code) ? code : 'invalid_request');
  }
  // A server failure, invalid success body or unreadable response can follow a
  // commit. Only a recognized, sanitized backend rejection is a known failure.
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (failureCodes.includes(data?.error?.code)) throw new DecisionFailure(data.error.code);
    throw new Error('ambiguous');
  }
  if (!response.headers.get('content-type')?.startsWith('application/json')) throw new Error('ambiguous');
  return response.json();
}

export interface DecisionTransport {
  bootstrap(signal: AbortSignal): Promise<string>;
  post(id: string, action: 'approve' | 'reject' | 'revise', body: Record<string, string>, token: string): Promise<DecisionResult>;
}
export const decisionClient: DecisionTransport = {
  async bootstrap(signal) {
    const response = await fetch('/api/bootstrap', {method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal, headers: {Accept: 'application/json'}});
    const data = await responseData(response);
    if ((!valid(data, contracts.BootstrapResponse) && !valid(data, contracts.TailscaleBootstrapResponse)) ||
        !data || typeof data !== 'object' || !('csrf_token' in data) || typeof data.csrf_token !== 'string' || !data.csrf_token) throw new Error('unavailable');
    return data.csrf_token;
  },
  async post(id, action, body, token) {
    packetId(id);
    if (!['approve', 'reject', 'revise'].includes(action)) throw new DecisionFailure('invalid_request');
    const response = await fetch(`/api/packets/${id}/${action}`, {method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: {Accept: 'application/json', 'Content-Type': 'application/json', 'X-Job-Pilot-CSRF': token}, body: JSON.stringify(body)});
    const data = await responseData(response);
    if (!valid(data, contracts.DecisionResult)) throw new Error('ambiguous');
    return data as DecisionResult;
  },
};
