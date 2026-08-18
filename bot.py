"""Bot LCU — chấp nhận trận + phát hiện dodge qua API local của client LoL.

Thay thế hoàn toàn bot pixel cũ (v2.0): không click chuột, không nhìn màn
hình, không reset queue, không đếm giờ. Mọi trạng thái đọc từ LCU:

  - Chờ ready-check "InProgress" → POST accept
  - Xác nhận vào champ select qua gameflow-phase
  - Dodge/decline = phase ChampSelect → Matchmaking (client TỰ quay lại
    hàng chờ — Riot xác nhận — bot không bao giờ click Find Match)

Giữ nguyên contract callback với GUI: update_status_callback,
on_stop_callback, on_success_callback (reset_dimmer),
on_champ_select_callback (switch_to_gaming_mode).
"""

import threading
import time
from typing import Callable, Optional

from config import config_manager
from constants import AppConfig, UIStatus
from logger import logger
from utils.lcu import lcu

# Sau accept, client mất vài giây để nhảy sang ChampSelect — trong khoảng
# này phase vẫn "Matchmaking"/"Lobby" là BÌNH THƯỜNG. Chỉ coi là dodge
# khi phase quay lại queue sau khoảng grace này.
VERIFY_GRACE = 5


class AntiFateBot(threading.Thread):
    """Vòng đời 1 phiên tìm trận: chờ trận → accept → xác nhận champ select."""

    def __init__(
        self,
        update_status_callback: Callable[[str, str], None],
        on_stop_callback: Optional[Callable[[str, str], None]],
        on_success_callback: Optional[Callable[[], None]] = None,
        on_champ_select_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__(daemon=True)
        self.update_status_callback = update_status_callback
        self.on_stop_callback = on_stop_callback
        self.on_success_callback = on_success_callback
        self.on_champ_select_callback = on_champ_select_callback
        self.running: bool = False
        self._accepting: bool = False
        self._champ_select_notified: bool = False
        self.verify_start_time: float = 0.0
        self._error_until: float = 0.0  # giữ status lỗi vài giây, không ghi đè
        self._stop_status: Optional[tuple[str, str]] = None
        self._stop_callback_sent = False

    # ---- vòng lặp ----

    def run(self) -> None:
        self.running = True
        self._stop_status = None
        self._stop_callback_sent = False
        self.update_status_callback(UIStatus.STARTING, "orange")
        logger.info("Bot LCU started (auto-accept + dodge detect)")

        try:
            while self.running:
                try:
                    self._tick()
                except Exception as e:
                    logger.error(f"Bot Loop Error: {e}")
                    self.update_status_callback(
                        "Đã xảy ra lỗi. Hãy thử lại.", "red"
                    )
                    time.sleep(2)
                time.sleep(1)
        finally:
            self.running = False
            status, color = self._stop_status or (UIStatus.STOPPED, "gray")
            self._notify_stop(status, color)

    def _tick(self) -> None:
        phase = lcu.gameflow_phase()
        if phase is None:
            self.update_status_callback("Chưa kết nối được với League of Legends", "red")
            return

        if phase == "ChampSelect":
            # Báo UI một lần, nhưng giữ worker sống để bắt dodge sau ChampSelect.
            self._accepting = False
            if not self._champ_select_notified:
                logger.info("Champ select confirmed via LCU — auto-accept remains active.")
                self._champ_select_notified = True
                self.update_status_callback(UIStatus.CHAMP_SELECT, "green")
                if self.on_success_callback:
                    self.on_success_callback()
                if self.on_champ_select_callback:
                    self.on_champ_select_callback()
            return

        if phase == "InProgress":
            # Giữ auto-accept sống; trận sau có thể xuất hiện sau khi kết thúc
            # game hoặc sau một dodge trong ChampSelect.
            self._leave_champ_select_if_needed(phase)
            self.update_status_callback(UIStatus.IN_GAME, "green")
            return

        self._leave_champ_select_if_needed(phase)
        if self._accepting:
            self._handle_verifying(phase)
        else:
            self._handle_searching(phase)

    def _leave_champ_select_if_needed(self, phase: str) -> None:
        if self._champ_select_notified:
            logger.info(f"Champ Select ended → phase {phase}; auto-accept remains active.")
            self._champ_select_notified = False

    def _handle_searching(self, phase: Optional[str]) -> None:
        if time.time() < self._error_until:
            return  # giữ status lỗi vài giây, không ghi đè

        search_active = lcu.search_active()
        if search_active is True:
            status_text = UIStatus.SEARCHING
            status_color = "blue"
        elif search_active is False and phase == "Lobby":
            status_text = UIStatus.READY
            status_color = "gray"
        elif search_active is False:
            status_text = UIStatus.QUEUEING
            status_color = "orange"
        else:
            status_text = "Đang kiểm tra hàng chờ"
            status_color = "orange"
        self.update_status_callback(status_text, status_color)

        if not config_manager.get("auto_accept_enabled"):
            return

        rc = lcu.ready_check()
        if not rc or rc.get("state") != "InProgress":
            return  # chưa có trận

        logger.info("MATCH FOUND! Accepting via LCU...")
        self.update_status_callback(UIStatus.MATCH_FOUND, "green")
        if not lcu.accept_match():
            logger.error("Accept failed via LCU")
            self.update_status_callback("Không thể xác nhận trận — đang thử lại", "red")
            self._error_until = time.time() + 3
            return

        self._accepting = True
        self.verify_start_time = time.time()
        self.update_status_callback(UIStatus.ACCEPTED, "purple")

    def _handle_verifying(self, phase: Optional[str]) -> None:
        elapsed = time.time() - self.verify_start_time
        remaining = int(max(0, AppConfig.VERIFY_TIMEOUT - elapsed))
        self.update_status_callback(UIStatus.VERIFYING.format(remaining), "purple")

        # Dodge / decline: phase quay lại queue sau grace period.
        if phase in ("Matchmaking", "Lobby") and elapsed >= VERIFY_GRACE:
            logger.info("Dodge/decline detected (ChampSelect -> queue). Client requeues itself.")
            self.update_status_callback(UIStatus.DODGED, "orange")
            self._accepting = False
            return

        # Hết thời gian xác nhận — dừng an toàn, KHÔNG bao giờ click gì.
        if elapsed > AppConfig.VERIFY_TIMEOUT:
            logger.warning("Verify timed out without champ select — stopping (no clicks).")
            self._finish_stop("Verify Timeout", "orange")

    # ---- kết thúc ----

    def _notify_stop(self, status: str, color: str) -> None:
        """Notify the GUI once, after the worker loop has fully exited."""
        if self._stop_callback_sent:
            return
        self._stop_callback_sent = True
        if self.on_stop_callback:
            self.on_stop_callback(status, color)

    def _finish_stop(self, status: str, color: str) -> None:
        self._stop_status = (status, color)
        self.running = False

    def stop(self) -> None:
        self._stop_status = (UIStatus.STOPPED, "gray")
        self.running = False
        # The worker owns the final callback. This prevents a stale tick from
        # updating the UI after STOP and keeps START locked until exit.
        if self.is_alive():
            self.join(timeout=1)
        if not self.is_alive():
            status, color = self._stop_status or (UIStatus.STOPPED, "gray")
            self._notify_stop(status, color)
