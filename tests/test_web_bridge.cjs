const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

test('a timed-out request terminates the worker and rejects all later work', async () => {
  const callbacks = new Map();
  let timer = 0, worker;
  class FakeWorker {
    constructor() { worker = this; this.terminated = false; }
    addEventListener() {}
    postMessage() {}
    terminate() { this.terminated = true; }
  }
  const context = {
    window: {}, location: { search: '?web=1' }, document: { currentScript: { src: 'https://example.com/static/web-bridge.js' } },
    URL, URLSearchParams, Response, Worker: FakeWorker,
    setTimeout(callback) { callbacks.set(++timer, callback); return timer; },
    clearTimeout(id) { callbacks.delete(id); }
  };
  vm.runInNewContext(fs.readFileSync('static/web-bridge.js', 'utf8'), context);
  const first = context.window.GoWebBackend.request('/api/action', {});
  const second = context.window.GoWebBackend.request('/api/state', {});
  const rejected = Promise.all([assert.rejects(first, /超时/), assert.rejects(second, /超时/)]);
  callbacks.get(1)();
  assert.equal(worker.terminated, true);
  await rejected;
  assert.equal(callbacks.size, 0);
  await assert.rejects(context.window.GoWebBackend.request('/api/state', {}), /刷新/);
});

test('worker initialization failure rejects requests with recovery instructions', async () => {
  let worker;
  class FakeWorker {
    constructor() { worker = this; this.handlers = {}; this.terminated = false; }
    addEventListener(event, callback) { this.handlers[event] = callback; }
    postMessage() {}
    terminate() { this.terminated = true; }
  }
  const context = {
    window: {}, location: { search: '?web=1' }, document: { currentScript: { src: 'https://example.com/static/web-bridge.js' } },
    URL, URLSearchParams, Response, Worker: FakeWorker, setTimeout, clearTimeout
  };
  vm.runInNewContext(fs.readFileSync('static/web-bridge.js', 'utf8'), context);
  const request = context.window.GoWebBackend.request('/api/state', {});
  worker.handlers.message({data: {id: 1, error: 'CDN unavailable'}});
  await assert.rejects(request, /检查网络.*刷新/);
  assert.equal(worker.terminated, true);
});
