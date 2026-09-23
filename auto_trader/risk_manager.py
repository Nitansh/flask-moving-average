"""
Risk Manager for Auto-Trader
Manages capital allocation, position sizing, max positions, and daily drawdown limits.
"""
from .config import BotConfig
from .db import get_bot_state, update_bot_state, get_open_positions, log_event

class RiskManager:
    def __init__(self):
        pass

    @staticmethod
    def get_allocation_per_slot():
        """Calculates maximum capital allocated per stock position."""
        state = get_bot_state()
        total_capital = float(state.get("total_capital", BotConfig.INITIAL_CAPITAL))
        max_positions = int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS))
        if max_positions <= 0:
            max_positions = 2
        return total_capital / max_positions

    @staticmethod
    def can_open_new_position():
        """Checks if capital and slot limits allow opening a new trade."""
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))
        max_positions = int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS))
        open_positions = get_open_positions()

        if len(open_positions) >= max_positions:
            return False, f"Maximum positions reached ({len(open_positions)}/{max_positions})"

        slot_size = RiskManager.get_allocation_per_slot()
        if available_cash < (slot_size * 0.75):
            return False, f"Insufficient cash (Available: ₹{available_cash:.2f}, Required: ~₹{slot_size:.2f})"

        return True, "OK"

    @staticmethod
    def calculate_position_size(price):
        """Calculates quantity of shares to purchase based on slot size."""
        if price <= 0:
            return 0
        slot_size = RiskManager.get_allocation_per_slot()
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))

        effective_budget = min(slot_size, available_cash)
        qty = int(effective_budget // price)
        return qty

    @staticmethod
    def check_daily_drawdown():
        """
        Circuit Breaker: Checks if total realized + unrealized loss exceeds MAX_DAILY_LOSS_PCT.
        Returns True if safe, False if trading must be halted.
        """
        state = get_bot_state()
        total_capital = float(state.get("total_capital", BotConfig.INITIAL_CAPITAL))
        max_loss = total_capital * (BotConfig.MAX_DAILY_LOSS_PCT / 100.0)

        # Calculate open positions unrealized PnL
        open_positions = get_open_positions()
        unrealized_pnl = sum((p["current_price"] - p["buy_price"]) * p["current_qty"] for p in open_positions)

        if (unrealized_pnl) < -max_loss:
            log_event("WARNING", f"Circuit Breaker Triggered! Unrealized loss ₹{unrealized_pnl:.2f} exceeds limit ₹{-max_loss:.2f}")
            return False
        return True
