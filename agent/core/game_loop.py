"""
Main game loop orchestrator.
Ties together: screenshot -> vision -> planning -> action -> memory
Runs continuously until stopped.
"""

import logging
import signal
import time
import traceback
from datetime import datetime

from config import settings
from agent.core.screen_capture import ScreenCapture
from agent.core.vision import VisionEngine
from agent.core import input_handler
from agent.core.memory_reader import GameState
from agent.core.battle_manager import BattleManager
from agent.core.player_stats import PlayerStats
from agent.core.navigator import Navigator
from agent.core.db import push_live_feed, create_session, update_session, end_session
from agent.memory.chroma_store import ChromaStore
from agent.memory.memory_types import MemoryType
from agent.planning.goal_planner import GoalPlanner
from agent.ui.overlay import Overlay

logger = logging.getLogger(__name__)


class GameLoop:
    """
    The main autonomous game loop.
    Screenshot -> LLM Vision -> Decide -> Act -> Remember -> Repeat
    """

    def __init__(self):
        logger.info("Initializing Pokemon AI Agent...")

        self.screen = ScreenCapture()
        self.vision = VisionEngine()
        self.memory = ChromaStore()
        self.planner = GoalPlanner()
        self.battle = BattleManager()
        self.stats = PlayerStats()
        self.navigator = Navigator()

        # State
        self.running = False
        self.loop_count = 0
        self.consecutive_errors = 0
        self.start_time = None
        self.session_id = None
        self.recent_actions = []

        # Overlay
        self.overlay = None
        logger.info(f"OVERLAY_ENABLED={settings.OVERLAY_ENABLED}")
        if settings.OVERLAY_ENABLED:
            try:
                self.overlay = Overlay(
                    hwnd=self.screen.hwnd,
                    width=settings.OVERLAY_WIDTH,
                )
                logger.info("Overlay initialized successfully")
            except Exception as e:
                logger.warning(f"Overlay init failed: {e}")
                import traceback
                logger.warning(traceback.format_exc())

        # Stuck detection
        self._prev_x = -1
        self._prev_y = -1
        self._stuck_count = 0

        # Signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        logger.info("Agent initialized successfully")

    def _handle_shutdown(self, signum, frame):
        logger.info("Shutdown signal received, stopping...")
        self.running = False

    def setup(self):
        """One-time setup before the main loop."""
        logger.info("Running setup...")

        # Initialize goals if none exist
        if not self.planner.goals:
            logger.info("No existing goals - setting up FireRed progression")
            self.planner.setup_firered_goals()

        # Store startup memory
        self.memory.add(
            "Agent started a new session",
            MemoryType.GENERAL,
            metadata={"event": "startup"},
        )

        logger.info("Setup complete")

    def run(self):
        """Main game loop - runs until stopped."""
        self.setup()
        self.running = True
        self.start_time = time.time()
        self.session_id = create_session()

        logger.info("=" * 60)
        logger.info("Pokemon AI Agent is now running")
        logger.info(f"Model: {settings.MODEL}")
        logger.info(f"Tick interval: {settings.TICK_INTERVAL}s")
        logger.info(f"Total memories: {self.memory.total_memories}")
        logger.info(f"Active goals: {len(self.planner.goals)}")
        logger.info("=" * 60)

        while self.running:
            try:
                self._tick()
                self.consecutive_errors = 0
                time.sleep(settings.TICK_INTERVAL)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt - stopping")
                break
            except Exception as e:
                self.consecutive_errors += 1
                logger.error(f"Game loop error ({self.consecutive_errors}): {e}")
                logger.error(traceback.format_exc())

                if self.consecutive_errors >= settings.MAX_CONSECUTIVE_ERRORS:
                    logger.error(
                        f"Too many errors ({self.consecutive_errors}), "
                        f"pausing for {settings.ERROR_PAUSE_SECONDS}s..."
                    )
                    time.sleep(settings.ERROR_PAUSE_SECONDS)
                    self.consecutive_errors = 0

        self._shutdown()

    def _tick(self):
        """Single iteration of the game loop. LLM decides EVERY action."""
        self.loop_count += 1
        tick_start = time.time()

        # 1. Read game memory from Lua-written JSON
        game_state = GameState.read()

        # If Lua script hasn't written game_state.json yet, wait
        if not settings.GAME_STATE_FILE.exists():
            if self.loop_count % 5 == 1:
                logger.info(
                    "Waiting for Lua script... "
                    "Load it in mGBA: Tools > Scripting > File > Load Script"
                )
            return

        # 2. Update stats from game state
        self.stats.update(game_state)

        # 3. Update battle tracking
        battle_events = self.battle.update(game_state)
        if battle_events.get("battle_end") == "won":
            self.stats.battles_won += 1

        # 4. Capture screenshot
        screenshot_b64, screenshot_img = self.screen.capture_base64()

        # 5. Get current goal context
        goal_context = self.planner.get_active_goal_context()

        # 6. Query relevant memories
        memory_query = f"{game_state.map_name} {goal_context}"
        memory_context = self.memory.get_context_for_situation(memory_query)

        # 7. Build extra context
        extra_context = self._build_extra_context(game_state)

        # 8. Get recent actions text
        recent_actions_text = self.vision.get_recent_actions_text()

        # 9. Send to LLM - it decides everything
        analysis = self.vision.analyze(
            screenshot_b64=screenshot_b64,
            game_state_text=game_state.get_party_summary(),
            current_goal=goal_context,
            memories=memory_context,
            recent_actions=recent_actions_text,
            extra_context=extra_context,
        )

        logger.info(
            f"[Tick {self.loop_count}] "
            f"Phase: {analysis.get('game_phase', '?')} | "
            f"See: {analysis.get('observation', '')[:80]} | "
            f"Action: {analysis.get('action', '?')}"
        )

        # 10. Execute the action chosen by LLM
        action = analysis.get("action", "A")

        if action in settings.DIRECTION_BUTTONS and not game_state.in_battle:
            # Direction press in overworld - walk a few steps
            for _ in range(3):
                input_handler.press_button(action, hold_seconds=0.12)
                time.sleep(0.03)
        else:
            # Button press (A, B, START, etc.)
            input_handler.execute_action(action)

        # Track action
        self.recent_actions.append(action)
        self.recent_actions = self.recent_actions[-20:]

        self.stats.log_action(
            self.loop_count,
            action,
            analysis.get("observation", ""),
            analysis.get("game_phase", "unknown"),
        )

        # Update overlay
        if self.overlay:
            hp_text = self._get_hp_text(game_state)
            self.overlay.update({
                "tick": self.loop_count,
                "game_phase": analysis.get("game_phase", "?"),
                "observation": analysis.get("observation", ""),
                "reasoning": analysis.get("reasoning", ""),
                "action": analysis.get("action", ""),
                "action_detail": analysis.get("action_detail", ""),
                "next_plan": analysis.get("next_plan", ""),
                "hp_status": hp_text,
            })

        # 14. Save memory if LLM suggests one
        save_memory = analysis.get("save_memory")
        if save_memory and save_memory != "null" and save_memory.strip():
            self.memory.add(
                save_memory,
                MemoryType.GENERAL,
                metadata={
                    "source": "llm",
                    "location": game_state.map_name,
                    "tick": self.loop_count,
                },
            )

        # 15. Process goal updates
        goal_update = analysis.get("goal_update")
        current_goal = self.planner.get_current_goal()
        if goal_update and current_goal and goal_update != "null":
            if "complete" in str(goal_update).lower():
                self.planner.complete_goal(current_goal.id, str(goal_update))
            elif "fail" in str(goal_update).lower():
                self.planner.fail_goal(current_goal.id, str(goal_update))
            elif "progress" in str(goal_update).lower():
                current_goal.notes.append(str(goal_update))

        # 16. Push to dashboard
        if self.loop_count % settings.DB_UPDATE_INTERVAL == 0:
            self._push_dashboard(game_state, analysis, tick_start, screenshot_b64)

        # 17. Periodic session update
        if self.session_id and self.loop_count % 10 == 0:
            update_session(
                self.session_id,
                ticks=self.loop_count,
                badges=game_state.badge_count,
                pokemon_caught=self.stats.pokemon_caught,
                whiteouts=self.stats.whiteouts,
            )

        tick_duration = time.time() - tick_start
        logger.debug(
            f"Tick {self.loop_count} completed in {tick_duration:.2f}s | "
            f"Memories: {self.memory.total_memories}"
        )

    def _get_hp_text(self, game_state):
        """Format lead Pokemon HP for overlay."""
        if not game_state.party:
            return "--"
        lead = game_state.party[0]
        name = lead.get("species_name", "?")
        hp_c = lead.get("hp_current", 0)
        hp_m = lead.get("hp_max", 1)
        return f"{name}: {hp_c}/{hp_m}"

    def _build_extra_context(self, game_state):
        """Build additional context for the LLM based on current state."""
        parts = []

        # Battle context
        if self.battle.in_battle:
            parts.append(self.battle.get_battle_context(game_state))

        # Critical HP warning
        if game_state.party:
            lead = game_state.party[0]
            lead_hp = lead.get("hp_current", 0)
            lead_max = lead.get("hp_max", 1)
            lead_name = lead.get("species_name", "Pokemon")
            lead_pct = (lead_hp / lead_max * 100) if lead_max > 0 else 0

            if lead_hp == 0 and not self.battle.in_battle:
                parts.append(
                    f"\nCRITICAL: {lead_name} has FAINTED! "
                    "Open menu (START) and switch to a healthy Pokemon, "
                    "then go to the nearest Pokemon Center!"
                )
            elif 0 < lead_pct < 25:
                parts.append(
                    f"\nCRITICAL HP WARNING: {lead_name} is at "
                    f"{lead_hp}/{lead_max} HP ({lead_pct:.0f}%)! "
                    "STOP fighting and go to a Pokemon Center NOW! "
                    "Avoid tall grass and trainers!"
                )

            all_low = all(
                (p.get("hp_current", 0) / max(p.get("hp_max", 1), 1)) < 0.25
                for p in game_state.party
            )
            if all_low:
                parts.append(
                    "\nEMERGENCY: ALL POKEMON ARE LOW HP! "
                    "GO TO POKEMON CENTER IMMEDIATELY! "
                    "Do NOT enter grass or fight anyone!"
                )

        # Navigation hints based on current map (no coord-based directions - those are unreliable)
        if not self.battle.in_battle:
            info = _MAP_INFO.get(game_state.map_id)
            if info:
                parts.append(f"\nNAVIGATION: {info}")

        # Stuck detection
        if game_state.player_x == self._prev_x and game_state.player_y == self._prev_y:
            self._stuck_count += 1
        else:
            self._stuck_count = 0
        self._prev_x = game_state.player_x
        self._prev_y = game_state.player_y

        if self._stuck_count >= 3 and not self.battle.in_battle:
            last_dir = ""
            for a in reversed(self.recent_actions):
                if a in settings.DIRECTION_BUTTONS:
                    last_dir = a
                    break
            if last_dir:
                parts.append(
                    f"\nSTUCK! You pressed {last_dir} but did NOT move. "
                    f"There is an obstacle blocking {last_dir}. "
                    f"Try a DIFFERENT direction to go around it."
                )
            else:
                parts.append(
                    "\nSTUCK! You have not moved for 3+ turns. "
                    "Try a different direction."
                )

        # Repeated action detection
        if len(self.recent_actions) >= 4:
            last_4 = self.recent_actions[-4:]
            if len(set(last_4)) == 1:
                parts.append(
                    f"\nSTOP pressing {last_4[0]}! It is not working. "
                    "You are blocked. Press a DIFFERENT direction."
                )

        # Save reminder
        if self.loop_count > 0 and self.loop_count % settings.SAVE_REMINDER_INTERVAL == 0:
            parts.append(
                "\nREMINDER: Save the game! Press START > SAVE > A > A"
            )

        # Goal tree review
        if self.loop_count % settings.PLANNING_REVIEW_INTERVAL == 0 and self.loop_count > 0:
            parts.append(f"\nGoal Tree:\n{self.planner.get_goal_tree_text()}")

        return "\n".join(parts) if parts else ""

    def _push_dashboard(self, game_state, analysis, tick_start, screenshot_b64=None):
        """Push current state to PostgreSQL for the live dashboard."""
        try:
            latency_ms = int((time.time() - tick_start) * 1000)

            feed_data = {
                "tick": self.loop_count,
                "timestamp": datetime.now().isoformat(),
                "latency_ms": latency_ms,
                "model": settings.MODEL,
                "game_phase": analysis.get("game_phase", "unknown"),
                "observation": analysis.get("observation", ""),
                "reasoning": analysis.get("reasoning", ""),
                "action": analysis.get("action", ""),
                "action_detail": analysis.get("action_detail", ""),
                "next_plan": analysis.get("next_plan", ""),
                "uptime": self._uptime(),
                "errors": self.consecutive_errors,
                "total_memories": self.memory.total_memories,
                "game_state": game_state.to_dict(),
                "player_stats": self.stats.to_dict(),
                "battle_stats": self.battle.to_dict(),
                "goals": self.planner.get_goals_snapshot(),
            }

            if screenshot_b64:
                feed_data["screenshot"] = screenshot_b64

            push_live_feed(feed_data)
        except Exception as e:
            logger.debug(f"Failed to push dashboard: {e}")

    def _uptime(self):
        if not self.start_time:
            return "0s"
        elapsed = int(time.time() - self.start_time)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def _shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down Pokemon AI Agent...")
        self.memory.add(
            f"Agent shutting down after {self.loop_count} ticks. Uptime: {self._uptime()}",
            MemoryType.GENERAL,
            metadata={"event": "shutdown", "ticks": self.loop_count},
        )

        if self.session_id:
            end_session(
                self.session_id,
                ticks=self.loop_count,
                badges=self.stats.badges_earned,
                pokemon_caught=self.stats.pokemon_caught,
                whiteouts=self.stats.whiteouts,
            )

        if self.overlay:
            self.overlay.shutdown()

        logger.info(f"Session stats: {self.loop_count} ticks, {self.memory.total_memories} memories")
        logger.info("Goodbye!")


