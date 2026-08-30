"""Pure validation rules for Arena champion automation."""
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple


PICK_FIELDS = ("main", "b1", "b2", "b3")
OPTIONAL_PICK_FIELDS = ("b1", "b2", "b3")
NO_PICK_LABEL = "Không"
NOT_SET_LABEL = "Chưa chọn"

# LCU inventory exposes some Arena/Jade aliases in the 60000 namespace,
# while Champ Select actions use the base champion ID. Example: 60053 and 53
# both identify Blitzcrank. Keep one canonical ID inside the application.
_CHAMPION_ALIAS_OFFSET = 60000
_CHAMPION_ALIAS_LIMIT = 70000


@dataclass(frozen=True)
class ArenaConfigIssue:
    """One actionable configuration problem."""

    code: str
    fields: Tuple[str, ...]
    message: str


def champion_id(value: object) -> int:
    """Return the canonical positive Champ Select champion ID."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, str):
        value = value.strip()
        if not value.isdecimal():
            return 0
        try:
            value = int(value)
        except (ValueError, OverflowError):
            return 0
    if not isinstance(value, int) or value <= 0:
        return 0
    if _CHAMPION_ALIAS_OFFSET <= value < _CHAMPION_ALIAS_LIMIT:
        value -= _CHAMPION_ALIAS_OFFSET
    return value if value > 0 else 0


def normalize_pick_chain(chain: object) -> Tuple[int, int, int, int]:
    """Return exactly four safe champion ids from a stored pick chain."""
    if not isinstance(chain, (list, tuple)):
        return (0, 0, 0, 0)
    values = [champion_id(value) for value in chain[:4]]
    values.extend([0] * (4 - len(values)))
    return (values[0], values[1], values[2], values[3])


def validate_arena_config(
    *,
    auto_ban_enabled: bool,
    auto_pick_enabled: bool,
    ban_champion_id: object,
    pick_chain: object,
    owned_ids: Optional[Iterable[int]] = None,
) -> list[ArenaConfigIssue]:
    """Validate active Arena settings.

    ``owned_ids=None`` means the client roster is not verified yet. In that
    state, saved ids remain usable but are reported by the UI as unverified.
    """
    ban_id = champion_id(ban_champion_id)
    chain = normalize_pick_chain(pick_chain)
    issues: list[ArenaConfigIssue] = []

    if auto_ban_enabled and ban_id == 0:
        issues.append(
            ArenaConfigIssue(
                "missing_ban",
                ("ban",),
                "Auto ban đang bật nhưng chưa chọn tướng cần ban.",
            )
        )

    if auto_pick_enabled and chain[0] == 0:
        issues.append(
            ArenaConfigIssue(
                "missing_main",
                ("main",),
                "Auto pick đang bật nhưng chưa chọn Tướng chính.",
            )
        )

    if auto_pick_enabled:
        positions: dict[int, list[str]] = {}
        for field, cid in zip(PICK_FIELDS, chain):
            if cid > 0:
                positions.setdefault(cid, []).append(field)
        for fields in positions.values():
            if len(fields) > 1:
                issues.append(
                    ArenaConfigIssue(
                        "duplicate_pick",
                        tuple(fields),
                        "Chuỗi pick đang bị trùng tướng.",
                    )
                )

    if auto_ban_enabled and auto_pick_enabled and ban_id > 0:
        conflicting = tuple(
            field for field, cid in zip(PICK_FIELDS, chain) if cid == ban_id
        )
        if conflicting:
            issues.append(
                ArenaConfigIssue(
                    "ban_pick_conflict",
                    ("ban",) + conflicting,
                    "Tướng cần ban đang trùng với tướng chọn.",
                )
            )

    if owned_ids is not None:
        owned = {champion_id(value) for value in owned_ids}
        if auto_ban_enabled and ban_id > 0 and ban_id not in owned:
            issues.append(
                ArenaConfigIssue(
                    "ban_not_owned",
                    ("ban",),
                    "Tướng cần ban không còn trong danh sách client.",
                )
            )
        if auto_pick_enabled:
            for field, cid in zip(PICK_FIELDS, chain):
                if cid > 0 and cid not in owned:
                    issues.append(
                        ArenaConfigIssue(
                            "pick_not_owned",
                            (field,),
                            "Tướng đã lưu không còn trong danh sách client.",
                        )
                    )

    return issues
