"""
Battle phase logic and tracking.
Detects battle state transitions, tracks battle statistics,
and provides battle context to the LLM using type effectiveness data.
"""

import json
import logging

from config import settings

logger = logging.getLogger(__name__)

# Pokemon species -> type(s) mapping for Gen 1 (FireRed encounters)
# Only includes Pokemon commonly encountered in FireRed
SPECIES_TYPES = {
    "Bulbasaur": ["Grass", "Poison"], "Ivysaur": ["Grass", "Poison"], "Venusaur": ["Grass", "Poison"],
    "Charmander": ["Fire"], "Charmeleon": ["Fire"], "Charizard": ["Fire", "Flying"],
    "Squirtle": ["Water"], "Wartortle": ["Water"], "Blastoise": ["Water"],
    "Caterpie": ["Bug"], "Metapod": ["Bug"], "Butterfree": ["Bug", "Flying"],
    "Weedle": ["Bug", "Poison"], "Kakuna": ["Bug", "Poison"], "Beedrill": ["Bug", "Poison"],
    "Pidgey": ["Normal", "Flying"], "Pidgeotto": ["Normal", "Flying"], "Pidgeot": ["Normal", "Flying"],
    "Rattata": ["Normal"], "Raticate": ["Normal"],
    "Spearow": ["Normal", "Flying"], "Fearow": ["Normal", "Flying"],
    "Ekans": ["Poison"], "Arbok": ["Poison"],
    "Pikachu": ["Electric"], "Raichu": ["Electric"],
    "Sandshrew": ["Ground"], "Sandslash": ["Ground"],
    "Nidoran-F": ["Poison"], "Nidorina": ["Poison"], "Nidoqueen": ["Poison", "Ground"],
    "Nidoran-M": ["Poison"], "Nidorino": ["Poison"], "Nidoking": ["Poison", "Ground"],
    "Clefairy": ["Normal"], "Clefable": ["Normal"],
    "Vulpix": ["Fire"], "Ninetales": ["Fire"],
    "Jigglypuff": ["Normal"], "Wigglytuff": ["Normal"],
    "Zubat": ["Poison", "Flying"], "Golbat": ["Poison", "Flying"],
    "Oddish": ["Grass", "Poison"], "Gloom": ["Grass", "Poison"], "Vileplume": ["Grass", "Poison"],
    "Paras": ["Bug", "Grass"], "Parasect": ["Bug", "Grass"],
    "Venonat": ["Bug", "Poison"], "Venomoth": ["Bug", "Poison"],
    "Diglett": ["Ground"], "Dugtrio": ["Ground"],
    "Meowth": ["Normal"], "Persian": ["Normal"],
    "Psyduck": ["Water"], "Golduck": ["Water"],
    "Mankey": ["Fighting"], "Primeape": ["Fighting"],
    "Growlithe": ["Fire"], "Arcanine": ["Fire"],
    "Poliwag": ["Water"], "Poliwhirl": ["Water"], "Poliwrath": ["Water", "Fighting"],
    "Abra": ["Psychic"], "Kadabra": ["Psychic"], "Alakazam": ["Psychic"],
    "Machop": ["Fighting"], "Machoke": ["Fighting"], "Machamp": ["Fighting"],
    "Bellsprout": ["Grass", "Poison"], "Weepinbell": ["Grass", "Poison"], "Victreebel": ["Grass", "Poison"],
    "Tentacool": ["Water", "Poison"], "Tentacruel": ["Water", "Poison"],
    "Geodude": ["Rock", "Ground"], "Graveler": ["Rock", "Ground"], "Golem": ["Rock", "Ground"],
    "Ponyta": ["Fire"], "Rapidash": ["Fire"],
    "Slowpoke": ["Water", "Psychic"], "Slowbro": ["Water", "Psychic"],
    "Magnemite": ["Electric", "Steel"], "Magneton": ["Electric", "Steel"],
    "Farfetch'd": ["Normal", "Flying"],
    "Doduo": ["Normal", "Flying"], "Dodrio": ["Normal", "Flying"],
    "Seel": ["Water"], "Dewgong": ["Water", "Ice"],
    "Grimer": ["Poison"], "Muk": ["Poison"],
    "Shellder": ["Water"], "Cloyster": ["Water", "Ice"],
    "Gastly": ["Ghost", "Poison"], "Haunter": ["Ghost", "Poison"], "Gengar": ["Ghost", "Poison"],
    "Onix": ["Rock", "Ground"],
    "Drowzee": ["Psychic"], "Hypno": ["Psychic"],
    "Krabby": ["Water"], "Kingler": ["Water"],
    "Voltorb": ["Electric"], "Electrode": ["Electric"],
    "Exeggcute": ["Grass", "Psychic"], "Exeggutor": ["Grass", "Psychic"],
    "Cubone": ["Ground"], "Marowak": ["Ground"],
    "Hitmonlee": ["Fighting"], "Hitmonchan": ["Fighting"],
    "Lickitung": ["Normal"],
    "Koffing": ["Poison"], "Weezing": ["Poison"],
    "Rhyhorn": ["Ground", "Rock"], "Rhydon": ["Ground", "Rock"],
    "Chansey": ["Normal"], "Tangela": ["Grass"], "Kangaskhan": ["Normal"],
    "Horsea": ["Water"], "Seadra": ["Water"],
    "Goldeen": ["Water"], "Seaking": ["Water"],
    "Staryu": ["Water"], "Starmie": ["Water", "Psychic"],
    "Mr. Mime": ["Psychic"], "Scyther": ["Bug", "Flying"],
    "Jynx": ["Ice", "Psychic"], "Electabuzz": ["Electric"], "Magmar": ["Fire"],
    "Pinsir": ["Bug"], "Tauros": ["Normal"],
    "Magikarp": ["Water"], "Gyarados": ["Water", "Flying"],
    "Lapras": ["Water", "Ice"], "Ditto": ["Normal"],
    "Eevee": ["Normal"], "Vaporeon": ["Water"], "Jolteon": ["Electric"], "Flareon": ["Fire"],
    "Porygon": ["Normal"],
    "Omanyte": ["Rock", "Water"], "Omastar": ["Rock", "Water"],
    "Kabuto": ["Rock", "Water"], "Kabutops": ["Rock", "Water"],
    "Aerodactyl": ["Rock", "Flying"], "Snorlax": ["Normal"],
    "Articuno": ["Ice", "Flying"], "Zapdos": ["Electric", "Flying"], "Moltres": ["Fire", "Flying"],
    "Dratini": ["Dragon"], "Dragonair": ["Dragon"], "Dragonite": ["Dragon", "Flying"],
    "Mewtwo": ["Psychic"], "Mew": ["Psychic"],
}

