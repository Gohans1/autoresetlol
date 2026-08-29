"""Focused tests for LCU queue mode normalization."""
import base64
import io
import sys
import tempfile
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import utils.lcu as lcu_module
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


class ActionClient(LCUClient):
    def __init__(self):
        super().__init__()
        self.last_request = None

    def request(self, method, path, body=None, raise_on_error=False):
        self.last_request = (method, path, body, raise_on_error)
        return None


action_client = ActionClient()
check(
    "T5b: PATCH chuẩn hóa Arena alias 60053 → 53",
    action_client.set_action_champion(7, 60053)
    and action_client.last_request[2] == {"championId": 53},
    str(action_client.last_request),
)
check(
    "T5c: set_action_champion gửi đúng PATCH",
    action_client.last_request
    == (
        "PATCH",
        "/lol-champ-select/v1/session/actions/7",
        {"championId": 53},
        True,
    ),
    "set_action_champion gửi sai method, path, body, hoặc raise_on_error",
)


class SearchClient(LCUClient):
    def request(self, method, path, body=None, raise_on_error=False):
        return {"isActive": path == "/lol-matchmaking/v1/search"}


check("T6: search.isActive được đọc đúng", SearchClient().search_active() is True)


class RosterResultClient(LCUClient):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def request(self, method, path, body=None, raise_on_error=False):
        return self.value


check("T7: roster request lỗi → None", RosterResultClient(None).owned_champions_result() is None)
check("T8: roster response rỗng hợp lệ → []", RosterResultClient([]).owned_champions_result() == [])
check("T7b: owned_champions request lỗi → None", RosterResultClient(None).owned_champions() is None)
check("T8b: owned_champions response rỗng hợp lệ → []", RosterResultClient([]).owned_champions() == [])


class DisconnectedClient(LCUClient):
    def connect(self):
        return False


disconnected = DisconnectedClient()
check(
    "T9: mất kết nối → accept thất bại",
    disconnected.accept_match() is False,
)
check(
    "T9b: mất kết nối → PATCH thất bại",
    disconnected.set_action_champion(7, 53) is False,
)


class FakeResponse:
    def __init__(self, payload=b""):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def ready_client():
    client = LCUClient()
    client._base = "https://127.0.0.1:1234"
    client._auth = "Basic old"
    client._connection_generation = 7
    return client


original_urlopen = lcu_module.urllib.request.urlopen
try:
    lcu_module.urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse()
    empty_body = ready_client()
    check("T10: request 204 rỗng là response hợp lệ", empty_body.request("GET", "/empty") is None)

    def raise_404(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://127.0.0.1:1234/missing",
            404,
            "missing",
            Message(),
            io.BytesIO(),
        )

    lcu_module.urllib.request.urlopen = raise_404
    not_found = ready_client()
    check("T10b: 404 mềm trả None", not_found.request("GET", "/missing") is None)
    strict_404 = ready_client()
    try:
        strict_404.request("GET", "/missing", raise_on_error=True)
    except lcu_module.LCUError:
        strict_404_ok = True
    else:
        strict_404_ok = False
    check("T10c: 404 strict ném LCUError", strict_404_ok)

    def raise_401(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://127.0.0.1:1234/auth",
            401,
            "unauthorized",
            Message(),
            io.BytesIO(),
        )

    lcu_module.urllib.request.urlopen = raise_401
    unauthorized = ready_client()
    unauthorized.request("GET", "/auth")
    check("T10d: 401 invalidate credentials", not unauthorized.connected)

    def raise_transport(*_args, **_kwargs):
        raise OSError("client restarted")

    lcu_module.urllib.request.urlopen = raise_transport
    transport = ready_client()
    transport.request("GET", "/gone")
    check("T10e: transport error invalidate credentials", not transport.connected)

    stale = ready_client()

    def stale_request(*_args, **_kwargs):
        with stale._lock:
            stale._base = "https://127.0.0.1:5678"
            stale._auth = "Basic new"
            stale._connection_generation += 1
        raise OSError("old request failed")

    lcu_module.urllib.request.urlopen = stale_request
    stale.request("GET", "/race")
    check(
        "T10f: stale request không xóa connection mới",
        stale.connected
        and stale._base == "https://127.0.0.1:5678"
        and stale._auth == "Basic new",
    )
finally:
    lcu_module.urllib.request.urlopen = original_urlopen


# T22-T24: kiểm tra cầu nối LCU thật bằng lockfile và HTTP giả lập.
with tempfile.TemporaryDirectory() as temp_dir:
    executable = Path(temp_dir) / "LeagueClient.exe"
    lockfile = executable.parent / "lockfile"
    lockfile.write_text(
        "LeagueClient:1234:12345:lock-secret:https\n", encoding="utf-8"
    )
    process = SimpleNamespace(
        info={"name": "LeagueClient.exe", "exe": str(executable)}
    )
    original_process_iter = lcu_module.psutil.process_iter
    try:
        lcu_module.psutil.process_iter = lambda *args, **kwargs: [process]
        connected_client = LCUClient()
        check(
            "T22: connect đọc đúng lockfile",
            connected_client.connect() is True
            and connected_client.connected is True
            and connected_client._base == "https://127.0.0.1:12345"
            and connected_client._auth
            == "Basic "
            + base64.b64encode(b"riot:lock-secret").decode("ascii"),
            "connect không đọc đúng process, port, protocol, hoặc password",
        )

        invalid_lockfile = LCUClient()
        lockfile.write_text("broken-lockfile\n", encoding="utf-8")
        check(
            "T23: connect từ chối lockfile sai",
            invalid_lockfile.connect() is False
            and invalid_lockfile.connected is False,
            "connect chấp nhận lockfile sai định dạng",
        )
    finally:
        lcu_module.psutil.process_iter = original_process_iter


captured_request = {}
original_urlopen = lcu_module.urllib.request.urlopen


def capture_urlopen(request, **kwargs):
    captured_request["request"] = request
    captured_request["kwargs"] = kwargs
    return FakeResponse()


try:
    lcu_module.urllib.request.urlopen = capture_urlopen
    endpoint_client = ready_client()
    check(
        "T24: accept_match gửi đúng request và nhận 204",
        endpoint_client.accept_match() is True
        and captured_request["request"].get_method() == "POST"
        and captured_request["request"].full_url
        == "https://127.0.0.1:1234/lol-matchmaking/v1/ready-check/accept"
        and captured_request["request"].data is None
        and captured_request["request"].get_header("Authorization")
        == "Basic old",
        "accept_match gửi sai request hoặc không xem response 204 là thành công",
    )
finally:
    lcu_module.urllib.request.urlopen = original_urlopen

if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
