"""Multi-destiny agent strategies."""

from tools.destiny.strategies.debate import DebateStrategy
from tools.destiny.strategies.reflection import ReflectionStrategy
from tools.destiny.strategies.retriever import DestinyRetriever
from tools.destiny.strategies.tool_caller import ToolCaller

__all__ = ["DebateStrategy", "DestinyRetriever", "ReflectionStrategy", "ToolCaller"]
