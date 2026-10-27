#!/usr/bin/env python3
"""Run a dependency-free, loopback-only four-dimensional Go game."""

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from ai import choose_move
from engine import BLACK, WHITE, MAX_ACTIONS, Game

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000


class RequestError(ValueError):
    """An expected HTTP input error with a user-facing status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class GameSession:
    """Serialize one local game and reject actions from stale browser views."""

    def __init__(self):
        self.game = Game()
        self.mode = "local"
        self.revision = 0
        self.lock = threading.RLock()

    def state(self):
        with self.lock:
            return {"revision": self.revision, "mode": self.mode, "game": self.game.to_dict()}

    def check_revision(self, data):
        revision = data.get("revision")
        if type(revision) is not int:
            raise RequestError("请求缺少有效的棋局版本号。")
        if revision != self.revision:
            raise RequestError("棋局已在另一页面改变，已刷新，请重新操作。", 409)

    def ai_reply(self):
        if self.mode == "ai" and not self.game.finished and self.game.turn == WHITE:
            point = choose_move(self.game)
            if point is None:
                self.game.pass_turn()
            else:
                self.game.play(point)

    def action(self, data):
        with self.lock:
            self.check_revision(data)
            action = data.get("action")
            if self.mode == "ai" and action in ("move", "pass", "resume"):
                needs_reply = (action == "move" or
                               (action == "pass" and self.game.pass_count == 0) or
                               (action == "resume" and self.game.turn == WHITE))
                if len(self.game.moves) + 1 + int(needs_reply) > MAX_ACTIONS:
                    raise RequestError("棋谱剩余容量不足以记录完整人机回合，请保存后开始新局。")
            if action == "hint":
                if self.game.finished:
                    raise RequestError("本局已结束，继续对局后才能请求提示。")
                result = self.state()
                point = choose_move(self.game)
                result["hint"] = list(point) if point is not None else None
                result["message"] = "入门启发式建议，仅供参考。" if point else "建议停着。"
                return result
            if action == "new":
                mode = data.get("mode", "local")
                if mode not in ("local", "ai"):
                    raise RequestError("对局模式应为双人或电脑。")
                game = Game(size=data.get("size", 3), komi=data.get("komi", 0.5))
                self.game, self.mode = game, mode
            elif action == "demo":
                center = (1, 1, 1, 1)
                setup = {center: WHITE}
                for axis in range(4):
                    for direction in (-1, 1):
                        neighbor = list(center)
                        neighbor[axis] += direction
                        if tuple(neighbor) != (1, 1, 1, 2):
                            setup[tuple(neighbor)] = BLACK
                self.game, self.mode = Game(setup=setup), "local"
            elif action in ("move", "pass", "resign"):
                if self.mode == "ai" and self.game.turn != BLACK:
                    raise RequestError("电脑执白，请等待电脑落子。")
                if action == "move":
                    self.game.play(data.get("point"))
                elif action == "pass":
                    self.game.pass_turn()
                else:
                    self.game.resign()
                self.ai_reply()
            elif action == "undo":
                if self.mode == "ai" and not any(move["color"] == BLACK for move in self.game.moves):
                    raise RequestError("还没有玩家操作可撤销；初始电脑手保留。")
                if not self.game.undo():
                    raise RequestError("还没有可以撤销的手数。")
                if self.mode == "ai":
                    while self.game.turn != BLACK and self.game.undo():
                        pass
            elif action == "dead":
                self.game.toggle_dead(data.get("point"))
            elif action == "resume":
                self.game.resume()
                self.ai_reply()
            else:
                raise RequestError("未知棋局操作。")
            self.revision += 1
            return self.state()

    def export(self):
        with self.lock:
            return {"format": "go4d-session-v1", "mode": self.mode, "game": self.game.export_data()}

    def import_save(self, data):
        with self.lock:
            self.check_revision(data)
            save = data.get("data")
            if not isinstance(save, dict) or save.get("format") != "go4d-session-v1":
                raise RequestError("这不是受支持的四维围棋存档。")
            mode = save.get("mode")
            if mode not in ("local", "ai"):
                raise RequestError("存档对局模式无效。")
            game = Game.from_data(save.get("game"))
            # White may be to play in an imported human game. Finish that
            # computer turn before exposing an interactive AI-mode position.
            if mode == "ai" and not game.finished and game.turn == WHITE:
                point = choose_move(game)
                game.pass_turn() if point is None else game.play(point)
            self.game, self.mode = game, mode
            self.revision += 1
            return self.state()


class GameServer(ThreadingHTTPServer):
    """Own the session without global mutable game state."""

    daemon_threads = True

    def __init__(self, port):
        self.session = GameSession()
        super().__init__(("127.0.0.1", port), GameHandler)


class GameHandler(BaseHTTPRequestHandler):
    """Serve a fixed asset list and strictly validated local JSON requests."""

    def log_message(self, format, *args):
        pass

    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        self.send_body(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def check_local(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            raise RequestError("仅接受本机游戏地址。", 403)
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in hosts}:
            raise RequestError("拒绝来自其他网站的棋局请求。", 403)

    def read_json(self):
        kind = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if kind != "application/json":
            raise RequestError("请求必须使用 JSON。", 415)
        if self.headers.get("Transfer-Encoding"):
            raise RequestError("不支持分块请求。")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise RequestError("请求长度无效。") from None
        if length < 1 or length > MAX_BODY:
            raise RequestError("存档或请求太大，最大 2 MB。", 413)
        try:
            raw = self.rfile.read(length)
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise RequestError("JSON 格式损坏。") from None
        if not isinstance(data, dict):
            raise RequestError("请求必须是一个 JSON 对象。")
        return data

    def error(self, exc):
        self.send_json(getattr(exc, "status", 400), {"error": str(exc), "state": self.server.session.state()})

    def do_GET(self):
        try:
            self.check_local()
            path = urlsplit(self.path).path
            if path == "/api/state":
                self.send_json(200, self.server.session.state())
            elif path == "/api/export":
                self.send_json(200, self.server.session.export())
            elif path == "/favicon.ico":
                self.send_body(204, b"", "image/x-icon")
            else:
                assets = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"), "/app.js": ("app.js", "text/javascript")}
                if path not in assets:
                    raise RequestError("页面不存在。", 404)
                name, kind = assets[path]
                self.send_body(200, (ROOT / "static" / name).read_bytes(), kind + "; charset=utf-8")
        except (RequestError, ValueError) as exc:
            self.error(exc)

    def do_POST(self):
        try:
            self.check_local()
            path = urlsplit(self.path).path
            if path not in ("/api/action", "/api/import"):
                raise RequestError("接口不存在。", 404)
            data = self.read_json()
            session = self.server.session
            result = session.action(data) if path == "/api/action" else session.import_save(data)
            self.send_json(200, result)
        except (RequestError, ValueError) as exc:
            self.error(exc)


def make_server(port=0):
    """Create a server; port zero asks the OS to allocate an unused port."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("端口必须为 0–65535 的整数。")
    return GameServer(port)


def main():
    parser = argparse.ArgumentParser(description="四维围棋：Python 标准库本地小游戏")
    parser.add_argument("--port", type=int, default=0, help="本地端口，默认自动选择空闲端口")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()
    try:
        server = make_server(args.port)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"无法启动游戏：{exc}\n")
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"四维围棋已启动：{url}", flush=True)
    print("关闭服务：Ctrl+C。关闭前可在游戏中下载存档。", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n游戏服务已关闭。", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
