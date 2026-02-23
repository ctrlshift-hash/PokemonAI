"""
Coordinate-based navigator for Pokemon FireRed.
Uses verified warp coordinates from the pokefirered decompilation.
LLM decides WHERE to go, this module handles the actual walking.
"""

import json
import logging

from config import settings

logger = logging.getLogger(__name__)

WARP_DATA_FILE = settings.PROJECT_ROOT / "data" / "warp_data.json"


class Navigator:
    """Walks the player to a target coordinate using simple pathfinding."""

    def __init__(self):
        self.warp_data = self._load_warp_data()
        self.target = None       # (x, y) target coordinates
        self.target_label = ""   # human-readable name
        self.target_map = -1     # map the target is on
        self.active = False

        # Stuck handling
        self._prev_x = -1
        self._prev_y = -1
        self._stuck_count = 0
        self._stuck_dir_idx = 0  # cycle through unstick directions

        # Detour: when stuck, commit to walking perpendicular for several ticks
        self._detour_dir = None
        self._detour_ticks = 0
        self._total_stuck = 0  # how many times we've been stuck total

    def set_target(self, map_id, landmark_key):
        """Set navigation target by landmark key. Returns True if valid."""
        map_data = self.warp_data.get(str(map_id))
        if not map_data:
            logger.warning(f"No warp data for map {map_id}")
            return False

        landmark = map_data.get("landmarks", {}).get(landmark_key)
        if not landmark:
            logger.warning(
                f"No landmark '{landmark_key}' on map {map_id} "
                f"({map_data.get('name', '?')})"
            )
            return False

        self.target = (landmark["x"], landmark["y"])
        self.target_label = landmark.get("label", landmark_key)
        self.target_map = map_id
        self.active = True
        self._stuck_count = 0
        self._prev_x = -1
        self._prev_y = -1
        self._stuck_dir_idx = 0
        self._detour_dir = None
        self._detour_ticks = 0
        self._total_stuck = 0

        logger.info(
            f"Navigator: target set to {self.target_label} "
            f"at ({landmark['x']}, {landmark['y']}) on map {map_id}"
        )
        return True

    def get_next_direction(self, player_x, player_y, current_map):
        """
        Get the next direction to walk toward the target.
        Returns a direction string ("UP", "DOWN", "LEFT", "RIGHT") or None if arrived.
        """
        if not self.active or not self.target:
            return None

        # Cancel if map changed (entered a building, etc.)
        if current_map != self.target_map:
            logger.info(
                f"Navigator: map changed ({self.target_map} -> {current_map}), "
                "cancelling navigation"
            )
            self.cancel()
            return None

        tx, ty = self.target
        dx = tx - player_x
        dy = ty - player_y

        # Arrived (within 1 tile)
        if abs(dx) <= 1 and abs(dy) <= 1:
            logger.info(f"Navigator: arrived at {self.target_label}!")
            self.active = False
            self._total_stuck = 0
            return None

        # If mid-detour, keep walking that direction
        if self._detour_ticks > 0:
            # Check if detour direction is also blocked
            if player_x == self._prev_x and player_y == self._prev_y:
                # Detour direction blocked too - try the other perpendicular
                self._detour_ticks = 0
                self._stuck_dir_idx += 1
                self._stuck_count = 3  # force immediate re-detour
                self._prev_x = player_x
                self._prev_y = player_y
                return self._start_detour(dx, dy)
            else:
                # Detour is working, keep going
                self._detour_ticks -= 1
                self._prev_x = player_x
                self._prev_y = player_y
                if self._detour_ticks > 0:
                    return self._detour_dir
                # Detour finished - fall through to normal pathfinding

        # Stuck detection
        if player_x == self._prev_x and player_y == self._prev_y:
            self._stuck_count += 1
        else:
            self._stuck_count = 0
        self._prev_x = player_x
        self._prev_y = player_y

        # If stuck for 3+ ticks, start a detour
        if self._stuck_count >= 3:
            self._total_stuck += 1
            return self._start_detour(dx, dy)

        # Give up and cancel if stuck way too many times
        if self._total_stuck >= 15:
            logger.info(
                f"Navigator: giving up after {self._total_stuck} stuck events, "
                f"cancelling navigation to {self.target_label}"
            )
            self.cancel()
            return None

        # Normal pathfinding: close the larger gap first
        if abs(dx) > abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        elif abs(dy) > 0:
            return "DOWN" if dy > 0 else "UP"
        else:
            return "RIGHT" if dx > 0 else "LEFT"

    def _start_detour(self, dx, dy):
        """Start a multi-tick detour to walk around an obstacle."""
        # Detour gets longer the more times we've been stuck (3 -> 5 -> 7 -> ...)
        detour_len = min(3 + self._total_stuck * 2, 12)

        # Pick perpendicular direction based on which axis we're trying to move on
        if abs(dx) >= abs(dy):
            options = ["UP", "DOWN"]
        else:
            options = ["LEFT", "RIGHT"]

        # Alternate which perpendicular direction we try
        self._detour_dir = options[self._stuck_dir_idx % len(options)]
        self._detour_ticks = detour_len
        self._stuck_count = 0

        logger.info(
            f"Navigator: stuck! Detouring {self._detour_dir} for "
            f"{detour_len} ticks (stuck count: {self._total_stuck})"
        )
        return self._detour_dir

    def cancel(self):
        """Cancel current navigation."""
        if self.active:
            logger.info(f"Navigator: cancelled (was heading to {self.target_label})")
        self.active = False
        self.target = None
        self.target_label = ""
        self.target_map = -1
        self._detour_dir = None
        self._detour_ticks = 0
        self._total_stuck = 0

    def distance_remaining(self, player_x, player_y):
        """Manhattan distance to target."""
        if not self.target:
            return 0
        return abs(self.target[0] - player_x) + abs(self.target[1] - player_y)

    def get_available_targets(self, map_id):
        """Get list of available landmark keys for a map."""
        map_data = self.warp_data.get(str(map_id))
        if not map_data:
            return []
        return list(map_data.get("landmarks", {}).keys())

    def get_targets_text(self, map_id):
        """Format available targets as text for the LLM prompt."""
        map_data = self.warp_data.get(str(map_id))
        if not map_data:
            return ""
        landmarks = map_data.get("landmarks", {})
        if not landmarks:
            return ""
        parts = []
        for key, info in landmarks.items():
            goto_cmd = f"GOTO_{key.upper()}"
            parts.append(f"  {goto_cmd} = walk to {info.get('label', key)}")
        return "\n".join(parts)

    def _load_warp_data(self):
        """Load warp coordinate database."""
        if not WARP_DATA_FILE.exists():
            logger.error(f"Warp data file not found: {WARP_DATA_FILE}")
            return {}
        with open(WARP_DATA_FILE) as f:
            data = json.load(f)
        total = sum(len(m.get("landmarks", {})) for m in data.values())
        logger.info(f"Navigator: loaded {total} landmarks across {len(data)} maps")
        return data
