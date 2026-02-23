"""
LLM Vision Engine for Pokemon FireRed.
Sends screenshots to Gemini 2.0 Flash via OpenRouter and parses action decisions.
"""

import json
import logging

import openai

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Pokemon FireRed player AI. You control the game by choosing ONE button press per turn based on what you see on screen.

Goal: Complete Pokemon FireRed. Beat all 8 gym leaders and the Elite Four.

CURRENT GAME STATE (from memory):
{game_state}

CURRENT GOAL:
{current_goal}

RECENT MEMORIES:
{memories}

RECENT ACTIONS (last 5):
{recent_actions}

CONTROLS:
- A = confirm/interact/select move in battle
- B = cancel/back/run from battle
- START = open menu
- UP/DOWN/LEFT/RIGHT = move character or navigate menus
- WAIT = do nothing (ONLY when screen is completely black)
- When you see ANY text on screen, press A to advance it. NEVER press WAIT if there is text.

GAME PHASES:
- "overworld" = walking around, can see the player character on the map
- "battle" = battle screen with Pokemon sprites and HP bars
- "dialogue" = text box on screen, NPC or system message
- "menu" = start menu, bag, party, pokedex, save screen
- "title" = title screen or save file select
- "transition" = screen fading/loading between areas, just wait

OVERWORLD MOVEMENT:
- Look at the screenshot carefully. Identify where your character is and where you need to go.
- Press UP/DOWN/LEFT/RIGHT to walk in that direction.
- Buildings have doors on their south side. Walk UP into a door to enter.
- To leave a building: walk DOWN to the exit mat.
- Avoid walking into walls, trees, fences, or water.
- If you are stuck (same position for multiple turns), try a DIFFERENT direction to go around the obstacle.
- Save periodically (START > SAVE > A > A) every ~50 actions.

POKEMON CENTER RULES (IMPORTANT):
- If you are INSIDE a Pokemon Center, you are there to HEAL. Do NOT leave until you have healed.
- Walk UP toward the nurse at the counter (she is at the top center of the room).
- Press A to talk to her, then press A through ALL dialogue until healing is complete.
- ONLY leave the Pokemon Center AFTER your Pokemon have been healed.
- Do NOT exit the Pokemon Center without healing first.

END OF BATTLE:
- When a Pokemon faints or you win a battle, PRESS A repeatedly to advance through ALL text.
- "X fainted!", XP gained, level up, new move — press A through ALL of it until you are back in the overworld.
- NEVER press WAIT during battle results. ALWAYS press A.

BATTLE STRATEGY:
- Use type advantages! Water beats Fire, Fire beats Grass, Grass beats Water, etc.
- Use STAB moves (Same Type Attack Bonus) when possible.
- ALWAYS prefer your strongest attacking move.
- The move menu is a 2x2 grid: top-left, top-right, bottom-left, bottom-right.
- Cursor starts at top-left. Press DOWN to go to bottom row, RIGHT to go to right column.
- Navigate to the best move BEFORE pressing A.
- If HP is critically low: use a Potion from bag or switch Pokemon.
- To run from wild battles: press RIGHT to select RUN, then A.

HEALING:
- Heal at Pokemon Centers when HP is below 50%.
- Do NOT keep fighting with low HP. Go heal FIRST, then come back.

