"""
Hierarchical goal tree for Pokemon FireRed progression.
Pre-populated with the full game from Pallet Town to Elite Four.
Same architecture as ClaudeScape's goal_planner.py.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

PLANS_FILE = settings.PROJECT_ROOT / "agent" / "planning" / "active_plans.json"


class GoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Goal:
    """A single goal or sub-goal in the planning tree."""
    id: str
    name: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    priority: int = 5
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 10
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "prerequisites": self.prerequisites,
            "notes": self.notes,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data):
        data["status"] = GoalStatus(data["status"])
        return cls(**data)


class GoalPlanner:
    """Manages the hierarchical goal tree for Pokemon FireRed progression."""

    def __init__(self):
        self.goals: dict[str, Goal] = {}
        self._id_counter = 0
        self._load()

    def _next_id(self):
        self._id_counter += 1
        return f"goal_{self._id_counter}"

    # --- Goal CRUD ---

    def add_goal(self, name, description, priority=5, parent_id=None, prerequisites=None):
        """Add a new goal. Returns the goal ID."""
        goal_id = self._next_id()
        goal = Goal(
            id=goal_id,
            name=name,
            description=description,
            priority=priority,
            parent_id=parent_id,
            prerequisites=prerequisites or [],
        )
        self.goals[goal_id] = goal

        if parent_id and parent_id in self.goals:
            self.goals[parent_id].children_ids.append(goal_id)

        self._save()
        return goal_id

    def add_subgoals(self, parent_id, subgoals):
        """Add multiple sequential sub-goals to a parent."""
        ids = []
        prev_id = None
        for sg in subgoals:
            prereqs = sg.get("prerequisites", [])
            if sg.get("sequential") and prev_id:
                prereqs.append(prev_id)
            gid = self.add_goal(
                name=sg["name"],
                description=sg["description"],
                priority=sg.get("priority", 5),
                parent_id=parent_id,
                prerequisites=prereqs,
            )
            ids.append(gid)
            prev_id = gid
        return ids

    def complete_goal(self, goal_id, notes=""):
        """Mark a goal as completed."""
        if goal_id not in self.goals:
            return
        goal = self.goals[goal_id]
        goal.status = GoalStatus.COMPLETED
        goal.completed_at = time.time()
        if notes:
            goal.notes.append(f"Completed: {notes}")

        # Auto-complete parent if all children done
        if goal.parent_id and goal.parent_id in self.goals:
            parent = self.goals[goal.parent_id]
            if all(
                self.goals[cid].status == GoalStatus.COMPLETED
                for cid in parent.children_ids
                if cid in self.goals
            ):
                self.complete_goal(parent.id, "All sub-goals completed")

        self._save()
        logger.info(f"Completed goal: {goal.name}")

    def fail_goal(self, goal_id, reason=""):
        """Mark a goal as failed (resets to pending if retries remain)."""
        if goal_id not in self.goals:
            return
        goal = self.goals[goal_id]
        goal.attempts += 1
        if goal.attempts >= goal.max_attempts:
            goal.status = GoalStatus.FAILED
            goal.notes.append(f"Failed permanently: {reason}")
            logger.warning(f"Goal permanently failed: {goal.name}")
        else:
            goal.status = GoalStatus.PENDING
            goal.notes.append(f"Attempt {goal.attempts} failed: {reason}")
            logger.info(f"Goal attempt failed, will retry: {goal.name}")
        self._save()

    def block_goal(self, goal_id, reason):
        """Mark a goal as blocked."""
        if goal_id in self.goals:
            self.goals[goal_id].status = GoalStatus.BLOCKED
            self.goals[goal_id].notes.append(f"Blocked: {reason}")
            self._save()

    # --- Goal Selection ---

    def get_current_goal(self):
        """Get the currently active/in-progress leaf goal."""
        for goal in self.goals.values():
            if goal.status in (GoalStatus.ACTIVE, GoalStatus.IN_PROGRESS):
                if goal.children_ids:
                    child = self._get_next_child(goal)
                    if child:
                        return child
                return goal
        return self._select_next_goal()

    def _get_next_child(self, parent):
        """Get the next actionable child goal."""
        for cid in parent.children_ids:
            child = self.goals.get(cid)
            if not child:
                continue
            if child.status in (GoalStatus.ACTIVE, GoalStatus.IN_PROGRESS):
                if child.children_ids:
                    deeper = self._get_next_child(child)
                    if deeper:
                        return deeper
                return child
            if child.status == GoalStatus.PENDING and self._prerequisites_met(child):
                child.status = GoalStatus.ACTIVE
                self._save()
                return child
        return None

    def _select_next_goal(self):
        """Select the highest-priority pending goal whose prerequisites are met."""
        candidates = [
            g for g in self.goals.values()
            if g.status == GoalStatus.PENDING
            and not g.parent_id
            and self._prerequisites_met(g)
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda g: g.priority)
        best = candidates[0]
        best.status = GoalStatus.ACTIVE
        self._save()
        return best

    def _prerequisites_met(self, goal):
        """Check if all prerequisites are completed."""
        for prereq_id in goal.prerequisites:
            prereq = self.goals.get(prereq_id)
            if not prereq or prereq.status != GoalStatus.COMPLETED:
                return False
        return True

    # --- Context for LLM ---

    def get_active_goal_context(self):
        """Get a context string about the current goal for the LLM."""
        current = self.get_current_goal()
        if not current:
            return "No active goal. All goals completed or none set."

        parts = [f"Current goal: {current.name}"]
        parts.append(f"Description: {current.description}")
        parts.append(f"Status: {current.status.value}")
        parts.append(f"Attempts: {current.attempts}/{current.max_attempts}")

        if current.notes:
            parts.append(f"Notes: {'; '.join(current.notes[-3:])}")

        # Show parent chain for context
        parent_chain = []
        pid = current.parent_id
        while pid and pid in self.goals:
            parent_chain.append(self.goals[pid].name)
            pid = self.goals[pid].parent_id
        if parent_chain:
            parts.append(f"Part of: {' > '.join(reversed(parent_chain))}")

        return "\n".join(parts)

    def get_goal_tree_text(self):
        """Get a human-readable text representation of the goal tree."""
        lines = []
        top_level = [g for g in self.goals.values() if not g.parent_id]
        top_level.sort(key=lambda g: g.priority)
        for goal in top_level:
            self._render_goal(goal, lines, indent=0)
        return "\n".join(lines) if lines else "No goals set."

    def _render_goal(self, goal, lines, indent):
        status_icons = {
            GoalStatus.PENDING: "[ ]",
            GoalStatus.ACTIVE: "[>]",
            GoalStatus.IN_PROGRESS: "[~]",
            GoalStatus.COMPLETED: "[x]",
            GoalStatus.FAILED: "[!]",
            GoalStatus.BLOCKED: "[-]",
        }
        icon = status_icons.get(goal.status, "[?]")
        prefix = "  " * indent
        lines.append(f"{prefix}{icon} {goal.name} ({goal.status.value})")
        for cid in goal.children_ids:
            child = self.goals.get(cid)
            if child:
                self._render_goal(child, lines, indent + 1)

    def get_goals_snapshot(self):
        """Get simplified goal list for the dashboard."""
        snapshot = []
        for goal in self.goals.values():
            snapshot.append({
                "name": goal.name,
                "status": goal.status.value,
                "parent_id": goal.parent_id,
                "id": goal.id,
            })
        return snapshot

    # --- Persistence ---

    def _save(self):
        """Save goals to disk."""
        PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "counter": self._id_counter,
            "goals": {gid: g.to_dict() for gid, g in self.goals.items()},
        }
        PLANS_FILE.write_text(json.dumps(data, indent=2))

    def _load(self):
        """Load goals from disk."""
        if PLANS_FILE.exists():
            try:
                data = json.loads(PLANS_FILE.read_text())
                self._id_counter = data.get("counter", 0)
                for gid, gdata in data.get("goals", {}).items():
                    self.goals[gid] = Goal.from_dict(gdata)
                logger.info(f"Loaded {len(self.goals)} goals from disk")
            except Exception as e:
                logger.warning(f"Failed to load plans: {e}")

    # --- Pre-populated FireRed Progression ---

    def setup_firered_goals(self):
        """Pre-populate the full Pokemon FireRed progression tree."""
        root = self.add_goal(
            "Beat the Elite Four",
            "Complete Pokemon FireRed by defeating all 8 gym leaders and the Elite Four + Champion",
            priority=1,
        )

        steps = [
            {
                "name": "Pallet Town - Get starter Pokemon",
                "description": "Go downstairs, try to leave town, go to Oak's lab, pick a starter (Charmander/Squirtle/Bulbasaur), win rival battle",
                "sequential": True,
            },
            {
                "name": "Route 1 - Reach Viridian City",
                "description": "Walk north through Route 1 to Viridian City. Battle wild Pokemon to gain XP along the way",
                "sequential": True,
            },
            {
                "name": "Viridian City - Deliver Oak's Parcel",
                "description": "Get Oak's Parcel from the Poke Mart, deliver it to Prof. Oak in Pallet Town, return to Viridian City",
                "sequential": True,
            },
            {
                "name": "Route 2 + Viridian Forest - Reach Pewter City",
                "description": "Go north through Route 2 and Viridian Forest. Train Pokemon to Lv.12+ for Brock. Catch a Pikachu if possible",
                "sequential": True,
            },
            {
                "name": "Pewter City - Beat Brock (Gym 1, Rock)",
                "description": "Challenge Brock's Rock-type gym. Use Water/Grass moves. His ace is Onix Lv.14. Need Lv.12+ to win",
                "sequential": True,
            },
            {
                "name": "Route 3 + Mt. Moon - Reach Cerulean City",
                "description": "Travel through Route 3, Mt. Moon (get fossils), Route 4 to Cerulean City. Train along the way",
                "sequential": True,
            },
            {
                "name": "Cerulean City - Beat Misty (Gym 2, Water)",
                "description": "Challenge Misty's Water-type gym. Use Grass/Electric moves. Her ace is Starmie Lv.21. Need Lv.18+",
                "sequential": True,
            },
            {
                "name": "Route 24/25 - Nugget Bridge + Bill's House",
                "description": "Cross Nugget Bridge (5 trainers + Rocket Grunt), visit Bill's house to get the SS Anne ticket",
                "sequential": True,
            },
            {
                "name": "Routes 5/6 - Reach Vermilion City",
                "description": "Go south through Routes 5 and 6, through the underground path, to Vermilion City",
                "sequential": True,
            },
            {
                "name": "SS Anne - Get HM01 Cut",
                "description": "Board the SS Anne, battle trainers, defeat rival, get HM01 Cut from the captain",
                "sequential": True,
            },
            {
                "name": "Vermilion City - Beat Lt. Surge (Gym 3, Electric)",
                "description": "Use Cut on the tree blocking the gym. Solve the trash can switch puzzle. Beat Lt. Surge's Electric types. Use Ground moves. His ace is Raichu Lv.24",
                "sequential": True,
            },
            {
                "name": "Routes 9/10 + Rock Tunnel - Reach Lavender Town",
                "description": "Travel east through Route 9, Rock Tunnel (need Flash), Route 10 to Lavender Town",
                "sequential": True,
            },
            {
                "name": "Celadon City - Beat Erika (Gym 4, Grass)",
                "description": "Go west to Celadon City. Challenge Erika's Grass-type gym. Use Fire/Flying/Ice moves. Her ace is Vileplume Lv.29",
                "sequential": True,
            },
            {
                "name": "Celadon City - Rocket Game Corner + Silph Scope",
                "description": "Infiltrate the Rocket Game Corner hideout, defeat Giovanni, get the Silph Scope",
                "sequential": True,
            },
            {
                "name": "Lavender Town - Clear Pokemon Tower",
                "description": "Use Silph Scope in Pokemon Tower. Battle Ghost Marowak. Rescue Mr. Fuji. Get the Poke Flute",
                "sequential": True,
            },
            {
                "name": "Saffron City - Clear Silph Co.",
                "description": "Enter Silph Co., navigate floors, defeat Rocket Grunts, battle rival, defeat Giovanni. Get Master Ball",
                "sequential": True,
            },
            {
                "name": "Saffron City - Beat Sabrina (Gym 5, Psychic)",
                "description": "Navigate the teleporter maze gym. Beat Sabrina's Psychic types. Use Bug/Ghost/Dark moves. Her ace is Alakazam Lv.43",
                "sequential": True,
            },
            {
                "name": "Fuchsia City - Beat Koga (Gym 6, Poison)",
                "description": "Travel to Fuchsia City. Beat Koga's Poison-type gym. Use Ground/Psychic moves. His ace is Weezing Lv.43. Get HM03 Surf from Safari Zone",
                "sequential": True,
            },
            {
                "name": "Cinnabar Island - Beat Blaine (Gym 7, Fire)",
                "description": "Surf south to Cinnabar Island. Get Secret Key from Pokemon Mansion. Beat Blaine's Fire types. Use Water/Ground/Rock moves. His ace is Arcanine Lv.47",
                "sequential": True,
            },
            {
                "name": "Viridian City - Beat Giovanni (Gym 8, Ground)",
                "description": "Return to Viridian City gym. Beat Giovanni's Ground types. Use Water/Grass/Ice moves. His ace is Rhyhorn Lv.50",
                "sequential": True,
            },
            {
                "name": "Route 23 + Victory Road",
                "description": "Show all 8 badges at the gate. Navigate Victory Road (strength puzzles). Train team to Lv.50+",
                "sequential": True,
            },
            {
                "name": "Indigo Plateau - Elite Four + Champion",
                "description": "Beat Lorelei (Ice), Bruno (Fighting), Agatha (Ghost), Lance (Dragon), then Champion (rival). Need Lv.55+ team with good type coverage",
                "sequential": True,
            },
        ]

        self.add_subgoals(root, steps)
        logger.info("FireRed progression goals initialized (22 milestones)")
        return root
