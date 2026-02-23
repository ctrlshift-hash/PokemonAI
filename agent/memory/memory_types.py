"""Memory category definitions for ChromaDB storage."""

from enum import Enum


class MemoryType(str, Enum):
    BATTLE = "battle"
    NAVIGATION = "navigation"
    ITEM = "item"
    FAILURE = "failure"
    GENERAL = "general"
    STRATEGY = "strategy"
    LOCATION = "location"
    POKEMON = "pokemon"