Respond in EXACT JSON (no markdown, no code blocks, no extra text):
{{"game_phase": "overworld|battle|dialogue|menu|title|transition", "observation": "Be SPECIFIC. Describe exactly what you see: name the building, NPCs, Pokemon, items, terrain. Not 'a building' but 'the Pokemon Center in Cerulean City'. Not 'a person' but 'Nurse Joy behind the counter'.", "reasoning": "Explain your thinking like a streamer narrating gameplay. WHY this action? What is your plan? Example: 'My Pokemon are hurt from the battle with Misty, so I need to heal at the nurse counter before heading to Route 5.'", "action": "A|B|START|SELECT|UP|DOWN|LEFT|RIGHT|WAIT", "action_detail": "what this action does", "next_plan": "what to do after this", "save_memory": "important info to remember or null", "goal_update": "complete|fail|progress|null"}}"""


class VisionEngine:
    """Sends screenshots to Gemini 2.0 Flash and parses action decisions."""

    def __init__(self):
        self.client = openai.OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
        )
        self.conversation_history = []
        self.max_history = 10
        logger.info("Vision engine initialized (Gemini 2.0 Flash via OpenRouter)")

    def analyze(self, screenshot_b64, game_state_text="", current_goal="",
                memories="", recent_actions="", extra_context=""):
        """
        Send screenshot to LLM for analysis.
        Returns parsed JSON dict with game_phase, observation, reasoning, action, etc.
        """
        system = SYSTEM_PROMPT.format(
            game_state=game_state_text or "No game state available",
            current_goal=current_goal or "Explore and progress through the game",
            memories=memories or "No memories yet",
            recent_actions=recent_actions or "None",
        )

        if extra_context:
            system += f"\n\nADDITIONAL CONTEXT:\n{extra_context}"

        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{screenshot_b64}",
                },
            },
            {
                "type": "text",
                "text": "Analyze this Pokemon FireRed screenshot and decide what button to press next. Respond with JSON only.",
            },
        ]

        try:
            response = self.client.chat.completions.create(
                model=settings.MODEL,
                max_tokens=settings.LLM_MAX_TOKENS,
                temperature=settings.LLM_TEMPERATURE,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )

            raw = response.choices[0].message.content
            parsed = self._parse_response(raw)

            # Track history
            self.conversation_history.append({
                "observation": parsed.get("observation", "")[:100],
                "action": parsed.get("action", ""),
                "phase": parsed.get("game_phase", ""),
            })
            if len(self.conversation_history) > self.max_history:
                self.conversation_history = self.conversation_history[-self.max_history:]

            return parsed

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return {
                "game_phase": "unknown",
                "observation": f"LLM call failed: {str(e)[:80]}",
                "reasoning": "Error occurred, pressing A as fallback",
                "action": "A",
                "action_detail": "Fallback action due to error",
                "next_plan": "Retry next tick",
                "save_memory": None,
                "goal_update": None,
            }

    def _parse_response(self, response):
        """Parse LLM response into structured dict. Handles code block wrapping."""
        response = response.strip()

        # Strip markdown code blocks (Gemini sometimes wraps in ```)
        if "```json" in response:
            try:
                start = response.index("```json") + 7
                end = response.index("```", start)
                response = response[start:end].strip()
            except ValueError:
                response = response.split("```json", 1)[1].strip().rstrip("`")
        elif "```" in response:
            try:
                start = response.index("```") + 3
                end = response.index("```", start)
                response = response[start:end].strip()
            except ValueError:
                response = response.split("```", 1)[1].strip().rstrip("`")

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse LLM response: {response[:150]}")
                    data = self._fallback_response(response)
            else:
                data = self._fallback_response(response)

        # Ensure required fields
        data.setdefault("game_phase", "unknown")
        data.setdefault("observation", "")
        data.setdefault("reasoning", "")
        data.setdefault("action", "A")
        data.setdefault("action_detail", "")
        data.setdefault("next_plan", "")
        data.setdefault("save_memory", None)
        data.setdefault("goal_update", None)

        # Validate action
        data["action"] = data["action"].upper()
        valid_buttons = {"A", "B", "START", "SELECT", "UP", "DOWN", "LEFT", "RIGHT", "WAIT"}
        if data["action"] not in valid_buttons:
            logger.warning(f"Invalid action '{data['action']}', defaulting to A")
            data["action"] = "A"

        return data

    def _fallback_response(self, raw_text):
        return {
            "game_phase": "unknown",
            "observation": raw_text[:150] if raw_text else "No response",
            "reasoning": "Could not parse LLM response",
            "action": "A",
            "action_detail": "Fallback: press A",
            "next_plan": "Retry analysis next tick",
            "save_memory": None,
            "goal_update": None,
        }

    def get_recent_actions_text(self):
        """Format recent action history for the LLM prompt."""
        if not self.conversation_history:
            return "None"
        lines = []
        for entry in self.conversation_history[-5:]:
            lines.append(
                f"[{entry['phase']}] {entry['action']}: {entry['observation']}"
            )
        return "\n".join(lines)
