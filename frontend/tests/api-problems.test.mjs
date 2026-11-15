import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
  API_NOT_CONNECTED, SERVER_UNAVAILABLE, foreignFailureCode, isFromOsripApi, isWorthRetrying, problemOf,
} from '../src/api/problems.ts';

const headers = (values) => ({ get: (name) => values[name.toLowerCase()] ?? null });

test('the API’s own answers are recognised by its headers; a static host’s are not', () => {
  assert.equal(isFromOsripApi(headers({ 'x-request-id': 'abc', 'x-osrip-api': '0.8.0' })), true);
  // Older API releases send only X-Request-ID.
  assert.equal(isFromOsripApi(headers({ 'x-request-id': 'abc' })), true);
  // Vercel's 404 for /api/v1/... (JSON shaped like the API's error, but no API behind it).
  assert.equal(isFromOsripApi(headers({ 'x-vercel-error': 'NOT_FOUND', 'x-vercel-id': 'bom1::x' })), false);
  assert.equal(isFromOsripApi(headers({ 'x-vercel-error': 'NOT_FOUND', 'x-request-id': 'spoof' })), false);
  assert.equal(isFromOsripApi(headers({ 'content-type': 'text/html' })), false);
});

test('a host answering in the API’s place: gateway errors mean “not responding”, the rest “not connected”', () => {
  for (const status of [500, 502, 503, 504]) assert.equal(foreignFailureCode(status), SERVER_UNAVAILABLE, String(status));
  for (const status of [200, 400, 404, 405]) assert.equal(foreignFailureCode(status), API_NOT_CONNECTED, String(status));
});

test('every failure is sorted into a kind a person can act on', () => {
  const err = (status, code, message = 'm') => ({ status, code, message });
  assert.equal(problemOf(err(404, 'api_not_connected')).kind, 'not_connected');
  assert.equal(problemOf(err(0, 'server_unavailable')).kind, 'server_unavailable');
  assert.equal(problemOf(err(502, 'server_unavailable')).kind, 'server_unavailable');
  assert.equal(problemOf(err(503, 'database_unavailable')).kind, 'database_unavailable');
  assert.equal(problemOf(err(401, 'authentication_required')).kind, 'sign_in_required');
  assert.equal(problemOf(err(401, 'session_expired')).kind, 'sign_in_required');
  assert.equal(problemOf(err(403, 'forbidden')).kind, 'forbidden');
  assert.equal(problemOf(err(200, 'contract_mismatch')).kind, 'invalid_response');
  const refused = problemOf(err(422, 'invalid_request', 'Some request fields are missing or invalid.'));
  assert.deepEqual(refused, { kind: 'request_failed', status: 422, code: 'invalid_request', message: 'Some request fields are missing or invalid.' });
  // Not an API error at all (a programming error, a rejected promise with no details).
  assert.equal(problemOf(new TypeError('x')).kind, 'request_failed');
  assert.equal(problemOf(undefined).kind, 'request_failed');
  assert.equal(problemOf(err(0, 'server_unavailable')).status, null);
});

test('only failures that can pass are retried', () => {
  const err = (status, code) => ({ status, code, message: 'm' });
  assert.equal(isWorthRetrying(err(0, 'server_unavailable')), true);
  assert.equal(isWorthRetrying(err(503, 'database_unavailable')), true);
  assert.equal(isWorthRetrying(err(500, 'internal_error')), true);
  assert.equal(isWorthRetrying(err(404, 'api_not_connected')), false);
  assert.equal(isWorthRetrying(err(401, 'authentication_required')), false);
  assert.equal(isWorthRetrying(err(403, 'forbidden')), false);
  assert.equal(isWorthRetrying(err(422, 'invalid_request')), false);
});

test('Vercel serves the app for every page address but never for /api (one rule, in both possible root folders)', () => {
  const inFrontend = readFileSync(new URL('../vercel.json', import.meta.url), 'utf8');
  const atRoot = readFileSync(new URL('../../vercel.json', import.meta.url), 'utf8');
  assert.equal(atRoot, inFrontend);
  const config = JSON.parse(inFrontend);
  assert.equal(config.rewrites.length, 1);
  const [rule] = config.rewrites;
  assert.equal(rule.destination, '/index.html');
  // The source is a path-to-regexp pattern whose only group is a plain regular expression.
  const pattern = new RegExp(`^${rule.source}$`);
  for (const page of ['/', '/overview', '/energy/electricity', '/food-security', '/admin/health', '/reports/analysis/1f3c-22']) {
    assert.ok(pattern.test(page), page);
  }
  for (const other of ['/api/v1/health', '/api/v1/auth/me', '/assets/index-abc.js', '/images/photos/x.jpg', '/favicon.svg']) {
    assert.ok(!pattern.test(other), other);
  }
});