# ── Map info for navigation context ─────────────

_MAP_INFO = {
    0: "Pallet Town. NO Pokemon Center. Go UP to Route 1 to reach Viridian City.",
    1: "Viridian City. Route 1 is SOUTH, Viridian Forest is NORTH.",
    2: "Pewter City. Brock's Gym is upper area. Route 3 is EAST.",
    3: "Cerulean City. Misty's Gym upper-left. Route 5 SOUTH, Route 24 (Nugget Bridge) NORTH.",
    4: "Lavender Town. Pokemon Tower is EAST. Route 8 WEST.",
    5: "Vermilion City. Lt. Surge's Gym bottom area (need CUT). S.S. Anne SOUTH.",
    6: "Celadon City. Dept Store center. Erika's Gym lower-left.",
    7: "Fuchsia City. Koga's Gym lower-left. Safari Zone NORTH.",
    8: "Cinnabar Island. Blaine's Gym upper area. Pokemon Mansion upper-left.",
    9: "Indigo Plateau. Elite Four ahead. Heal fully first!",
    10: "Saffron City. Sabrina's Gym east-center. Silph Co. center.",
    11: "Route 1. Viridian City is NORTH (UP). Pallet Town is SOUTH.",
    12: "Route 2. Pewter City is NORTH. Viridian City is SOUTH.",
    13: "Route 3. Mt. Moon is EAST. Pewter City is WEST.",
    14: "Route 4. Cerulean City is EAST.",
    15: "Route 5. Saffron City SOUTH. Cerulean City NORTH.",
    16: "Route 6. Vermilion City SOUTH. Saffron City NORTH.",
    24: "Route 24 (Nugget Bridge). Goes NORTH from Cerulean City.",
    25: "Route 25. Bill's house is at the far EAST end.",
}
