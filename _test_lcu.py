"""Focused tests for LCU queue mode normalization."""
import sys

from utils.lcu import LCUClient, normalize_game_mode


FAILURES = []


def check(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


arena_cherry = {
    "gameData": {
        "queue": {
            "gameMode": "CHERRY",
            "type": "CHERRY",
            "name": "Arena 3x6",
        }
    }
}
check("T1: CHERRY queue → ARENA", normalize_game_mode(arena_cherry) == "ARENA")

arena_name = {
    "gameData": {
        "queue": {
            "gameMode": "UNKNOWN",
            "type": "PVP",
            "name": "Arena 3x6",
        }
    }
}
check("T2: Arena queue name → ARENA", normalize_game_mode(arena_name) == "ARENA")

classic = {"gameData": {"queue": {"gameMode": "CLASSIC", "type": "PVP"}}}
check("T3: Classic queue remains CLASSIC", normalize_game_mode(classic) == "CLASSIC")
check("T4: malformed session → None", normalize_game_mode({}) is None)


class FakeClient(LCUClient):
    def request(self, method, path, body=None, raise_on_error=False):
        return arena_cherry


check("T5: LCUClient.game_mode() normalizes CHERRY", FakeClient().game_mode() == "ARENA")


class SearchClient(LCUClient):
    def request(self, method, path, body=None, raise_on_error=False):
        return {"isActive": path == "/lol-matchmaking/v1/search"}


check("T6: search.isActive được đọc đúng", SearchClient().search_active() is True)

if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
