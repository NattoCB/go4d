"""Small bounded heuristic opponent, using the exact game legality evaluator.

This is a teaching opponent, not a solved four-dimensional Go strategy. It
checks at most 192 candidate placements and does not adjudicate dead groups.
"""

from __future__ import annotations

import random

from engine import EMPTY, MAX_ACTIONS, Game, IllegalMove, Point

MAX_CANDIDATES = 192


def choose_move(game: Game, seed: int | None = None) -> Point | None:
    """Choose a legal useful move, or pass; never alter the supplied game.

Candidates include threatened groups' liberties before a random sample of
other vacant points. Captures and escaping atari dominate shape preferences.
"""
    if game.finished or len(game.moves) >= MAX_ACTIONS:
        return None
    rng = random.Random(seed)
    board = game.board
    groups = []
    group_at = {}
    checked = set()
    priorities = {}
    for index, color in enumerate(board):
        if color == EMPTY or index in checked:
            continue
        stones, liberties = game._group_indices(board, index)
        checked.update(stones)
        group_number = len(groups)
        groups.append((color, stones, liberties))
        for stone in stones:
            group_at[stone] = group_number
        if len(liberties) <= 2:
            weight = (120 if len(liberties) == 1 else 12) * len(stones)
            for liberty in liberties:
                priorities[liberty] = priorities.get(liberty, 0) + weight
    tactical = sorted(priorities, key=lambda index: (-priorities[index], index))
    remainder = [index for index, color in enumerate(board)
                 if color == EMPTY and index not in priorities]
    rng.shuffle(remainder)
    candidates = (tactical + remainder)[:MAX_CANDIDATES]
    best_point = None
    best_score = 0.0
    for index in candidates:
        point = game._points[index]
        neighbors = game._adjacent[index]
        if all(board[neighbor] == game.turn for neighbor in neighbors):
            continue
        try:
            proposed, captured = game._candidate(point)
        except IllegalMove:
            continue
        own_stones, own_liberties = game._group_indices(proposed, index)
        score = 120 * len(captured) + 2 * min(len(own_liberties), 12)
        if len(own_liberties) == 1:
            score -= 85 + 8 * len(own_stones)
        touching = {group_at[n] for n in neighbors if n in group_at}
        for group_number in touching:
            color, stones, liberties = groups[group_number]
            if color == game.turn:
                score += 1.5
                if len(liberties) == 1 and len(own_liberties) > 1:
                    score += 100 * len(stones)
                elif len(liberties) == 2 and len(own_liberties) > 2:
                    score += 8 * len(stones)
            elif len(liberties) > 1:
                representative = min(stones)
                if proposed[representative] != EMPTY:
                    remaining = game._group_indices(proposed, representative)[1]
                    if len(remaining) == 1:
                        score += 18 * len(stones)
                    elif len(remaining) < len(liberties):
                        score += 2
        score += 0.3 * sum(min(value, game.size - 1 - value) for value in point)
        score += rng.random() * 0.25
        if score > best_score:
            best_score = score
            best_point = point
    return best_point
