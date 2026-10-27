/* Only the static-hosted entry enables the browser-local backend. */
(() => {
  if (new URLSearchParams(location.search).get('web') !== '1') return;
  const workerURL = new URL('web-worker.js', document.currentScript.src);
  let worker;
  let serial = 0;
  let startupFailure = null;
  const pending = new Map();
  function failAll(message) {
    startupFailure = message;
    if (worker) worker.terminate();
    for (const { reject, timeout } of pending.values()) { clearTimeout(timeout); reject(new Error(message)); }
    pending.clear();
  }
  try {
    worker = new Worker(workerURL);
    worker.addEventListener('message', ({ data }) => {
      const request = pending.get(data.id);
      if (!request) return;
      if (data.error) { failAll('浏览器游戏引擎加载或运行失败，请检查网络后刷新页面并重新读取存档。'); return; }
      pending.delete(data.id);
      clearTimeout(request.timeout);
      request.resolve(new Response(JSON.stringify(data.body), { status: data.status, headers: { 'Content-Type': 'application/json' } }));
    });
    worker.addEventListener('error', () => failAll('浏览器游戏引擎加载失败，请检查网络后刷新页面。'));
  } catch (error) {
    startupFailure = `浏览器游戏引擎启动失败：${error.message}`;
  }
  window.GoWebBackend = {
    request(path, options = {}) {
      if (startupFailure) return Promise.reject(new Error(startupFailure));
      return new Promise((resolve, reject) => {
        const id = ++serial;
        const timeout = setTimeout(() => {
          failAll('游戏引擎加载或计算超时，已停止运行。请刷新页面并重新读取存档。');
        }, 60000);
        pending.set(id, { resolve, reject, timeout });
        worker.postMessage({ id, path, body: options.body ? JSON.parse(options.body) : null });
      });
    }
  };
})();
