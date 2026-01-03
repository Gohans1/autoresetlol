import threading
import time
import winsound
import pyautogui
from playsound import playsound
from enum import Enum, auto
from typing import Callable, Optional, Tuple

from config import config_manager
from constants import GameInfo, UIStatus, Colors, AppConfig
from logger import logger
from utils.windows import (
    find_window_by_title,
    force_focus_window,
    get_foreground_window_title,
)


class BotState(Enum):
    SEARCHING = auto()
    VERIFYING = auto()
    STANDBY = auto()


class AntiFateBot(threading.Thread):
    def __init__(
        self,
        update_status_callback: Callable[[str, str], None],
        on_stop_callback: Optional[Callable[[str, str], None]],
        on_success_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.update_status_callback = update_status_callback
        self.on_stop_callback = on_stop_callback
        self.on_success_callback = on_success_callback
        self.running: bool = False
        self.state: BotState = BotState.SEARCHING
        self.start_search_time: float = 0
        self.sound_played: bool = False
        self.daemon = True

    def focus_client(self) -> None:
        """Attempts to bring the League of Legends client to the foreground."""
        hwnd = find_window_by_title(GameInfo.CLIENT_TITLE)
        if hwnd:
            force_focus_window(hwnd)
        else:
            logger.warning("League client window not found!")

    def is_game_running(self) -> bool:
        """Checks if the actual LoL Game (not Client) is the foreground window."""
        title = get_foreground_window_title()
        return GameInfo.GAME_TITLE in title

    def check_pixel(
        self, pos: list[int], color: list[int], tolerance: int = 10
    ) -> bool:
        """Safe wrapper for pixel matching."""
        try:
            return pyautogui.pixelMatchesColor(
                pos[0], pos[1], (color[0], color[1], color[2]), tolerance=tolerance
            )
        except Exception as e:
            logger.error(f"Pixel check failed at {pos}: {e}")
            return False

    def run(self) -> None:
        self.running = True
        self.state = BotState.SEARCHING
        self.start_search_time = time.time()

        logger.info(f"Bot started. Threshold: {config_manager.get('reset_time')}s")
        self.update_status_callback(UIStatus.RUNNING, "blue")

        while self.running:
            try:
                if self.state == BotState.SEARCHING:
                    self._handle_searching()
                elif self.state == BotState.VERIFYING:
                    self._handle_verifying()
                elif self.state == BotState.STANDBY:
                    self._handle_standby()

                time.sleep(1)

            except Exception as e:
                logger.error(f"Bot Loop Error: {e}")
                self.update_status_callback(f"Error: {str(e)[:20]}", "red")
                time.sleep(2)

    def _handle_searching(self) -> None:
        current_time = time.time()
        elapsed_float = current_time - self.start_search_time
        elapsed = int(elapsed_float)
        reset_threshold = int(config_manager.get("reset_time") or 120)

        # 0. Global Champ Select Check (Handles manual accept or late start)
        champ_pos = config_manager.get("champ_select_pixel_pos")
        champ_color = config_manager.get("champ_select_pixel_color")
        if champ_pos and champ_pos != [0, 0]:
            if self.check_pixel(champ_pos, champ_color):
                logger.info("CHAMP SELECT DETECTED (Manual/Late)! Entering Standby.")
                self.state = BotState.STANDBY
                if self.on_success_callback:
                    self.on_success_callback()
                self.update_status_callback(UIStatus.CHAMP_SELECT, "green")
                # Removed sleep, UI should handle state-based colors
                return

        # Sound Notification (1.5s before reset)
        if config_manager.get("reset_sound_enabled") and not self.sound_played:
            if elapsed_float >= (reset_threshold - 1.5):
                logger.info("Playing pre-reset sound alert...")
                self.sound_played = True

                def _play():
                    try:
                        playsound(AppConfig.NOTIFY_SOUND)
                    except Exception as e:
                        logger.error(f"Failed to play sound: {e}")
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)

                threading.Thread(target=_play, daemon=True).start()

        # 1. Check Accept (Global check)
        accept_pos = config_manager.get("accept_match_pixel_pos")
        accept_color = config_manager.get("accept_match_pixel_color")

        if self.check_pixel(accept_pos, accept_color):
            logger.info("MATCH FOUND! Accepting...")
            self.update_status_callback(UIStatus.MATCH_FOUND, "green")

            pyautogui.click(accept_pos[0], accept_pos[1])

            # Transition to VERIFYING instead of STANDBY
            self.state = BotState.VERIFYING
            self.verify_start_time = time.time()
            self.update_status_callback("Verifying Accept...", "purple")
            time.sleep(0.5)
            return

        # 2. Check Timer & Reset
        self.update_status_callback(
            UIStatus.SEARCHING.format(elapsed, reset_threshold), "blue"
        )

        if elapsed >= reset_threshold:
            logger.info("Threshold reached. Context checking...")

            if self.is_game_running():
                logger.info("User IN GAME. Skipping focus.")
                self.start_search_time = time.time()
                self.sound_played = False
                time.sleep(1)
                return

            # Focus Client
            self.focus_client()

            # Verify Queue State
            queue_pos = config_manager.get("in_queue_pixel_pos")
            queue_color = config_manager.get("in_queue_pixel_color")

            if self.check_pixel(queue_pos, queue_color):
                self._perform_reset()
            else:
                logger.info("Queue pixel not found. Resetting timer.")
                self.start_search_time = time.time()
                self.sound_played = False

    def _handle_verifying(self) -> None:
        """
        New state to handle the 'Accept Clicked' limbo.
        We wait here until we confirm we are in Champ Select.
        If we see the queue again, we go back to SEARCHING.
        """
        elapsed = time.time() - self.verify_start_time
        timeout = AppConfig.VERIFY_TIMEOUT
        remaining = int(max(0, timeout - elapsed))

        # Update UI with countdown
        self.update_status_callback(UIStatus.VERIFYING.format(remaining), "purple")

        # 1. Check if we are in Champ Select (Success Condition)
        champ_pos = config_manager.get("champ_select_pixel_pos")
        champ_color = config_manager.get("champ_select_pixel_color")

        # Only check if config is set (not [0,0])
        if champ_pos and champ_pos != [0, 0]:
            if self.check_pixel(champ_pos, champ_color):
                logger.info("CHAMP SELECT CONFIRMED! Entering Standby.")
                self.state = BotState.STANDBY
                if self.on_success_callback:
                    self.on_success_callback()
                self.update_status_callback(UIStatus.CHAMP_SELECT, "green")
                return

        # 2. Check if we are back in Queue (Failure Condition - Dodge/Decline)
        queue_pos = config_manager.get("in_queue_pixel_pos")
        queue_color = config_manager.get("in_queue_pixel_color")

        if self.check_pixel(queue_pos, queue_color):
            logger.info(
                "Back in queue detected (Decline/Dodge). Hard Resetting immediately."
            )
            self._perform_reset()
            self.state = BotState.SEARCHING
            return

        # 3. Check Accept button again (Retry Condition)
        accept_pos = config_manager.get("accept_match_pixel_pos")
        accept_color = config_manager.get("accept_match_pixel_color")

        if self.check_pixel(accept_pos, accept_color):
            logger.info("Accept button reappeared. Clicking again...")
            pyautogui.click(accept_pos[0], accept_pos[1])
            time.sleep(0.5)
            return

        # 4. Timeout
        if elapsed > timeout:
            logger.warning(
                "Verification timed out. Assuming logic failure or lag. Hard Resetting."
            )
            # Force focus client to foreground because if match was declined,
            # the client might still be in background (user alt-tabbed).
            self.focus_client()
            time.sleep(0.5)

            self._perform_reset()
            self.state = BotState.SEARCHING
            self.update_status_callback("Verify Timeout", "orange")
            time.sleep(1)

    def _perform_reset(self) -> None:
        logger.info("Resetting queue...")
        self.sound_played = False
        self.update_status_callback(UIStatus.RESETTING, "red")

        find_pos = config_manager.get("find_match_button_pos")
        cancel_pos = config_manager.get("cancel_button_pos")
        minimize_pos = config_manager.get("minimize_btn_pos")

        # Cancel
        pyautogui.click(cancel_pos[0], cancel_pos[1])
        time.sleep(1.0)  # Shortened wait

        # Find Match
        pyautogui.click(find_pos[0], find_pos[1])

        # Auto Minimize (New Feature)
        if minimize_pos and minimize_pos != [0, 0]:
            time.sleep(0.2)
            logger.info(f"Minimizing client at {minimize_pos}")
            pyautogui.click(minimize_pos[0], minimize_pos[1])

        self.start_search_time = time.time()
        self.sound_played = False
        self.update_status_callback(UIStatus.RESTARTING, "blue")

    def _handle_standby(self) -> None:
        queue_pos = config_manager.get("in_queue_pixel_pos")
        queue_color = config_manager.get("in_queue_pixel_color")

        # Optimistic check
        if self.check_pixel(queue_pos, queue_color):
            if self.is_game_running():
                logger.info("In Game during standby. Ignoring.")
                time.sleep(5)
                return

            # Verification Focus
            logger.info("Potential Dodge. Verifying...")
            self.focus_client()
            time.sleep(0.5)

            if self.check_pixel(queue_pos, queue_color):
                logger.info("Dodge CONFIRMED. Hard Reset.")
                self.update_status_callback(UIStatus.DODGE_DETECTED, "red")
                self._perform_reset()
                self.state = BotState.SEARCHING
            else:
                logger.info("False alarm.")
                self.update_status_callback(UIStatus.STANDBY, "green")
        else:
            self.update_status_callback(UIStatus.STANDBY, "green")

    def stop(self, found: bool = False) -> None:
        self.running = False
        if self.on_stop_callback:
            self.on_stop_callback(UIStatus.STOPPED, "gray")
