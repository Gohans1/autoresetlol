import threading
import time
import pyautogui
import win32gui
import win32con
import win32com.client
from config import config_manager


class BotState:
    SEARCHING = "SEARCHING"
    STANDBY = "STANDBY"


class AntiFateBot(threading.Thread):
    def __init__(self, update_status_callback, on_stop_callback):
        super().__init__()
        self.update_status_callback = update_status_callback
        self.on_stop_callback = on_stop_callback
        self.running = False
        self.state = BotState.SEARCHING
        self.start_search_time = 0
        self.daemon = True

    def focus_client(self):
        """Attempts to bring the League of Legends client to the foreground using forced methods."""
        try:
            # League client title is usually "League of Legends"
            hwnd = win32gui.FindWindow(None, "League of Legends")
            if hwnd:
                # Check if already foreground to avoid unnecessary flashes
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd == hwnd:
                    return

                print("Focusing League client...")
                try:
                    # Trick to bypass Windows Foreground Lock
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shell.SendKeys("%")  # Sends a harmless ALT key press

                    win32gui.ShowWindow(
                        hwnd, win32con.SW_RESTORE
                    )  # Restore if minimized
                    win32gui.SetForegroundWindow(hwnd)  # Bring to front
                    time.sleep(0.5)  # Wait for render
                except Exception as e:
                    print(f"Force focus failed: {e}")
            else:
                print("League client window not found!")
        except Exception as e:
            print(f"Error focusing client: {e}")

    def is_client_foreground(self):
        """Checks if League of Legends is the current active window."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return "League of Legends" in title
        except Exception:
            return False

    def run(self):
        self.running = True
        self.state = BotState.SEARCHING
        self.start_search_time = time.time()

        # Initial callback
        self.update_status_callback("Bot Started - Searching...", "blue")

        # Load config once
        accept_pos = config_manager.get("accept_match_pixel_pos") or [0, 0]
        accept_color = config_manager.get("accept_match_pixel_color") or [0, 0, 0]

        find_pos = config_manager.get("find_match_button_pos") or [0, 0]
        cancel_pos = config_manager.get("cancel_button_pos") or find_pos

        queue_pos = config_manager.get("in_queue_pixel_pos") or [0, 0]
        queue_color = config_manager.get("in_queue_pixel_color") or [0, 0, 0]

        reset_threshold = int(config_manager.get("reset_time") or 120)

        print(f"Bot started. Threshold: {reset_threshold}s. Mode: Immortal Supervisor")

        while self.running:
            try:
                # --- STATE: SEARCHING ---
                if self.state == BotState.SEARCHING:
                    current_time = time.time()
                    elapsed = int(current_time - self.start_search_time)

                    # 1. Check Accept (Always priority)
                    # ONLY check if League Client is FOREGROUND to avoid false positives (YouTube/FB)
                    if self.is_client_foreground():
                        if pyautogui.pixelMatchesColor(
                            accept_pos[0],
                            accept_pos[1],
                            (accept_color[0], accept_color[1], accept_color[2]),
                            tolerance=10,
                        ):
                            # DEBOUNCE CHECK: Verify if it's a real button or just a UI flash
                            print("Possible match detected. Verifying...")
                            time.sleep(0.5)

                            if pyautogui.pixelMatchesColor(
                                accept_pos[0],
                                accept_pos[1],
                                (accept_color[0], accept_color[1], accept_color[2]),
                                tolerance=10,
                            ):
                                self.update_status_callback(
                                    "MATCH FOUND! Accepting...", "green"
                                )
                                print("Match found! Clicking Accept...")
                                pyautogui.click(accept_pos[0], accept_pos[1])

                                # Move to STANDBY state
                                self.state = BotState.STANDBY
                                self.update_status_callback(
                                    "Accepted. Monitoring...", "purple"
                                )
                                time.sleep(1)  # Wait for click registration
                                continue
                            else:
                                print("False positive ignored (UI Flash).")

                    # 2. Check Queue & Handle Reset Logic
                    self.update_status_callback(
                        f"Searching... ({elapsed}/{reset_threshold}s)", "orange"
                    )

                    # Check if threshold reached
                    if elapsed >= reset_threshold:
                        print("Threshold reached. Checking window focus...")
                        # Force focus to check reality
                        self.focus_client()

                        # Re-check queue pixel after focus
                        if pyautogui.pixelMatchesColor(
                            queue_pos[0],
                            queue_pos[1],
                            (queue_color[0], queue_color[1], queue_color[2]),
                            tolerance=10,
                        ):
                            self.update_status_callback("Resetting Queue...", "red")
                            print("Resetting queue...")

                            # Perform Reset
                            pyautogui.click(cancel_pos[0], cancel_pos[1])
                            time.sleep(2)
                            pyautogui.click(find_pos[0], find_pos[1])

                            # Reset Timer
                            self.start_search_time = time.time()
                            self.update_status_callback(
                                "Queue Reset. Restarting...", "blue"
                            )
                        else:
                            print("Queue pixel not found after focus. Resetting timer.")
                            self.start_search_time = time.time()

                # --- STATE: STANDBY (Supervisor) ---
                elif self.state == BotState.STANDBY:
                    # Check for Queue pixel (Dodge detection)
                    # Optimistic check first (without focus) to save resources
                    if pyautogui.pixelMatchesColor(
                        queue_pos[0],
                        queue_pos[1],
                        (queue_color[0], queue_color[1], queue_color[2]),
                        tolerance=10,
                    ):
                        print("Potential Dodge detected. Verifying...")

                        # SAFETY FIRST: Focus client before clicking anything!
                        self.focus_client()
                        time.sleep(0.5)  # Wait for window to settle

                        # Verify again after focus
                        if pyautogui.pixelMatchesColor(
                            queue_pos[0],
                            queue_pos[1],
                            (queue_color[0], queue_color[1], queue_color[2]),
                            tolerance=10,
                        ):
                            print("Dodge CONFIRMED. Performing Hard Reset...")
                            self.update_status_callback(
                                "Dodge detected! Resetting...", "red"
                            )

                            # Hard Reset Sequence
                            pyautogui.click(cancel_pos[0], cancel_pos[1])
                            time.sleep(2)
                            pyautogui.click(find_pos[0], find_pos[1])

                            self.state = BotState.SEARCHING
                            self.start_search_time = time.time()
                            self.update_status_callback(
                                "Queue Reset. Searching...", "blue"
                            )
                        else:
                            print("False alarm (Background pixel match).")
                            self.update_status_callback(
                                "Standby (In Game/Lobby)...", "gray"
                            )
                    else:
                        self.update_status_callback(
                            "Standby (In Game/Lobby)...", "gray"
                        )

                time.sleep(1)

            except Exception as e:
                print(f"Bot Error: {e}")
                self.update_status_callback(f"Error: {str(e)[:20]}", "red")
                # Don't stop on minor errors, just sleep and retry
                time.sleep(2)

    def stop(self, found=False):
        self.running = False
        if self.on_stop_callback:
            status = "Stopped"
            color = "red"
            self.on_stop_callback(status, color)
