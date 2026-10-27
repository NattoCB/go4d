/* Display geometry follows the engine's x-fast storage; legality stays on the server. */
(() => {
  "use strict";
  const AXES = ["x", "y", "z", "w"];
  const pointIndex = (p, n) => (((p[3] * n + p[2]) * n + p[1]) * n + p[0]);
  const indexPoint = (index, n) => {
    const p = [];
    for (let axis = 0; axis < 4; axis += 1) { p.push(index % n); index = Math.floor(index / n); }
    return p;
  };
  const neighbors = (p, n) => {
    const result = [];
    for (let axis = 0; axis < 4; axis += 1) {
      for (const step of [-1, 1]) {
        if (p[axis] + step >= 0 && p[axis] + step < n) {
          const next = [...p]; next[axis] += step; result.push(next);
        }
      }
    }
    return result;
  };
  const groupInfo = (board, n, p) => {
    const start = pointIndex(p, n), color = board[start];
    const stones = new Set(), liberties = new Set();
    if (!color) return {stones, liberties};
    const pending = [start]; stones.add(start);
    while (pending.length) {
      for (const q of neighbors(indexPoint(pending.pop(), n), n)) {
        const i = pointIndex(q, n);
        if (board[i] === 0) liberties.add(i);
        else if (board[i] === color && !stones.has(i)) { stones.add(i); pending.push(i); }
      }
    }
    return {stones, liberties};
  };
  globalThis.Go4DViewModel = Object.freeze({pointIndex, indexPoint, neighbors, groupInfo});
  if (typeof document === "undefined") return;

  const backendFetch = (path, options) => window.GoWebBackend ? window.GoWebBackend.request(path, options) : fetch(path, options);
  const $ = id => document.getElementById(id);
  const svgElement = (tag, attributes = {}) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    return node;
  };
  const coordinates = p => `(${p.join(", ")})`;
  const colorName = color => color === 1 ? "黑棋" : "白棋";
  const displayNumber = n => Number.isInteger(n) ? String(n) : String(Number(n.toFixed(2)));
  let state = null, busy = false, inspection = null, hintedPoint = null, notice = "", noticeError = false;
  let innerAxes = [0, 1], outerAxes = [2, 3], pointNodes = new Map(), panelNodes = [];
  const mutations = ["pass-button", "undo-button", "hint-button", "resign-button", "resume-button", "new-button", "demo-button", "load-button"];

  function setNotice(message, error = false) { notice = message; noticeError = error; renderStatus(); }
  function setBusy(value) {
    busy = value; document.body.classList.toggle("is-busy", value); renderControls();
    for (const svg of document.querySelectorAll(".slice-board")) svg.setAttribute("aria-busy", String(value));
  }
  function renderControls() {
    const g = state?.game;
    for (const id of mutations) $(id).disabled = busy || !g;
    if (!g) return;
    const aiTurn = state.mode === "ai" && g.turn === 2;
    $("pass-button").disabled = busy || g.finished || aiTurn;
    $("hint-button").disabled = busy || g.finished || aiTurn;
    $("resign-button").disabled = busy || g.finished || aiTurn;
    $("undo-button").disabled = busy || (!g.move_number && !g.finished);
    $("resume-button").hidden = !g.finished || g.resigned !== null;
    $("save-button").disabled = busy;
    for (const id of ["size-select", "mode-select", "komi-input", "inner-a", "inner-b"]) $(id).disabled = busy;
  }
  function renderStatus() {
    const banner = $("status-banner"); banner.classList.toggle("error", noticeError);
    if (busy) { banner.textContent = !state && window.GoWebBackend ? "正在加载浏览器游戏引擎，首次加载需要联网，请稍候…" : "正在计算棋局，请稍候…"; return; }
    if (notice) { banner.textContent = notice; return; }
    if (!state) { banner.textContent = "正在连接棋盘…"; return; }
    const g = state.game;
    if (g.resigned !== null) banner.textContent = `${colorName(g.resigned)}认输，${colorName(3 - g.resigned)}获胜。`;
    else if (g.finished) {
      const diff = g.score.black - g.score.white;
      banner.textContent = `${diff === 0 ? "当前平局" : `${colorName(diff > 0 ? 1 : 2)}暂胜 ${displayNumber(Math.abs(diff))} 目`}。点棋块标记死子，确认后按面积数子。`;
    } else if (g.last_captured.length) banner.textContent = `上一手提走 ${g.last_captured.length} 子。跨切片相连的棋子也会整块被提走。`;
    else if (g.pass_count) banner.textContent = "上一手停着。若下一手也停着，将进入数子。";
    else banner.textContent = "点击任一切片的交叉点落子；悬停查看跨层连接。";
  }

  async function readResponse(response) {
    let result;
    try { result = await response.json(); } catch { throw new Error("服务响应无法读取。请检查本地程序是否仍在运行。"); }
    if (!response.ok) {
      if (result.state) applyState(result.state);
      throw new Error(result.error || `请求失败 (${response.status})`);
    }
    return result;
  }
  async function action(actionName, parameters = {}) {
    if (busy || !state) return;
    setBusy(true); notice = ""; noticeError = false; renderStatus();
    try {
      const response = await backendFetch("/api/action", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({action:actionName, revision:state.revision, ...parameters})});
      const result = await readResponse(response);
      hintedPoint = actionName === "hint" ? result.hint : null;
      applyState(result);
      if (actionName === "demo") setNotice("七面已围：在 w = 2 层的 (1, 1, 1, 2) 落黑，补掉白子最后一气。");
      if (actionName === "hint") {
        if (result.hint) {
          inspection = [...result.hint]; updateInspection();
          setNotice(result.message || `试试 ${coordinates(result.hint)}。提示只来自启发式判断。`);
          pointNodes.get(pointIndex(result.hint, state.game.size))?.scrollIntoView({block:"nearest", inline:"nearest"});
        } else setNotice(result.message || "没有推荐落点，可以选择停一手。");
      }
    } catch (error) { setNotice(error.message, true); }
    finally { setBusy(false); renderStatus(); }
  }
  function applyState(next) {
    state = next;
    if (inspection && inspection.some(value => value >= state.game.size)) inspection = null;
    render();
  }

  function stoneGradient(id, colors) {
    const gradient = svgElement("radialGradient", {id,cx:"32%",cy:"24%",r:"80%"});
    for (const [offset, color] of colors) gradient.append(svgElement("stop", {offset,"stop-color":color}));
    return gradient;
  }
  function renderBoard() {
    const g = state.game, n = g.size;
    const previousFocus = document.activeElement?.dataset.point;
    const matrix = $("boards"); matrix.replaceChildren(); pointNodes = new Map(); panelNodes = [];
    matrix.style.setProperty("--slices", n);
    matrix.style.setProperty("--matrix-min", `${n * (n === 3 ? 108 : 140) + (n - 1) * 8}px`);
    $("dimension-guide").textContent = `切片内 ${AXES[innerAxes[0]]} / ${AXES[innerAxes[1]]} · 列 ${AXES[outerAxes[0]]} → · 行 ${AXES[outerAxes[1]]} ↓ · 坐标 (x, y, z, w)`;
    const dead = new Set(g.dead.map(p => pointIndex(p, n)));
    const territory = $("territory-toggle").checked;
    const radius = n === 3 ? 20 : n === 4 ? 15 : 12;
    for (let row = 0; row < n; row += 1) {
      for (let col = 0; col < n; col += 1) {
        const panel = document.createElement("section"); panel.className = "slice-panel";
        panel.dataset.row = row; panel.dataset.col = col;
        const heading = document.createElement("div"); heading.className = "slice-heading";
        const label = document.createElement("strong"); label.textContent = `${AXES[outerAxes[0]]}=${col} · ${AXES[outerAxes[1]]}=${row}`;
        const axes = document.createElement("span"); axes.textContent = `${AXES[innerAxes[0]].toUpperCase()} / ${AXES[innerAxes[1]].toUpperCase()}`;
        heading.append(label, axes); panel.append(heading);
        const svg = svgElement("svg", {viewBox:"0 0 200 200",class:"slice-board", "aria-label":`${AXES[outerAxes[0]]} 等于 ${col}，${AXES[outerAxes[1]]} 等于 ${row} 的切片`, "aria-busy":busy});
        const defs = svgElement("defs");
        defs.append(stoneGradient(`black-${row}-${col}`, [["0%","#53636c"],["40%","#1c2a31"],["100%","#090f15"]]),stoneGradient(`white-${row}-${col}`, [["0%","#fffefa"],["60%","#f3f2e5"],["100%","#c8c9b8"]]));
        svg.append(defs);
        const position = v => 28 + v * 144 / (n - 1);
        for (let i = 0; i < n; i += 1) {
          svg.append(svgElement("line", {x1:28,y1:position(i),x2:172,y2:position(i),class:"grid-line"}),svgElement("line", {x1:position(i),y1:28,x2:position(i),y2:172,class:"grid-line"}));
          const xLabel = svgElement("text", {x:position(i), y:16, "text-anchor":"middle", class:"axis-label"}); xLabel.textContent = i;
          const yLabel = svgElement("text", {x:12, y:position(i) + 3, "text-anchor":"middle", class:"axis-label"}); yLabel.textContent = i;
          svg.append(xLabel,yLabel);
        }
        for (let v = 0; v < n; v += 1) {
          for (let u = 0; u < n; u += 1) {
            const p = [0,0,0,0]; p[innerAxes[0]] = u; p[innerAxes[1]] = v; p[outerAxes[0]] = col; p[outerAxes[1]] = row;
            const index = pointIndex(p,n), color = g.board[index], cx = position(u), cy = position(v);
            if (territory && !color && g.score.territory[index]) {
              const owner = g.score.territory[index];
              svg.append(svgElement("rect", {x:cx - 4,y:cy - 4,width:8,height:8,rx:1,class:`territory-mark ${owner === 1 ? "black" : "white"}`}));
            }
            const point = svgElement("circle", {cx,cy,r:radius,class:`point-surface ${color === 1 ? "black" : color === 2 ? "white" : "empty"}${dead.has(index) ? " dead-stone" : ""}`, "data-point":p.join(","),role:"button",tabindex:0,"aria-label":`${coordinates(p)}，${color ? colorName(color) : "空点"}${dead.has(index) ? "，已标记死子" : ""}`});
            if (color) point.style.fill = `url(#${color === 1 ? "black" : "white"}-${row}-${col})`;
            point.addEventListener("pointerenter", () => { inspection = p; updateInspection(); });
            point.addEventListener("focus", () => { inspection = p; updateInspection(); });
            point.addEventListener("click", () => playPoint(p));
            point.addEventListener("keydown", event => {
              if (event.key === "Enter" || event.key === " ") { event.preventDefault(); playPoint(p); }
              else if (["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)) {
                event.preventDefault();
                const next = [...p], axis = ["ArrowLeft","ArrowRight"].includes(event.key) ? innerAxes[0] : innerAxes[1];
                next[axis] += ["ArrowLeft","ArrowUp"].includes(event.key) ? -1 : 1;
                if (next[axis] >= 0 && next[axis] < n) pointNodes.get(pointIndex(next,n))?.focus();
              }
            });
            pointNodes.set(index, point); svg.append(point);
            if (g.last_move && index === pointIndex(g.last_move,n) && color) svg.append(svgElement("circle", {cx,cy,r:3.3,class:`point-decoration last-marker ${color === 2 ? "white" : ""}`}));
            if (dead.has(index)) {
              const d = radius * .55;
              svg.append(svgElement("path", {d:`M${cx-d},${cy-d} L${cx+d},${cy+d} M${cx+d},${cy-d} L${cx-d},${cy+d}`,class:"point-decoration dead-marker"}));
            }
          }
        }
        panel.append(svg); matrix.append(panel); panelNodes.push(panel);
      }
    }
    if (previousFocus) pointNodes.get(pointIndex(previousFocus.split(",").map(Number),n))?.focus({preventScroll:true});
    updateInspection();
  }

  function playPoint(p) {
    if (busy || !state) return;
    const g = state.game;
    if (g.finished && g.resigned !== null) { setNotice("棋局已因认输结束。可以悔棋或开始新局。"); return; }
    if (g.finished) {
      if (!g.board[pointIndex(p,g.size)]) { setNotice("数子阶段请点击棋子，将整块标记为死子；再次点击可恢复。"); return; }
      action("dead", {point:p});
    } else if (state.mode === "ai" && g.turn === 2) setNotice("电脑执白，正在等待电脑落子。");
    else action("move", {point:p});
  }
  function updateInspection() {
    if (!state) return;
    const g = state.game, n = g.size;
    const index = inspection ? pointIndex(inspection,n) : -1;
    const adjacent = new Set(inspection ? neighbors(inspection,n).map(p => pointIndex(p,n)) : []);
    const info = inspection ? groupInfo(g.board,n,inspection) : {stones:new Set(),liberties:new Set()};
    const hintIndex = hintedPoint ? pointIndex(hintedPoint,n) : -1;
    for (const [i, node] of pointNodes) {
      node.classList.toggle("inspected", i === index);
      node.classList.toggle("is-neighbor", adjacent.has(i));
      node.classList.toggle("in-group", info.stones.has(i));
      node.classList.toggle("is-liberty", info.liberties.has(i));
      node.classList.toggle("hint-point", i === hintIndex);
    }
    for (const panel of panelNodes) panel.classList.toggle("contains-inspected", Boolean(inspection && Number(panel.dataset.col) === inspection[outerAxes[0]] && Number(panel.dataset.row) === inspection[outerAxes[1]]));
    if (!inspection) {
      $("inspect-title").textContent = "探索一个交叉点";
      $("inspect-description").textContent = "悬停或用 Tab 聚焦，查看四维邻点与整块的气。坐标从 0 开始。";
      return;
    }
    const cross = neighbors(inspection,n).filter(p => p[outerAxes[0]] !== inspection[outerAxes[0]] || p[outerAxes[1]] !== inspection[outerAxes[1]]).length;
    const color = g.board[index];
    $("inspect-title").textContent = `${coordinates(inspection)} · ${color ? `${colorName(color)} ${info.stones.size} 子一块 · ${info.liberties.size} 气` : `空点 · ${adjacent.size} 个直接邻点`}`;
    $("inspect-description").textContent = `${adjacent.size} 个直接邻点中，${cross} 个位于其他切片（沿 ${AXES[outerAxes[0]]} / ${AXES[outerAxes[1]]}）。${color ? "绿色标出整块棋子和所有气，跨层一起计算。" : "落子后按四轴连接计算气；只有某一坐标相差 1 才相邻。"}`;
  }

  function render() {
    const g = state.game;
    $("total-points").textContent = `${g.size ** 4} 个格点`;
    $("board-size-mark").replaceChildren(document.createTextNode(g.size));
    const exponent = document.createElement("span"); exponent.textContent = "⁴"; $("board-size-mark").append(exponent);
    $("turn-stone").className = `turn-stone ${g.turn === 1 ? "black" : "white"}`;
    $("turn-title").textContent = g.finished ? (g.resigned !== null ? "棋局结束" : "共同确认数子") : `${colorName(g.turn)}落子`;
    $("turn-subtitle").textContent = g.finished ? (g.resigned !== null ? "认输结束" : "点击棋块标记或恢复死子") : (state.mode === "ai" ? "你执黑 · 电脑执白" : "双人对弈 · 黑先白后");
    $("move-number").textContent = String(g.move_number).padStart(2,"0");
    $("black-player").textContent = state.mode === "ai" ? "你" : "玩家一";
    $("white-player").textContent = state.mode === "ai" ? "电脑" : "玩家二";
    $("black-captures").textContent = `提 ${g.captures.black}`; $("white-captures").textContent = `提 ${g.captures.white}`;
    $("black-score").textContent = displayNumber(g.score.black); $("white-score").textContent = displayNumber(g.score.white);
    $("score-title").textContent = g.finished ? "终局数子" : "预估面积";
    $("komi-label").textContent = `白贴 ${displayNumber(g.komi)}`;
    $("score-breakdown").textContent = `黑 ${g.score.black_stones} 子 + ${g.score.black_territory} 地 · 白 ${g.score.white_stones} 子 + ${g.score.white_territory} 地`;
    $("score-note").textContent = g.finished && g.resigned === null ? `已标记 ${g.dead.length} 枚死子；公气 ${g.score.neutral} 点。双方确认死活后，以此面积为结果。` : (g.resigned !== null ? "认输结果优先，面积仅供查看。" : "中盘空域变化很大，估算不代表胜负；终局需共同确认死活。");
    $("size-select").value = String(g.size); $("mode-select").value = state.mode; $("komi-input").value = String(g.komi);
    renderHistory(); renderBoard(); renderControls(); renderStatus();
  }
  function renderHistory() {
    const moves = state.game.moves, list = $("history-list"); list.replaceChildren();
    $("history-count").textContent = `${moves.length} 手`;
    if (!moves.length) { const empty = document.createElement("li"); empty.className = "history-empty"; empty.textContent = "棋局尚未开始"; list.append(empty); return; }
    for (let i = moves.length - 1; i >= Math.max(0,moves.length - 30); i -= 1) {
      const move = moves[i], item = document.createElement("li");
      const number = document.createElement("span"); number.className = "history-index"; number.textContent = String(i+1).padStart(2,"0");
      const stone = document.createElement("i"); stone.className = `small-stone ${move.color === 1 ? "black" : "white"}`;
      const name = document.createElement("span"); name.textContent = colorName(move.color);
      const text = document.createElement("span"); text.className = "history-action"; text.textContent = move.point ? coordinates(move.point) : move.action === "resign" ? "认输" : move.action === "resume" ? "继续对弈" : "停着";
      item.append(number,stone,name,text); list.append(item);
    }
  }
  function confirmDialog(title, description, buttonText = "确认") {
    const dialog = $("confirm-dialog"); $("dialog-title").textContent = title; $("dialog-description").textContent = description; $("dialog-confirm").textContent = buttonText;
    return new Promise(resolve => {
      dialog.returnValue = "cancel";
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {once:true});
      dialog.showModal();
    });
  }
  async function replaceGame(actionName) {
    if (busy || !state) return;
    const size = Number($("size-select").value), mode = $("mode-select").value, komi = Number($("komi-input").value);
    if (actionName === "new" && (!$("komi-input").value.trim() || !Number.isFinite(komi) || komi < -50 || komi > 50)) { setNotice("贴目请输入 -50 到 50 之间的数字。",true); return; }
    if ((state.game.move_number > 0 || state.game.finished) && !(await confirmDialog(actionName === "demo" ? "打开教学局面？" : "开始新局？","当前棋局将被替换。可先保存棋局，以便稍后继续。",actionName === "demo" ? "打开教学" : "开始新局"))) return;
    inspection = null;
    await action(actionName, actionName === "new" ? {size,mode,komi} : {});
  }
  async function saveGame() {
    if (busy || !state) return;
    setBusy(true);
    try {
      const data = await readResponse(await backendFetch("/api/export"));
      const blob = new Blob([JSON.stringify(data,null,2) + "\n"],{type:"application/json"});
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = `go4d-${state.game.size}x${state.game.size}-move${state.game.move_number}.json`; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url),1000);
      setNotice("棋局 JSON 已生成。可通过「读取棋局」恢复规则历史与当前局面。");
    } catch (error) { setNotice(error.message,true); }
    finally { setBusy(false); renderStatus(); }
  }
  async function loadGame(event) {
    const file = event.target.files[0]; event.target.value = "";
    if (!file || busy || !state) return;
    if (file.size > 2000000) { setNotice("存档超过 2,000,000 字节，无法读取。",true); return; }
    let data;
    try { data = JSON.parse(await file.text()); } catch { setNotice("文件不是有效的 JSON 存档，当前棋局已保留。",true); return; }
    if ((state.game.move_number > 0 || state.game.finished) && !(await confirmDialog("读取保存的棋局？",`将用 ${file.name} 替换当前棋局。未保存的落子将丢失。`,"读取棋局"))) return;
    setBusy(true); notice = ""; noticeError = false; renderStatus();
    try {
      const result = await readResponse(await backendFetch("/api/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({revision:state.revision,data})}));
      inspection = null; hintedPoint = null; applyState(result); setNotice("棋局已恢复，可以继续对弈。");
    } catch (error) { setNotice(error.message,true); }
    finally { setBusy(false); renderStatus(); }
  }
  function changeAxes(which) {
    const a = Number($("inner-a").value), b = Number($("inner-b").value);
    if (a === b) {
      if (which === 0) { $("inner-b").value = String(innerAxes[0]); innerAxes = [a,innerAxes[0]]; }
      else { $("inner-a").value = String(innerAxes[1]); innerAxes = [innerAxes[1],b]; }
    } else innerAxes = [a,b];
    outerAxes = [0,1,2,3].filter(axis => !innerAxes.includes(axis));
    if (state) renderBoard();
  }
  $("inner-a").addEventListener("change", () => changeAxes(0)); $("inner-b").addEventListener("change", () => changeAxes(1));
  $("territory-toggle").addEventListener("change", () => { if (state) renderBoard(); });
  $("pass-button").addEventListener("click", () => action("pass")); $("undo-button").addEventListener("click", () => action("undo"));
  $("hint-button").addEventListener("click", () => action("hint")); $("resume-button").addEventListener("click", () => action("resume"));
  $("new-button").addEventListener("click", () => replaceGame("new")); $("demo-button").addEventListener("click", () => replaceGame("demo"));
  $("resign-button").addEventListener("click", async () => { if (state && !busy && await confirmDialog(`${colorName(state.game.turn)}认输？`,"认输会立即结束当前棋局，对方获胜。", "确认认输")) action("resign"); });
  $("save-button").addEventListener("click", saveGame); $("load-button").addEventListener("click", () => $("load-file").click()); $("load-file").addEventListener("change", loadGame);
  $("boards").addEventListener("pointerleave", () => {
    const focused = document.activeElement?.dataset.point;
    inspection = focused ? focused.split(",").map(Number) : null; updateInspection();
  });
  async function initialize() {
    if (window.GoWebBackend) {
      $("web-session-note").hidden = false;
      $("turn-subtitle").textContent = "浏览器内运行";
      window.addEventListener("beforeunload", event => {
        if (state && state.revision > 0) { event.preventDefault(); event.returnValue = ""; }
      });
    }
    setBusy(true); renderStatus();
    try { applyState(await readResponse(await backendFetch("/api/state",{cache:"no-store"}))); }
    catch (error) { setNotice(error.message,true); }
    finally { setBusy(false); renderStatus(); }
  }
  initialize();
})();
