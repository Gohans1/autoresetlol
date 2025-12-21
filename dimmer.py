import ctypes
from ctypes import wintypes
import time

# Load GDI32 and User32 libraries
gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32


class Dimmer:
    def __init__(self):
        self.hdc = user32.GetDC(None)
        self.original_ramp = (wintypes.WORD * 768)()
        self.current_brightness = 100

        # Try to save original ramp, though we might just reset to linear 100% on exit
        # GetDeviceGammaRamp(self.hdc, ctypes.byref(self.original_ramp))

    def set_brightness(self, level):
        """
        Set screen brightness using Gamma Ramp.
        level: 0 to 100 (integer)
        """
        # Clamp level
        level = max(
            10, min(100, int(level))
        )  # Don't go below 10% to prevent black screen panic
        self.current_brightness = level

        ramp = (wintypes.WORD * 768)()

        # Calculate gamma ramp
        # 3 arrays of 256 entries (R, G, B) flattened to 768
        # Standard linear ramp value for index i is i * 256 (mapping 0-255 to 0-65535)
        # We scale this by level/100

        for i in range(256):
            val = i * 256
            adjusted_val = int(val * (level / 100.0))
            # Limit to 65535
            adjusted_val = min(65535, adjusted_val)

            # Set R, G, B same value
            ramp[i] = adjusted_val  # Red
            ramp[i + 256] = adjusted_val  # Green
            ramp[i + 512] = adjusted_val  # Blue

        success = gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(ramp))
        return success

    def reset(self):
        """Reset to 100% brightness"""
        self.set_brightness(100)

    def close(self):
        """Cleanup resources"""
        if self.hdc:
            self.reset()
            user32.ReleaseDC(None, self.hdc)
            self.hdc = None


# Create a global instance if needed, or instantiate in App
if __name__ == "__main__":
    # Test
    d = Dimmer()
    print("Dimming to 50%...")
    d.set_brightness(50)
    time.sleep(2)
    print("Resetting...")
    d.reset()
    d.close()
