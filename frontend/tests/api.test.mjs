import assert from 'node:assert/strict';
import { test } from 'node:test';
import { pitwallRequest } from '../lib/api.ts';

test('validation errors surface the backend explanation', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => Response.json({
    detail: [{msg: 'Latitude must be at most 90'}],
  }, {status: 422}));
  await assert.rejects(pitwallRequest('/weather'), /Latitude must be at most 90/);
});

test('invalid successful responses cannot masquerade as loaded data', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => new Response('<html>Error</html>'));
  await assert.rejects(pitwallRequest('/session'), /invalid response/);
});

test('caller cancellation reaches the request and prevents stale results', async (context) => {
  const controller = new AbortController();
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    controller.abort();
    options.signal.throwIfAborted();
  });
  await assert.rejects(pitwallRequest('/snapshot/18', undefined, controller.signal), {name:'AbortError'});
});

test('proxy errors are preserved for retry feedback', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => Response.json({detail:'API unavailable'}, {status:503}));
  await assert.rejects(pitwallRequest('/session'), /API unavailable/);
});
