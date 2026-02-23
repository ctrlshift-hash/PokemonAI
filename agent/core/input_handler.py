"""
Keyboard input handler for mGBA emulator.
Sends button presses via pydirectinput (DirectInput scan codes).
Pokemon has 8 buttons: A, B, Start, Select, Up, Down, Left, Right.
"""

import logging
import time

import pydirectinput

from config import settings

logger = logging.getLogger(__name__)

pydirectinput.FAILSAFE = False
pydirectinput.PAUSE = 0.02


def press_button(button, hold_seconds=0.1):
    """
    Press a single GBA button.
    Maps button name (A, B, START, etc.) to keyboard key via BUTTON_MAP.
    """
    button = button.upper().strip()
    key = settings.BUTTON_MAP.get(button)
    if not key:
        logger.warning(f"Unknown button: {button}")
        return False

    try:
        pydirectinput.keyDown(key)
        time.sleep(hold_seconds)
        pydirectinput.keyUp(key)
        logger.debug(f"Pressed {button} ({key}) for {hold_seconds}s")
        return True
    except Exception as e:
        logger.error(f"Failed to press {button}: {e}")
        return False


def press_direction(direction, hold_seconds=0.3):
    """Press a direction button with longer hold for movement."""
    return press_button(direction, hold_seconds=hold_seconds)


def press_sequence(buttons, delay=0.15):
    """
    Press multiple buttons in sequence.
    buttons: list of button names like ["A", "UP", "A"]
    """
    results = []
    for button in buttons:
        if button.upper() == "WAIT":
            time.sleep(delay * 3)
            results.append(True)
            continue

        is_direction = button.upper() in settings.DIRECTION_BUTTONS
        hold = 0.3 if is_direction else 0.1
        result = press_button(button, hold_seconds=hold)
        results.append(result)
        time.sleep(delay)

    return results


def execute_action(action):
    """
    Execute a single action returned by the LLM.
    action: string like "A", "UP", "DOWN", "START", "WAIT", etc.
    Returns True on success.
    """
    action = action.upper().strip()

    if action == "WAIT":
        time.sleep(0.5)
        logger.debug("Waited 0.5s")
        return True

    if action in settings.BUTTON_MAP:
        is_direction = action in settings.DIRECTION_BUTTONS
        hold = 0.3 if is_direction else 0.1
        return press_button(action, hold_seconds=hold)

    logger.warning(f"Unknown action: {action}")
    return False
