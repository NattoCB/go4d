/* Run the existing Python rules inside a dedicated browser worker. */
const runtimeURL = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
const ready = (async () => {
  importScripts(`${runtimeURL}pyodide.js`);
  const pyodide = await loadPyodide({ indexURL: runtimeURL });
  const files = ['engine.py', 'ai.py', 'session.py', 'web_session.py'];
  await Promise.all(files.map(async file => {
    const response = await fetch(new URL(`../${file}`, self.location.href));
    if (!response.ok) throw new Error(`无法加载游戏文件 ${file} (${response.status})`);
    pyodide.FS.writeFile(file, await response.text(), { encoding: 'utf8' });
  }));
  pyodide.runPython('import json\nfrom web_session import BrowserSession\nbrowser_session = BrowserSession()');
  return pyodide;
})();

self.onmessage = async ({ data }) => {
  try {
    const pyodide = await ready;
    pyodide.globals.set('_request_path', data.path);
    pyodide.globals.set('_request_json', JSON.stringify(data.body ?? null));
    const response = pyodide.runPython('json.dumps(browser_session.request(_request_path, json.loads(_request_json)), ensure_ascii=False, allow_nan=False)');
    const [status, body] = JSON.parse(response);
    self.postMessage({ id: data.id, status, body });
  } catch (error) {
    self.postMessage({ id: data.id, error: error.message || String(error) });
  }
};
