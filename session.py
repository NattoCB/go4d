"""Shared game session for the local server and browser runtime."""

import threading

from ai import choose_move
from engine import BLACK, WHITE, MAX_ACTIONS, Game


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
