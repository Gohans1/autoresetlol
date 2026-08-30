"""Dimmer settings and automatic mode UI mixin."""

from __future__ import annotations

import time

from config import config_manager, normalize_dimmer_value
from constants import Colors
from logger import logger


DIMMER_SAVE_DEBOUNCE_MS = 250


class DimmerUiMixin:
    def _on_dimmer_mode_changed(self, mode: str, automatic: bool = False) -> None:
        """Handle dimmer mode switch between Gaming and Browsing."""
        if automatic and not self._automatic_dimmer_allowed():
            return
        # Save current slider value to the current mode before switching
        current_slider_val = int(self.dimmer_slider.get())
        old_mode = config_manager.get("dimmer_mode")

        # Map display name to internal key
        if "Gaming" in mode:
            new_mode = "gaming"
        else:
            new_mode = "browsing"

        # Save current value to the OLD mode (skip if called from switch_to_gaming_mode
        # OR if dimmer was visually reset to 100% by reset_dimmer())
        if not self._skip_dimmer_save and not self._dimmer_reset_visual:
            if old_mode == "gaming":
                config_manager.set(
                    "dimmer_gaming_value", current_slider_val, save=False
                )
            else:
                config_manager.set(
                    "dimmer_browsing_value", current_slider_val, save=False
                )

        # Reset flags
        self._skip_dimmer_save = False
        self._dimmer_reset_visual = False

        # Switch mode
        config_manager.set("dimmer_mode", new_mode, save=False)

        # Load and apply value for the NEW mode
        if new_mode == "gaming":
            new_val = config_manager.get("dimmer_gaming_value")
            if new_val is None:
                new_val = 100
        else:
            new_val = config_manager.get("dimmer_browsing_value")
            if new_val is None:
                new_val = 100

        new_val = normalize_dimmer_value(new_val)
        self.dimmer_slider.set(float(new_val))
        if self.dimmer_enabled_var.get():
            self.dimmer.set_brightness(new_val)
        config_manager.set("dimmer_value", new_val, save=False)
        self._dimmer_save_dirty = True
        saved = self._save_dimmer_config()
        if saved:
            logger.info(f"Dimmer mode switched to: {new_mode} (brightness: {new_val}%)")
        else:
            logger.warning(
                f"Dimmer mode switched to: {new_mode} (brightness: {new_val}%), "
                "config save pending"
            )

    def _automatic_dimmer_allowed(self) -> bool:
        """Single gate for every automatic dimmer write."""
        return (
            config_manager.get("auto_dimmer_switch_enabled") is True
            and config_manager.get("dimmer_enabled") is True
        )

    def _apply_automatic_mode(self, mode: str) -> None:
        """Apply a deferred automatic mode change only if gates still allow it."""
        if not self._automatic_dimmer_allowed():
            self._skip_dimmer_save = False
            return
        self.dimmer_mode_segment.set(mode)
        self._on_dimmer_mode_changed(mode, automatic=True)

    def _apply_automatic_brightness(self, level: int) -> None:
        """Apply deferred automatic brightness only if gates still allow it."""
        if not self._automatic_dimmer_allowed():
            self._dimmer_reset_visual = False
            return
        self.dimmer_slider.set(float(level))
        self.dimmer.set_brightness(level)

    def switch_to_gaming_mode(self) -> None:
        """Callback to switch to Gaming dimmer mode (called by bot on champ select)."""
        if not self._automatic_dimmer_allowed():
            return

        current_mode = config_manager.get("dimmer_mode")
        if current_mode != "gaming":
            logger.info("Champ select detected - switching to Gaming dimmer mode")

            # FIX (v1.15): save browsing from CONFIG, NOT from the slider.
            # reset_dimmer() runs first (same bot tick) and queues a visual
            # slider.set(100) via after(0); by the time this callback reads
            # the slider the main thread may have applied it, overwriting the
            # real browsing value with 100 (race - reproduced in logs:
            # "Saved browsing dimmer value: 100%").
            if current_mode == "browsing":
                browsing_val = config_manager.get("dimmer_browsing_value")
                if browsing_val is None:
                    browsing_val = 100
                browsing_val = normalize_dimmer_value(browsing_val)
                config_manager.set("dimmer_browsing_value", browsing_val, save=False)
                self._dimmer_save_dirty = True
                saved = self._save_dimmer_config()
                if saved:
                    logger.info(f"Saved browsing dimmer value: {browsing_val}%")
                else:
                    logger.warning("Browsing dimmer value save pending")

            # Set flag to prevent _on_dimmer_mode_changed from re-saving (would save wrong value)
            self._skip_dimmer_save = True
            self.after(10, lambda: self._apply_automatic_mode("🎮 Gaming"))
        else:
            # FIX (v1.15 review): mode is already gaming - re-apply the
            # configured gaming value anyway. reset_dimmer() (success
            # callback of the previous match) set the slider AND the real
            # brightness to 100; without this re-apply the screen would
            # stay at 100% from the second match onward (dimmer silently
            # dead - reproduced in the user's logs).
            gv = config_manager.get("dimmer_gaming_value")
            if gv is None:
                gv = 100
            gv = normalize_dimmer_value(gv)
            self._dimmer_reset_visual = False
            self.after(0, lambda: self._apply_automatic_brightness(gv))
            logger.info(
                f"Champ select detected - re-applying Gaming dimmer "
                f"(already in gaming mode, {gv}%)"
            )

    def switch_to_browsing_mode(self) -> None:
        """Callback từ LCU watcher — hết trận/trở về phòng chờ → Browsing."""
        if not self._automatic_dimmer_allowed():
            return

        current_mode = config_manager.get("dimmer_mode")
        if current_mode != "browsing":
            logger.info("Match ended - switching to Browsing dimmer mode")

            # Lưu gaming value từ CONFIG (không đọc slider — tránh race
            # với reset_dimmer đang set slider về 100).
            if current_mode == "gaming":
                gaming_val = config_manager.get("dimmer_gaming_value")
                if gaming_val is None:
                    gaming_val = 100
                gaming_val = normalize_dimmer_value(gaming_val)
                config_manager.set("dimmer_gaming_value", gaming_val, save=False)
                self._dimmer_save_dirty = True
                self._save_dimmer_config()

            self._skip_dimmer_save = True
            self.after(10, lambda: self._apply_automatic_mode("🌐 Browsing"))
        else:
            # Đã ở browsing — re-apply giá trị (phòng reset_dimmer đã set 100)
            bv = config_manager.get("dimmer_browsing_value")
            if bv is None:
                bv = 100
            bv = normalize_dimmer_value(bv)
            self._dimmer_reset_visual = False
            self.after(0, lambda: self._apply_automatic_brightness(bv))
            logger.info(f"Match ended - re-applying Browsing dimmer ({bv}%)")

    def toggle_dimmer(self, save: bool = True) -> None:
        is_enabled = self.dimmer_enabled_var.get()
        current_val = self.dimmer_slider.get()

        if save:
            config_manager.set("dimmer_enabled", is_enabled, save=False)
            self._dimmer_save_dirty = True
            self._save_dimmer_config()

        if is_enabled:
            self.dimmer_slider.configure(state="normal", button_color=Colors.PRIMARY)

            # Smooth Step Down
            if current_val < 90:
                temp_val = 90
                while temp_val > current_val:
                    self.dimmer.set_brightness(int(temp_val))
                    temp_val -= 20
                    time.sleep(0.015)

            # Final set
            self.dimmer.set_brightness(int(current_val))
        else:
            self.dimmer_slider.configure(
                state="disabled", button_color=Colors.SECONDARY
            )
            self.dimmer.set_brightness(100)

    def _schedule_dimmer_save(self) -> None:
        if self._dimmer_save_after_id:
            try:
                self.after_cancel(self._dimmer_save_after_id)
            except Exception:
                pass
        self._dimmer_save_after_id = self.after(
            DIMMER_SAVE_DEBOUNCE_MS,
            self._flush_dimmer_save,
        )

    def _save_dimmer_config(self) -> bool:
        if config_manager.save_config():
            self._dimmer_save_dirty = False
            return True
        self._dimmer_save_dirty = True
        logger.error("Dimmer config save failed; keeping pending value")
        return False

    def _flush_dimmer_save(self) -> None:
        self._dimmer_save_after_id = None
        self._save_dimmer_config()

    def _flush_pending_dimmer_save(self) -> None:
        if not self._dimmer_save_after_id and not getattr(
            self, "_dimmer_save_dirty", False
        ):
            return
        if self._dimmer_save_after_id:
            try:
                self.after_cancel(self._dimmer_save_after_id)
            except Exception:
                pass
        self._dimmer_save_after_id = None
        self._save_dimmer_config()

    def change_brightness(self, value: float) -> None:
        # Only apply if enabled
        if self.dimmer_enabled_var.get():
            self.dimmer.set_brightness(int(value))
            # Keep slider drags in memory and save once after the user pauses.
            config_manager.set("dimmer_value", int(value), save=False)

            # Clear visual reset flag when user actively drags slider
            # This means user is now manually setting brightness
            self._dimmer_reset_visual = False

            # Also save to the current mode's specific value
            current_mode = config_manager.get("dimmer_mode") or "browsing"
            if current_mode == "gaming":
                config_manager.set("dimmer_gaming_value", int(value), save=False)
            else:
                config_manager.set("dimmer_browsing_value", int(value), save=False)
            self._dimmer_save_dirty = True
            self._schedule_dimmer_save()
            logger.debug(
                f"Slider changed to {int(value)}% ({current_mode} mode) - "
                f"gaming={config_manager.get('dimmer_gaming_value')} "
                f"browsing={config_manager.get('dimmer_browsing_value')}"
            )

    def _start_dimmer_watchdog(self) -> None:
        """Periodically verify the dimmer state matches the slider (safety).

        Guards against drift caused by Windows adaptive brightness or a
        partially failed set. Re-applies the target when it detects a gap.
        """
        self._dimmer_watchdog_id = self.after(5000, self._dimmer_watchdog_tick)

    def _dimmer_watchdog_tick(self) -> None:
        try:
            if self._automatic_dimmer_allowed():
                target = int(self.dimmer_slider.get())
                if not self.dimmer.verify(target):
                    # Re-apply only after 2 consecutive drifts (~10s): a
                    # single mismatch can be transient (or a Night Light
                    # style colour filter) - don't fight it immediately.
                    self._watchdog_drift_count += 1
                    if self._watchdog_drift_count >= 2:
                        logger.info(
                            f"Dimmer watchdog: display drifted from {target}% - "
                            f"re-applying ({self.dimmer.backend_name})"
                        )
                        self._apply_automatic_brightness(target)
                else:
                    self._watchdog_drift_count = 0
        except Exception as e:
            logger.error(f"Dimmer watchdog error: {e}")
        self._start_dimmer_watchdog()

    def reset_dimmer(self) -> None:
        """Force reset dimmer to 100% (Success callback).

        This is a VISUAL-ONLY reset. The slider shows 100% but config values
        are NOT overwritten. This prevents browsing/gaming values from being
        lost when mode switches after a reset.
        """
        if not self._automatic_dimmer_allowed():
            return
        logger.info("Bot success confirmed. Resetting dimmer to 100% (visual only).")
        # Set flag to prevent _on_dimmer_mode_changed from saving this fake 100 value
        self._dimmer_reset_visual = True
        self.after(0, lambda: self._apply_automatic_brightness(100))
