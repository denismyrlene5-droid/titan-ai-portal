from dataclasses import dataclass
from typing import Optional

N = 10

@dataclass(frozen=True)
class Move:
    player: int
    start: tuple[int, int]
    end: tuple[int, int]
    captures: tuple[tuple[int, int], ...] = ()
    promoted: bool = False
    confidence: float = 0.0

def infer_move(before: list[list[int]], after: list[list[int]], player: int) -> Optional[Move]:
    own = {1, 3} if player == 1 else {2, 4}
    opp = {2, 4} if player == 1 else {1, 3}
    removed_own, added_own, removed_opp = [], [], []

    for r in range(N):
        for c in range(N):
            b, a = before[r][c], after[r][c]
            if b in own and a not in own:
                removed_own.append((r, c))
            if a in own and b not in own:
                added_own.append((r, c))
            if b in opp and a not in opp:
                removed_opp.append((r, c))

    if len(removed_own) != 1 or len(added_own) != 1:
        return None

    start, end = removed_own[0], added_own[0]
    before_piece = before[start[0]][start[1]]
    after_piece = after[end[0]][end[1]]
    promoted = before_piece in {1, 2} and after_piece in {3, 4}

    confidence = 0.98 if not removed_opp else 0.94
    if len(removed_opp) > 1:
        confidence = 0.90

    return Move(
        player=player,
        start=start,
        end=end,
        captures=tuple(removed_opp),
        promoted=promoted,
        confidence=confidence,
    )
