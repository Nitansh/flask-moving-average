"""
Auto-Trader Submodule
Provides autonomous trading capabilities using Kite Connect and the DEMA Stage-Rider Strategy.
"""
from .config import BotConfig
from .bot_runner import bot_runner
from .db import init_db

__all__ = ["BotConfig", "bot_runner", "init_db"]
