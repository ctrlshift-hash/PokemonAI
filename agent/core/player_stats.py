"""
Player statistics tracker.
Compares consecutive game states from RAM to detect events and track progress.
Unlike ClaudeScape's text-parsing approach, this uses ground-truth RAM data.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PlayerStats:
    """Cumulative player statistics derived from game memory comparisons."""

    # Movement
    steps_taken: int = 0
    _prev_x: int = -1
    _prev_y: int = -1

    # Pokemon
    pokemon_caught: int = 0
    _prev_pokedex_caught: int = 0
    highest_level: int = 0

    # Battle
    battles_won: int = 0
    whiteouts: int = 0

    # Progression
    badges_earned: int = 0
    _prev_badges: int = 0

    # Economy
    _prev_money: int = 0

    # Pokedex
    pokedex_seen: int = 0
    pokedex_caught: int = 0

    # Time
    total_ticks: int = 0

    # Action log for dashboard (last 30)
    action_history: list = field(default_factory=list)

    def update(self, game_state):
        """Update stats by comparing current game state to previous values."""
        self.total_ticks += 1

        # Detect movement (steps)
        if self._prev_x >= 0 and self._prev_y >= 0:
            if game_state.player_x != self._prev_x or game_state.player_y != self._prev_y:
                self.steps_taken += 1
        self._prev_x = game_state.player_x
        self._prev_y = game_state.player_y

        # Detect new Pokemon caught
        if game_state.pokedex_caught > self._prev_pokedex_caught:
            new_catches = game_state.pokedex_caught - self._prev_pokedex_caught
            self.pokemon_caught += new_catches
            logger.info(f"Caught {new_catches} new Pokemon! Total: {self.pokemon_caught}")
        self._prev_pokedex_caught = game_state.pokedex_caught
        self.pokedex_seen = game_state.pokedex_seen
        self.pokedex_caught = game_state.pokedex_caught

        # Track highest level
        for pkmn in game_state.party:
            level = pkmn.get("level", 0)
            if level > self.highest_level:
                self.highest_level = level
                logger.info(f"New highest level: {level}")

        # Detect badge earned
        if game_state.badge_count > self._prev_badges:
            new_badges = game_state.badge_count - self._prev_badges
            self.badges_earned = game_state.badge_count
            logger.info(f"Earned {new_badges} new badge(s)! Total: {self.badges_earned}")
        self._prev_badges = game_state.badge_count

        # Detect whiteout (all party HP=0 and money decreased)
        if game_state.party:
            all_fainted = all(
                p.get("hp_current", 0) == 0 for p in game_state.party
            )
            money_decreased = game_state.money < self._prev_money and self._prev_money > 0
            if all_fainted and money_decreased:
                self.whiteouts += 1
                logger.info(f"WHITEOUT detected! Total: {self.whiteouts}")
        self._prev_money = game_state.money

    def log_action(self, tick, action, observation, game_phase):
        """Record an action for the dashboard timeline."""
        self.action_history.append({
            "tick": tick,
            "action": action,
            "observation": observation[:120],
            "phase": game_phase,
        })
        # Keep last 30
        if len(self.action_history) > 30:
            self.action_history = self.action_history[-30:]

    def to_dict(self):
        """Serialize for the live dashboard."""
        return {
            "steps_taken": self.steps_taken,
            "pokemon_caught": self.pokemon_caught,
            "highest_level": self.highest_level,
            "battles_won": self.battles_won,
            "whiteouts": self.whiteouts,
            "badges_earned": self.badges_earned,
            "pokedex_seen": self.pokedex_seen,
            "pokedex_caught": self.pokedex_caught,
            "total_ticks": self.total_ticks,
            "action_history": self.action_history[-30:],
        }
