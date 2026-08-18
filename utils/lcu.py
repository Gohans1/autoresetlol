"""LCU client — giao tiếp với client LoL qua API nội bộ (localhost).

Mọi request chỉ chạy trên máy local, KHÔNG bao giờ lên server Riot.
Thông tin kết nối đọc từ file `lockfile` nằm cạnh LeagueClient.exe
(định dạng: name:pid:port:password:protocol). Auth basic user "riot".

Chỉ dùng stdlib (urllib) + psutil (đã có sẵn trong project) — không thêm
dependency mới.
"""

import base64
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import psutil

from logger import logger

# Cert tự ký của LCU — cố ý bỏ qua xác thực (chỉ localhost, không có
# thông tin nhạy cảm đi qua mạng).
_CTX = ssl._create_unverified_context()


def _basic_auth(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def normalize_game_mode(session: object) -> Optional[str]:
    """Normalize LCU queue metadata to stable app modes.

    Arena currently reports ``CHERRY`` in ``gameMode`` and ``type`` while
    queue names identify it as Arena. The app uses ``ARENA`` internally.
    """
    if not isinstance(session, dict):
        return None
    game_data = session.get("gameData")
    queue = game_data.get("queue") if isinstance(game_data, dict) else None
    if not isinstance(queue, dict):
        return None

    raw_mode = str(queue.get("gameMode") or "").upper()
    queue_type = str(queue.get("type") or "").upper()
    queue_text = " ".join(
        str(queue.get(key) or "").upper()
        for key in ("name", "shortName", "description", "detailedDescription")
    )
    if raw_mode == "CHERRY" or queue_type == "CHERRY" or "ARENA" in queue_text:
        return "ARENA"
    return raw_mode or None


class LCUError(Exception):
    """Lỗi LCU nghiêm trọng (HTTP != 404 hoặc mất kết nối)."""


class LCUClient:
    """HTTP client mỏng cho LCU. Tự reconnect khi client LoL đổi port."""

    def __init__(self) -> None:
        self._base: Optional[str] = None
        self._auth: Optional[str] = None
        self._lockfile_mtime: Optional[float] = None
        self._last_err_log: float = 0.0
        # Lock: connect()/request() chạy từ nhiều thread (watcher + GUI fetch)
        self._lock = threading.Lock()
        # Backoff: client tắt → không quét process list mỗi giây (tốn CPU)
        self._next_connect_at: float = 0.0

    # ---- Kết nối ----

    def connect(self) -> bool:
        """Tìm lockfile của client đang chạy. True khi sẵn sàng.

        Có cache theo mtime của lockfile: khi client chưa đổi port thì
        không phải quét lại process list mỗi lần. Khi thất bại → backoff
        5s trước khi quét lại.
        """
        if time.time() < self._next_connect_at:
            return self._base is not None
        try:
            for proc in psutil.process_iter(["name", "exe"]):
                try:
                    if proc.info["name"] != "LeagueClient.exe":
                        continue
                    exe = proc.info["exe"]
                    if not exe:
                        continue
                    lock_path = os.path.join(os.path.dirname(exe), "lockfile")
                    if not os.path.exists(lock_path):
                        continue  # client chưa khởi động xong — quét tiếp
                    mtime = os.path.getmtime(lock_path)
                    with self._lock:
                        if self._base and mtime == self._lockfile_mtime:
                            return True
                        with open(lock_path, "r", encoding="utf-8") as f:
                            parts = f.read().strip().split(":")
                        if len(parts) < 5:
                            continue
                        _, _, port, password, protocol = parts[:5]
                        if protocol not in ("https", "http"):
                            continue
                        self._base = f"{protocol}://127.0.0.1:{port}"
                        self._auth = _basic_auth("riot", password)
                        self._lockfile_mtime = mtime
                    logger.info(f"LCU connected: {self._base}")
                    return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    continue
        except Exception as e:
            logger.error(f"LCU connect failed: {e}")
        with self._lock:
            self._base = None
            self._auth = None
        self._next_connect_at = time.time() + 5
        return False

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._base is not None

    # ---- HTTP ----

    def request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        raise_on_error: bool = False,
    ) -> Optional[Any]:
        """Gọi LCU.

        Trả None khi thất bại (kể cả 404 — endpoint chưa tồn tại).
        raise_on_error=True: ném LCUError thay vì trả None (cho các chỗ
        cần phân biệt \"thành công nhưng body rỗng\" với \"thất bại\").
        """
        with self._lock:
            base, auth = self._base, self._auth
        if not base or not auth:
            if not self.connect():
                return None
            with self._lock:
                base, auth = self._base, self._auth
            if not base or not auth:
                return None
        url = base + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", auth)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, context=_CTX, timeout=3) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Auth hết hạn / lockfile cũ (client restart cùng port, mtime
                # trùng) → reset kết nối, lần sau tự tìm lockfile + auth mới.
                with self._lock:
                    self._base = None
                    self._auth = None
                self._next_connect_at = time.time() + 5
                logger.warning(
                    f"LCU {method} {path} -> HTTP 401 (auth stale) - "
                    "reconnecting..."
                )
            if e.code == 404 and not raise_on_error:
                return None  # ví dụ: chưa có session champ select
            if raise_on_error:
                raise LCUError(f"LCU {method} {path} -> HTTP {e.code}") from e
            logger.error(f"LCU {method} {path} -> HTTP {e.code}")
            return None
        except Exception as e:
            # Client tắt / khởi động lại → mất kết nối, lần sau tự tìm lại.
            with self._lock:
                self._base = None
                self._auth = None
            self._next_connect_at = time.time() + 5
            if raise_on_error:
                raise LCUError(f"LCU {method} {path} failed: {e}") from e
            self._log_rate_limited(f"LCU {method} {path} failed: {e}")
            return None

    def _log_rate_limited(self, msg: str) -> None:
        """Log lỗi kết nối tối đa 1 lần / 30s — tránh spam khi client tắt."""
        now = time.time()
        if now - self._last_err_log > 30:
            logger.warning(msg)
            self._last_err_log = now

    # ---- API cao cấp ----

    def gameflow_phase(self) -> Optional[str]:
        """Trạng thái client: Lobby / Matchmaking / ChampSelect / InProgress..."""
        v = self.request("GET", "/lol-gameflow/v1/gameflow-phase")
        return v if isinstance(v, str) else None

    def search_active(self) -> Optional[bool]:
        """Return whether the client is actively searching for a match."""
        value = self.request("GET", "/lol-matchmaking/v1/search")
        if not isinstance(value, dict) or not isinstance(value.get("isActive"), bool):
            return None
        return value["isActive"]

    def ready_check(self) -> Optional[Dict[str, Any]]:
        """Trạng thái ready check hiện tại: {"state": "InProgress"|...}."""
        v = self.request("GET", "/lol-matchmaking/v1/ready-check")
        return v if isinstance(v, dict) else None

    def accept_match(self) -> bool:
        """Đồng ý trận đã tìm thấy (ready check).

        Trả True khi server nhận request (kể cả response rỗng 204).
        """
        try:
            self.request(
                "POST",
                "/lol-matchmaking/v1/ready-check/accept",
                raise_on_error=True,
            )
            return True
        except LCUError:
            return False

    def game_mode(self) -> Optional[str]:
        """Game mode của session hiện tại (ARENA / CLASSIC / ...)."""
        s = self.request("GET", "/lol-gameflow/v1/session")
        return normalize_game_mode(s)

    def champ_select_session(self) -> Optional[Dict[str, Any]]:
        """Session champ select hiện tại, None khi không có (404)."""
        v = self.request("GET", "/lol-champ-select/v1/session")
        return v if isinstance(v, dict) else None

    def set_action_champion(self, action_id: int, champion_id: int) -> bool:
        """Hover champion vào action ban/pick.

        KHÔNG gọi .../complete — bot không bao giờ khóa, user còn đổi được.
        Dùng raise_on_error: PATCH thành công có thể trả 204/body rỗng —
        coi mọi response hợp lệ (kể cả không có body) là THÀNH CÔNG.
        """
        try:
            self.request(
                "PATCH",
                f"/lol-champ-select/v1/session/actions/{action_id}",
                {"championId": champion_id},
                raise_on_error=True,
            )
            return True
        except LCUError:
            return False

    def owned_champions(self) -> List[Dict[str, Any]]:
        """Danh sách tướng đã sở hữu: [{id, name, alias}]. Rỗng nếu lỗi."""
        v = self.request("GET", "/lol-champions/v1/owned-champions-minimal")
        if not isinstance(v, list):
            return []
        out: List[Dict[str, Any]] = []
        for c in v:
            if not isinstance(c, dict):
                continue
            cid = c.get("id")
            name = c.get("name")
            if isinstance(cid, int) and isinstance(name, str) and name:
                out.append({"id": cid, "name": name, "alias": str(c.get("alias") or "")})
        return out


# Singleton dùng chung cho toàn app
lcu = LCUClient()
