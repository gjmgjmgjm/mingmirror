"""Qi Zheng Si Yu (七政四余) analysis subsystem.

This package provides a DeepSeek-compatible LLM analyzer for classical Chinese
Qi Zheng Si Yu astrology. The recommended entry point is a birth datetime plus
geographic coordinates; the engine computes the real astronomical profile
(seven governors, four remainders, ascendant, houses, and 28 lunar mansions)
via `pyswisseph` and feeds those facts into the prompts. A traditional
four-pillar string is still accepted for backward compatibility.

The 28-lunar-mansion mapping supports both tropical and sidereal modes
(Lahiri, Fagan-Bradley, Raman, De Luce) via the ``precession_mode`` parameter.

Optional dependency:
    pip install -r requirements-qizheng.txt
"""

from tools.qizheng.engine import QiZhengAnalyzer

__all__ = ["QiZhengAnalyzer"]
