"""
Screenshot capture for the mGBA emulator window.
Uses ctypes to find the window and mss for fast screen capture.
"""

import base64
import ctypes
import ctypes.wintypes
import io
import logging

import mss
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)


class ScreenCapture:
    """Captures screenshots of the mGBA emulator window."""

    def __init__(self):
        self.hwnd = None
        self.sct = mss.mss()
        self._find_window()

    def _find_window(self):
        """Find the mGBA main window (largest one with 'mGBA' in title)."""
        # Enumerate all windows containing "mGBA" and pick the largest
        results = []

        def enum_cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if "mgba" in buf.value.lower():
                    rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    area = (rect.right - rect.left) * (rect.bottom - rect.top)
                    results.append((hwnd, buf.value, area))
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        if results:
            # Pick the largest mGBA window (the main game window)
            results.sort(key=lambda x: x[2], reverse=True)
            self.hwnd, title, area = results[0]
            logger.info(f"Found mGBA window: '{title}' (hwnd={self.hwnd}, area={area})")
        else:
            logger.warning(
                "mGBA window not found. Make sure mGBA is running."
            )

    def get_window_rect(self):
        """Get the mGBA window bounding box."""
        if not self.hwnd:
            self._find_window()
        if not self.hwnd:
            return None

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def capture(self):
        """
        Capture a screenshot of the mGBA window.
        Returns a PIL Image resized to SCREENSHOT_WIDTH x SCREENSHOT_HEIGHT.
        """
        rect = self.get_window_rect()
        if not rect:
            logger.warning("No window rect available, capturing full screen")
            monitor = self.sct.monitors[1]
        else:
            left, top, right, bottom = rect
            # Clamp to positive values (Windows invisible borders)
            left = max(0, left)
            top = max(0, top)
            monitor = {
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
            }

        logger.debug(f"Capture region: {monitor}")
        screenshot = self.sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

        # Save first capture for debugging
        if not hasattr(self, '_debug_saved'):
            debug_path = settings.PROJECT_ROOT / "data" / "debug_capture.png"
            img.save(str(debug_path))
            logger.info(f"Debug screenshot saved to {debug_path} (size: {img.size})")
            self._debug_saved = True

        # Resize to target dimensions
        img = img.resize(
            (settings.SCREENSHOT_WIDTH, settings.SCREENSHOT_HEIGHT),
            Image.LANCZOS,
        )

        return img

    def capture_base64(self):
        """Capture screenshot and return as JPEG base64 string."""
        img = self.capture()
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=settings.JPEG_QUALITY)
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return b64, img

    def bring_to_front(self):
        """Bring the mGBA window to the foreground."""
        if not self.hwnd:
            self._find_window()
        if self.hwnd:
            user32.SetForegroundWindow(self.hwnd)
