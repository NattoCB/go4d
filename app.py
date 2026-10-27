#!/usr/bin/env python3
"""Run a dependency-free, loopback-only four-dimensional Go game."""

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from session import GameSession, RequestError

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000


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
                assets = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"), "/app.js": ("app.js", "text/javascript"), "/web-bridge.js": ("web-bridge.js", "text/javascript")}
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