# Move name -> type mapping for common moves
MOVE_TYPES = {
    "Tackle": "Normal", "Scratch": "Normal", "Pound": "Normal", "Slam": "Normal",
    "Body Slam": "Normal", "Take Down": "Normal", "Double-Edge": "Normal",
    "Hyper Beam": "Normal", "Quick Attack": "Normal", "Slash": "Normal",
    "Headbutt": "Normal", "Strength": "Normal", "Cut": "Normal", "Swift": "Normal",
    "Ember": "Fire", "Flamethrower": "Fire", "Fire Blast": "Fire", "Fire Punch": "Fire",
    "Fire Spin": "Fire", "Flame Wheel": "Fire",
    "Water Gun": "Water", "Surf": "Water", "Hydro Pump": "Water", "Bubble": "Water",
    "Bubble Beam": "Water", "Waterfall": "Water", "Water Pulse": "Water",
    "Thunder Shock": "Electric", "Thunderbolt": "Electric", "Thunder": "Electric",
    "Thunder Punch": "Electric", "Thunder Wave": "Electric", "Spark": "Electric",
    "Vine Whip": "Grass", "Razor Leaf": "Grass", "Solar Beam": "Grass",
    "Mega Drain": "Grass", "Giga Drain": "Grass", "Absorb": "Grass", "Leech Seed": "Grass",
    "Bullet Seed": "Grass", "Leaf Blade": "Grass",
    "Ice Beam": "Ice", "Blizzard": "Ice", "Ice Punch": "Ice", "Aurora Beam": "Ice",
    "Powder Snow": "Ice", "Icy Wind": "Ice",
    "Karate Chop": "Fighting", "Low Kick": "Fighting", "Submission": "Fighting",
    "Seismic Toss": "Fighting", "Cross Chop": "Fighting", "Brick Break": "Fighting",
    "Mach Punch": "Fighting", "Dynamic Punch": "Fighting",
    "Poison Sting": "Poison", "Sludge": "Poison", "Sludge Bomb": "Poison",
    "Toxic": "Poison", "Acid": "Poison", "Poison Powder": "Poison",
    "Earthquake": "Ground", "Dig": "Ground", "Mud-Slap": "Ground",
    "Bone Club": "Ground", "Bonemerang": "Ground", "Mud Shot": "Ground",
    "Gust": "Flying", "Wing Attack": "Flying", "Fly": "Flying", "Drill Peck": "Flying",
    "Peck": "Flying", "Aerial Ace": "Flying", "Sky Attack": "Flying",
    "Confusion": "Psychic", "Psychic": "Psychic", "Psybeam": "Psychic",
    "Hypnosis": "Psychic", "Dream Eater": "Psychic", "Extrasensory": "Psychic",
    "Leech Life": "Bug", "Pin Missile": "Bug", "Twineedle": "Bug",
    "Signal Beam": "Bug", "Silver Wind": "Bug",
    "Rock Throw": "Rock", "Rock Slide": "Rock", "Rock Tomb": "Rock",
    "Ancient Power": "Rock", "Rock Blast": "Rock",
    "Lick": "Ghost", "Shadow Ball": "Ghost", "Night Shade": "Ghost",
    "Shadow Punch": "Ghost", "Astonish": "Ghost",
    "Dragon Rage": "Dragon", "Dragon Breath": "Dragon", "Dragon Claw": "Dragon",
    "Outrage": "Dragon", "Twister": "Dragon",
    "Bite": "Dark", "Crunch": "Dark", "Pursuit": "Dark", "Thief": "Dark",
    "Faint Attack": "Dark",
    "Steel Wing": "Steel", "Iron Tail": "Steel", "Metal Claw": "Steel",
    "Meteor Mash": "Steel", "Iron Defense": "Steel",
}


