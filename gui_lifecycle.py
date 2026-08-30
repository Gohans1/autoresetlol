"""Application lifecycle and bot controls UI mixin."""

from __future__ import annotations

import os
import subprocess
import sys
from tkinter import messagebox

from bot import AntiFateBot
from config import config_manager, normalize_dimmer_mode, normalize_dimmer_value
from constants import (
    AppConfig,
    Colors,
    DISCORD_NOTIFICATION_SPECS,
    NotificationSpec,
    UIStatus,
)
from logger import logger
from utils.windows import (
    get_autostart_snapshot,
    get_autostart_state,
    restore_autostart_snapshot,
    set_autostart,
)


class LifecycleUiMixin:
    def _cleanup_partial_initialization(self) -> None:
        """Stop resources that the constructor creates before a later step fails."""
        self._ui_callbacks_enabled = False
        self._safe_cleanup_call(
            "partial initialization runtime stop",
            lambda: self._stop_runtime_components(close_dimmer=False),
        )
        dimmer = self.__dict__.get("dimmer")
        if dimmer is not None:
            self._safe_cleanup_call(
                "partial initialization dimmer close", lambda: dimmer.close()
            )

    def _safe_cleanup_call(self, label: str, callback) -> None:
        try:
            callback()
        except Exception as error:
            logger.error(f"Cleanup step failed ({label}): {error}")

    def _stop_runtime_components(self, close_dimmer: bool = True) -> None:
        """Stop workers and block callbacks before the window exits or restarts."""
        self._ui_callbacks_enabled = False
        self._bot_stopping = True
        self._bot_generation = self.__dict__.get("_bot_generation", 0) + 1
        self._arena_automation_enabled = False
        roster_reload_id = self.__dict__.get("_arena_roster_reload_after_id")
        if roster_reload_id is not None:
            self._safe_cleanup_call(
                "cancel Arena roster reload",
                lambda timer_id=roster_reload_id: self.after_cancel(timer_id),
            )
            self._arena_roster_reload_after_id = None
        self._safe_cleanup_call(
            "Arena roster fetch stop", self._stop_arena_roster_fetch
        )
        watcher = self.__dict__.get("arena_watcher")
        if watcher is not None:
            self._safe_cleanup_call(
                "disable Arena automation",
                lambda: self._set_arena_automation_enabled(False),
            )

        bot = self.__dict__.get("bot")
        if bot is not None:
            def disable_bot_callbacks() -> None:
                for callback_name in (
                    "on_stop_callback",
                    "on_success_callback",
                    "on_champ_select_callback",
                ):
                    setattr(bot, callback_name, None)

            self._safe_cleanup_call("disable bot callbacks", disable_bot_callbacks)
            self._safe_cleanup_call("bot stop", lambda: bot.stop())

        if watcher is not None:
            self._safe_cleanup_call("Arena watcher stop", lambda: watcher.stop())

        notifier = self.__dict__.get("notifier")
        if notifier is not None:
            self._safe_cleanup_call(
                "notification worker stop", lambda: notifier.close()
            )

        if close_dimmer:
            dimmer = self.__dict__.get("dimmer")
            if dimmer is not None:
                self._safe_cleanup_call("dimmer close", lambda: dimmer.close())

    def _restart_app(self) -> None:
        """Restart the application to apply UI scale cleanly."""
        # Clean up before restart
        self._safe_cleanup_call(
            "flush dimmer config", self._flush_pending_dimmer_save
        )
        self._safe_cleanup_call(
            "flush Arena config", self._flush_pending_arena_save
        )
        self._stop_runtime_components()

        # Get the executable path
        if getattr(sys, "frozen", False):
            # Running as compiled exe
            exe_path = sys.executable
        else:
            # Running as script
            exe_path = sys.executable
            script_path = os.path.abspath(sys.argv[0])
            # --restart: child bỏ qua single-instance mutex (cha chưa thoát
            # hẳn khi child import — nếu không sẽ chết vì mutex, app biến mất)
            subprocess.Popen([exe_path, script_path, "--restart"])
            self.destroy()
            return

        subprocess.Popen([exe_path, "--restart"])
        self.destroy()

    def load_settings(self) -> None:
        # Load Dimmer Settings
        dimmer_val = config_manager.get("dimmer_value") or 100
        dimmer_enabled = config_manager.get("dimmer_enabled")
        if dimmer_enabled is None:
            dimmer_enabled = True

        # Load Dimmer Mode
        dimmer_mode = normalize_dimmer_mode(config_manager.get("dimmer_mode"))
        if dimmer_mode == "gaming":
            self.dimmer_mode_segment.set("🎮 Gaming")
            dimmer_val = config_manager.get("dimmer_gaming_value")
            if dimmer_val is None:
                dimmer_val = 100
        else:
            self.dimmer_mode_segment.set("🌐 Browsing")
            dimmer_val = config_manager.get("dimmer_browsing_value")
            if dimmer_val is None:
                dimmer_val = 100

        dimmer_val = normalize_dimmer_value(dimmer_val)
        self.dimmer_slider.set(float(dimmer_val))
        self.dimmer_enabled_var.set(dimmer_enabled)
        # Load Startup Settings
        saved_startup = get_autostart_state(AppConfig.APP_NAME)
        if saved_startup is None:
            saved_startup = config_manager.get("auto_startup_enabled")
            if saved_startup is None:
                saved_startup = False
        else:
            config_manager.set("auto_startup_enabled", saved_startup, save=False)
        self.auto_startup_enabled_var.set(saved_startup)

        # Load Auto Accept Settings
        saved_auto_accept = config_manager.get("auto_accept_enabled")
        if saved_auto_accept is None:
            saved_auto_accept = True
        self.auto_accept_enabled_var.set(saved_auto_accept)

        for spec in DISCORD_NOTIFICATION_SPECS:
            variable = getattr(self, f"{spec.config_key}_var")
            variable.set(bool(config_manager.get(spec.config_key)))
            self.notifier.set_event_enabled(spec.event_name, variable.get())

        # Apply settings immediately
        self.toggle_dimmer(save=False)
        logger.info(f"Dimmer backend active: {self.dimmer.backend_name}")

    def toggle_startup(self) -> None:
        is_enabled = self.auto_startup_enabled_var.get()
        previous_snapshot = get_autostart_snapshot(AppConfig.APP_NAME)
        if previous_snapshot is None:
            self.auto_startup_enabled_var.set(not is_enabled)
            logger.error("Auto Startup state read failed; keeping the previous state")
            return
        if not set_autostart(AppConfig.APP_NAME, add=is_enabled):
            self.auto_startup_enabled_var.set(not is_enabled)
            logger.error("Auto Startup change failed; keeping the previous state")
            return
        if not config_manager.set("auto_startup_enabled", is_enabled):
            if not restore_autostart_snapshot(previous_snapshot):
                logger.error("Auto Startup rollback failed")
            self.auto_startup_enabled_var.set(not is_enabled)
            logger.error("Auto Startup config save failed; keeping the previous state")
            return
        logger.info(f"Auto Startup toggled: {is_enabled}")

    def toggle_auto_accept(self) -> None:
        is_enabled = bool(self.auto_accept_enabled_var.get())
        previous = config_manager.get("auto_accept_enabled")
        if not config_manager.set("auto_accept_enabled", is_enabled):
            self.auto_accept_enabled_var.set(
                bool(previous) if previous is not None else not is_enabled
            )
            logger.error("Auto Accept save failed; keeping the previous state")
            return
        logger.info(f"Auto Accept Match toggled: {is_enabled}")

    def _toggle_discord_notification(
        self,
        spec: NotificationSpec,
        variable,
    ) -> None:
        is_enabled = bool(variable.get())
        previous = config_manager.get(spec.config_key)
        if not config_manager.set(spec.config_key, is_enabled):
            restored = bool(previous) if previous is not None else not is_enabled
            variable.set(restored)
            self.notifier.set_event_enabled(spec.event_name, restored)
            logger.error(
                f"Discord notification save failed; keeping {spec.event_name} state"
            )
            return
        self.notifier.set_event_enabled(spec.event_name, is_enabled)
        logger.info(f"Discord notification toggled: {spec.event_name}={is_enabled}")

    def _toggle_auto_dimmer_switch(self) -> None:
        """Handle auto dimmer switch toggle (auto-switch to Gaming mode on champ select)."""
        is_enabled = bool(self.auto_dimmer_switch_var.get())
        previous = config_manager.get("auto_dimmer_switch_enabled")
        if not config_manager.set("auto_dimmer_switch_enabled", is_enabled):
            self.auto_dimmer_switch_var.set(
                bool(previous) if previous is not None else not is_enabled
            )
            logger.error("Auto dimmer switch save failed; keeping the previous state")
            return
        logger.info(f"Auto dimmer switch toggled: {is_enabled}")

    def _set_arena_automation_enabled(self, enabled: bool) -> None:
        """Set the master gate for Arena ban/pick actions."""
        self._arena_automation_enabled = bool(enabled)
        watcher = self.__dict__.get("arena_watcher")
        if watcher is not None:
            watcher.set_automation_enabled(self._arena_automation_enabled)
        self._refresh_arena_validation()

    def start_bot(self) -> None:
        logger.info("Starting bot...")

        self._commit_empty_optional_picks()
        issues = self._refresh_arena_validation(force_errors=True)
        if issues:
            self._set_arena_automation_enabled(False)
            self._show_toast(
                "Không thể bắt đầu. Kiểm tra lại Cấu hình Arena.",
                Colors.STATUS_RED,
            )
            return

        # Guard: never run two bots at once (Stop does not kill the thread
        # instantly - it may still be winding down).
        if self.bot and self.bot.is_alive():
            messagebox.showwarning(
                "Tác vụ đang dừng",
                "Tác vụ trước vẫn đang dừng. Hãy chờ một chút rồi thử lại.",
            )
            return

        self._set_arena_automation_enabled(True)
        self._bot_generation += 1
        generation = self._bot_generation
        self._bot_stopping = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.bot = AntiFateBot(
            update_status_callback=lambda text, color, g=generation: self._post_to_ui(
                self._on_bot_status, g, text, color
            ),
            on_stop_callback=lambda status, color, g=generation: self._post_to_ui(
                self.on_bot_stop, status, color, g
            ),
            on_success_callback=lambda g=generation: self._post_to_ui(
                self._on_bot_success, g
            ),
            on_champ_select_callback=lambda g=generation: self._post_to_ui(
                self._on_bot_champ_select, g
            ),
        )
        self.bot.start()

    def stop_bot(self) -> None:
        logger.info("Bot Stopping...")
        self._bot_stopping = True
        self._set_arena_automation_enabled(False)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.update_status("Đang dừng...", "orange")
        if self.bot:
            self.bot.stop()
        else:
            self._bot_stopping = False
            self.update_status(UIStatus.STOPPED, "gray")

    def on_closing(self) -> None:
        """Cleanup before closing"""
        logger.info("Closing application...")
        for timer_name in (
            "_beacon_pulse_id",
            "_arena_validation_after_id",
            "_dimmer_watchdog_id",
        ):
            timer_id = self.__dict__.get(timer_name)
            if timer_id:
                self._safe_cleanup_call(
                    f"cancel {timer_name}",
                    lambda timer_id=timer_id: self.after_cancel(timer_id),
                )
                setattr(self, timer_name, None)
        self._safe_cleanup_call(
            "flush dimmer config",
            self._flush_pending_dimmer_save,
        )
        self._safe_cleanup_call(
            "flush Arena config",
            self._flush_pending_arena_save,
        )
        try:
            self._stop_runtime_components(close_dimmer=False)
        except Exception as error:
            logger.error("Runtime cleanup failed: %s", error)
        finally:
            dimmer = self.__dict__.get("dimmer")
            if dimmer is not None:
                self._safe_cleanup_call("dimmer close", lambda: dimmer.close())
            self._safe_cleanup_call("destroy window", lambda: self.destroy())
        raise SystemExit(0)
