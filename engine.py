"""Finite four-dimensional Go using orthogonal adjacency and positional superko.

Coordinates are (x, y, z, w). Flat boards store x fastest. Territory uses
area scoring on the same graph; marked dead stones are removed only for scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

EMPTY = 0
BLACK = 1
WHITE = 2
Point = tuple[int, int, int, int]
MAX_ACTIONS = 3000


class IllegalMove(ValueError):
    """An attempted action violates the rules or the current game phase."""


@dataclass(frozen=True)
class _Snapshot:
    board: tuple[int, ...]
    turn: int
    captures: tuple[int, int]
    move_number: int
    pass_count: int
    finished: bool
    resigned: int | None
    last_move: Point | None
    last_captured: tuple[Point, ...]
    dead: frozenset[int]


class Game:
    """A mutable local game; unsuccessful actions leave every field unchanged."""

    def __init__(self, size: int = 3, komi: float = 0.5,
                 setup: dict[Point, int] | None = None, turn: int = BLACK):
        if type(size) is not int or not 3 <= size <= 5:
            raise ValueError("棋盘每轴大小必须是 3、4 或 5")
        if type(komi) not in (int, float) or not -50 <= komi <= 50 or not math.isfinite(komi):
            raise ValueError("贴目必须是 -50 到 50 之间的有限数值")
        self._validate_color(turn)
        if setup is not None and type(setup) is not dict:
            raise ValueError("初始局面必须是坐标到颜色的字典")
        self.size = size
        self.komi = float(komi)
        self._points = [self._point(i) for i in range(size ** 4)]
        self._adjacent: list[tuple[int, ...]] = []
        for point in self._points:
            neighbors = []
            for axis in range(4):
                for step in (-1, 1):
                    other = list(point)
                    other[axis] += step
                    if 0 <= other[axis] < size:
                        neighbors.append(self._index(tuple(other)))
            self._adjacent.append(tuple(neighbors))
        self.board = [EMPTY] * (size ** 4)
        for point, color in (setup or {}).items():
            point = self._validate_point(point)
            self._validate_color(color)
            self.board[self._index(point)] = color
        checked = set()
        for index, color in enumerate(self.board):
            if color and index not in checked:
                stones, liberties = self._group_indices(self.board, index)
                if not liberties:
                    raise ValueError("初始局面包含无气棋块")
                checked.update(stones)
        self.turn = turn
        self.captures = {"black": 0, "white": 0}
        self.move_number = 0
        self.pass_count = 0
        self.finished = False
        self.resigned: int | None = None
        self.last_move: Point | None = None
        self.last_captured: list[Point] = []
        self.dead: set[int] = set()
        self.moves: list[dict[str, Any]] = []
        self._history: list[_Snapshot] = []
        self._initial_board = tuple(self.board)
        self._initial_turn = turn
        self._seen = {self._initial_board}

    @staticmethod
    def _validate_color(color: Any) -> None:
        if type(color) is not int or color not in (BLACK, WHITE):
            raise ValueError("棋子颜色必须是 1（黑）或 2（白）")

    def _validate_point(self, point: Any) -> Point:
        if type(point) not in (tuple, list) or len(point) != 4:
            raise IllegalMove("坐标必须包含 x、y、z、w 四个整数")
        if any(type(value) is not int or not 0 <= value < self.size for value in point):
            raise IllegalMove("坐标超出棋盘，或包含非整数")
        return tuple(point)

    def _index(self, point: Point) -> int:
        x, y, z, w = point
        n = self.size
        return (((w * n + z) * n + y) * n + x)

    def _point(self, index: int) -> Point:
        n = self.size
        return (index % n, index // n % n, index // (n * n) % n, index // (n ** 3))

    def neighbors(self, point: Point) -> list[Point]:
        """Return in-bounds orthogonal neighbors along all four axes."""
        return [self._points[index] for index in self._adjacent[self._index(self._validate_point(point))]]

    def _group_indices(self, board: list[int], start: int) -> tuple[set[int], set[int]]:
        color = board[start]
        if color == EMPTY:
            return set(), set()
        stones = {start}
        liberties = set()
        pending = [start]
        while pending:
            for neighbor in self._adjacent[pending.pop()]:
                if board[neighbor] == EMPTY:
                    liberties.add(neighbor)
                elif board[neighbor] == color and neighbor not in stones:
                    stones.add(neighbor)
                    pending.append(neighbor)
        return stones, liberties

    def group(self, point: Point) -> tuple[set[Point], set[Point]]:
        """Return the full same-color component and its distinct liberties."""
        index = self._index(self._validate_point(point))
        stones, liberties = self._group_indices(self.board, index)
        return {self._points[i] for i in stones}, {self._points[i] for i in liberties}

    def _require_active(self) -> None:
        if self.finished:
            raise IllegalMove("棋局已结束；数子结束后可继续对弈")

    def _snapshot(self) -> _Snapshot:
        return _Snapshot(tuple(self.board), self.turn,
                         (self.captures["black"], self.captures["white"]),
                         self.move_number, self.pass_count, self.finished, self.resigned,
                         self.last_move, tuple(self.last_captured), frozenset(self.dead))

    def _record(self, action: str, point: Point | None = None) -> None:
        if len(self.moves) >= MAX_ACTIONS:
            raise IllegalMove("棋谱最多支持 3000 次操作，请开始新局")
        self._history.append(self._snapshot())
        self.moves.append({"color": self.turn, "action": action, "point": point})

    def _candidate(self, point: Point) -> tuple[list[int], list[int]]:
        """Evaluate one placement without mutating state; also used by the AI."""
        point = self._validate_point(point)
        index = self._index(point)
        if self.board[index] != EMPTY:
            raise IllegalMove("这里已有棋子")
        board = self.board.copy()
        board[index] = self.turn
        captured = set()
        checked = set()
        enemy = 3 - self.turn
        for neighbor in self._adjacent[index]:
            if board[neighbor] == enemy and neighbor not in checked:
                stones, liberties = self._group_indices(board, neighbor)
                checked.update(stones)
                if not liberties:
                    captured.update(stones)
        for victim in captured:
            board[victim] = EMPTY
        if not self._group_indices(board, index)[1]:
            raise IllegalMove("禁自杀：落子后己方棋块没有气")
        if tuple(board) in self._seen:
            raise IllegalMove("位置超级劫：不能重现本局已经出现的棋盘")
        return board, sorted(captured)

    def play(self, point: Point) -> list[Point]:
        """Place the current color, capture enemies, and advance the turn."""
        self._require_active()
        point = self._validate_point(point)
        board, captured = self._candidate(point)
        self._record("move", point)
        self.board = board
        self._seen.add(tuple(board))
        self.last_move = point
        self.last_captured = [self._points[i] for i in captured]
        self.captures["black" if self.turn == BLACK else "white"] += len(captured)
        self.move_number += 1
        self.pass_count = 0
        self.turn = 3 - self.turn
        return self.last_captured.copy()

    def pass_turn(self) -> None:
        """Pass without a superko check; two consecutive passes enter scoring."""
        self._require_active()
        self._record("pass")
        self.move_number += 1
        self.pass_count += 1
        self.last_captured = []
        self.turn = 3 - self.turn
        self.finished = self.pass_count == 2

    def resign(self) -> None:
        """Finish the game with the current color as the resigned player."""
        self._require_active()
        self._record("resign")
        self.move_number += 1
        self.finished = True
        self.resigned = self.turn
        self.last_captured = []

    def undo(self) -> bool:
        """Undo one action, including its superko restriction; return whether undone."""
        if not self._history:
            return False
        action = self.moves.pop()
        if action["action"] == "move":
            self._seen.remove(tuple(self.board))
        state = self._history.pop()
        self.board = list(state.board)
        self.turn = state.turn
        self.captures = {"black": state.captures[0], "white": state.captures[1]}
        self.move_number = state.move_number
        self.pass_count = state.pass_count
        self.finished = state.finished
        self.resigned = state.resigned
        self.last_move = state.last_move
        self.last_captured = list(state.last_captured)
        self.dead = set(state.dead)
        return True

    def toggle_dead(self, point: Point) -> None:
        """During scoring, toggle a whole connected group as agreed dead stones."""
        if not self.finished or self.resigned is not None:
            raise IllegalMove("只可在双方停着后的数子阶段标记死子")
        index = self._index(self._validate_point(point))
        stones, _ = self._group_indices(self.board, index)
        if not stones:
            raise IllegalMove("请选择棋子所在位置")
        if stones <= self.dead:
            self.dead.difference_update(stones)
        else:
            self.dead.update(stones)

    def resume(self) -> None:
        """Resume a scoring phase, clear dead marks, and retain board history."""
        if not self.finished or self.resigned is not None:
            raise IllegalMove("只可从双方停着后的数子阶段继续")
        self._record("resume")
        self.finished = False
        self.pass_count = 0
        self.dead.clear()

    def _score(self) -> dict[str, Any]:
        board = [EMPTY if i in self.dead else stone for i, stone in enumerate(self.board)]
        territory = [EMPTY] * len(board)
        counts = {BLACK: 0, WHITE: 0}
        neutral = 0
        checked = set()
        for index, color in enumerate(board):
            if color != EMPTY or index in checked:
                continue
            region = {index}
            boundaries = set()
            pending = [index]
            checked.add(index)
            while pending:
                for neighbor in self._adjacent[pending.pop()]:
                    if board[neighbor] != EMPTY:
                        boundaries.add(board[neighbor])
                    elif neighbor not in checked:
                        checked.add(neighbor)
                        region.add(neighbor)
                        pending.append(neighbor)
            owner = next(iter(boundaries)) if len(boundaries) == 1 else EMPTY
            if owner:
                counts[owner] += len(region)
                for empty in region:
                    territory[empty] = owner
            else:
                neutral += len(region)
        black_stones = board.count(BLACK)
        white_stones = board.count(WHITE)
        return {"black": black_stones + counts[BLACK],
                "white": white_stones + counts[WHITE] + self.komi,
                "black_stones": black_stones, "white_stones": white_stones,
                "black_territory": counts[BLACK], "white_territory": counts[WHITE],
                "neutral": neutral, "territory": territory}

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible view, including provisional area score."""
        return {"size": self.size, "komi": self.komi, "board": self.board.copy(),
                "turn": self.turn, "captures": self.captures.copy(),
                "move_number": self.move_number, "pass_count": self.pass_count,
                "finished": self.finished, "resigned": self.resigned,
                "last_move": list(self.last_move) if self.last_move is not None else None,
                "last_captured": [list(p) for p in self.last_captured],
                "dead": [list(self._points[i]) for i in sorted(self.dead)],
                "moves": [{**m, "point": list(m["point"]) if m["point"] is not None else None}
                          for m in self.moves], "score": self._score()}

    def export_data(self) -> dict[str, Any]:
        """Export validated replay data and scoring annotations, without mutable aliases."""
        state = self.to_dict()
        return {"format": "go4d", "version": 1, "size": self.size, "komi": self.komi,
                "turn": self._initial_turn,
                "setup": [{"point": list(self._points[i]), "color": color}
                          for i, color in enumerate(self._initial_board) if color],
                "moves": state["moves"], "dead": state["dead"],
                "dead_history": [[list(self._points[i]) for i in sorted(snapshot.dead)]
                                 for snapshot in self._history]}

    def _load_dead(self, points: Any) -> None:
        if type(points) is not list or len(points) > len(self.board):
            raise ValueError("死子标记必须是棋盘内坐标数组")
        indices = set()
        for point in points:
            index = self._index(self._validate_saved_point(point))
            if index in indices or self.board[index] == EMPTY:
                raise ValueError("死子标记包含重复点或空点")
            indices.add(index)
        if indices and (not self.finished or self.resigned is not None):
            raise ValueError("死子标记只能存在于数子阶段")
        for index in indices:
            if not self._group_indices(self.board, index)[0] <= indices:
                raise ValueError("死子标记必须涵盖完整棋块")
        self.dead = indices

    def _validate_saved_point(self, point: Any) -> Point:
        if type(point) is not list:
            raise ValueError("存档坐标必须是 JSON 数组")
        return self._validate_point(point)

    @classmethod
    def from_data(cls, data: Any) -> Game:
        """Validate and replay a save; reject malformed input without repairing it."""
        expected = {"format", "version", "size", "komi", "turn", "setup", "moves", "dead", "dead_history"}
        if type(data) is not dict or set(data) != expected:
            raise ValueError("存档字段缺失、未知或格式错误")
        if data["format"] != "go4d" or type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("不支持的四维围棋存档版本")
        game = cls(data["size"], data["komi"], turn=data["turn"])
        if type(data["setup"]) is not list or len(data["setup"]) > len(game.board):
            raise ValueError("初始局面格式错误")
        setup = {}
        for stone in data["setup"]:
            if type(stone) is not dict or set(stone) != {"point", "color"}:
                raise ValueError("初始棋子格式错误")
            point = game._validate_saved_point(stone["point"])
            game._validate_color(stone["color"])
            if point in setup:
                raise ValueError("初始局面包含重复坐标")
            setup[point] = stone["color"]
        game = cls(data["size"], data["komi"], setup, data["turn"])
        moves = data["moves"]
        annotations = data["dead_history"]
        if type(moves) is not list or len(moves) > MAX_ACTIONS:
            raise ValueError("棋谱必须是最多 3000 次操作的数组")
        if type(annotations) is not list or len(annotations) != len(moves):
            raise ValueError("死子历史必须与棋谱操作一一对应")
        for number, move in enumerate(moves):
            if type(move) is not dict or set(move) != {"color", "action", "point"}:
                raise ValueError("棋谱操作格式错误")
            game._validate_color(move["color"])
            if move["color"] != game.turn:
                raise ValueError("棋谱行棋颜色与回合不符")
            action = move["action"]
            if type(action) is not str or action not in ("move", "pass", "resign", "resume"):
                raise ValueError("未知棋谱操作")
            if action != "move" and move["point"] is not None:
                raise ValueError("非落子操作不可携带坐标")
            game._load_dead(annotations[number])
            if action == "move":
                game.play(game._validate_saved_point(move["point"]))
            elif action == "pass":
                game.pass_turn()
            elif action == "resign":
                game.resign()
            else:
                game.resume()
        game._load_dead(data["dead"])
        return game