class BattleManager:
    """Tracks battle state transitions and provides battle context."""

    def __init__(self):
        self.in_battle = False
        self.battle_type = 0  # 0=none, 1=wild, 2=trainer
        self.battle_turns = 0
        self.battles_won = 0
        self.battles_fled = 0
        self.whiteouts = 0
        self.prev_money = 0
        self.prev_party_hp = []
        self.type_chart = self._load_type_chart()

    def _load_type_chart(self):
        """Load the type effectiveness chart from data/type_chart.json."""
        try:
            with open(settings.TYPE_CHART_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load type chart: {e}")
            return {}

    def update(self, game_state):
        """
        Update battle tracking from the current game state.
        Returns a dict with battle event info (if any transition occurred).
        """
        new_battle = game_state.in_battle
        events = {}

        if not self.in_battle and new_battle > 0:
            # Battle started
            self.in_battle = True
            self.battle_type = new_battle
            self.battle_turns = 0
            self.prev_party_hp = [
                (p.get("hp_current", 0), p.get("hp_max", 0))
                for p in game_state.party
            ]
            self.prev_money = game_state.money
            events["battle_start"] = "wild" if new_battle == 1 else "trainer"
            logger.info(f"Battle started: {'wild' if new_battle == 1 else 'trainer'}")

        elif self.in_battle and new_battle == 0:
            # Battle ended
            self.in_battle = False
            all_fainted = all(
                p.get("hp_current", 0) == 0 for p in game_state.party
            ) if game_state.party else False

            if all_fainted or game_state.money < self.prev_money:
                self.whiteouts += 1
                events["battle_end"] = "whiteout"
                logger.info("Battle ended: WHITEOUT")
            else:
                self.battles_won += 1
                events["battle_end"] = "won"
                logger.info(f"Battle ended: WON (total: {self.battles_won})")

            self.battle_type = 0

        elif self.in_battle:
            self.battle_turns += 1

        return events

    def get_battle_context(self, game_state):
        """
        Build battle context string for the LLM.
        Includes type matchup recommendations.
        """
        if not self.in_battle:
            return ""

        parts = []
        battle_label = "WILD" if self.battle_type == 1 else "TRAINER"
        parts.append(f"IN BATTLE ({battle_label}) - Turn {self.battle_turns}")

        # Recommend moves based on party's available moves
        if game_state.party:
            parts.append("\nYour team:")
            for i, pkmn in enumerate(game_state.party):
                name = pkmn.get("species_name", "Unknown")
                hp = pkmn.get("hp_current", 0)
                hp_max = pkmn.get("hp_max", 1)
                moves = pkmn.get("moves", [])
                hp_pct = int(100 * hp / hp_max) if hp_max > 0 else 0
                parts.append(f"  {i+1}. {name} HP:{hp}/{hp_max} ({hp_pct}%) Moves: {', '.join(moves)}")

        if self.battle_turns > 25:
            parts.append("\nWARNING: This battle is dragging on. Consider using stronger moves or running.")

        return "\n".join(parts)

    def get_type_effectiveness(self, attack_type, defend_types):
        """Calculate type effectiveness multiplier."""
        if not self.type_chart or not attack_type:
            return 1.0

        multiplier = 1.0
        matchups = self.type_chart.get(attack_type, {})
        for dtype in defend_types:
            if dtype in matchups:
                multiplier *= matchups[dtype]

        return multiplier

    def recommend_move(self, party_pokemon, enemy_name):
        """Recommend the best move against an enemy based on type chart."""
        enemy_types = SPECIES_TYPES.get(enemy_name, [])
        if not enemy_types:
            return None

        best_move = None
        best_effectiveness = 0

        moves = party_pokemon.get("moves", [])
        for move_name in moves:
            if not move_name or move_name == "---":
                continue
            move_type = MOVE_TYPES.get(move_name)
            if not move_type:
                continue

            effectiveness = self.get_type_effectiveness(move_type, enemy_types)
            if effectiveness > best_effectiveness:
                best_effectiveness = effectiveness
                best_move = move_name

        if best_move and best_effectiveness > 1.0:
            return f"Use {best_move} (super effective x{best_effectiveness}!)"
        return None

    def to_dict(self):
        """Serialize battle stats for dashboard."""
        return {
            "in_battle": self.in_battle,
            "battle_type": self.battle_type,
            "battle_turns": self.battle_turns,
            "battles_won": self.battles_won,
            "battles_fled": self.battles_fled,
            "whiteouts": self.whiteouts,
        }
