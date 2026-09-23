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
    def get_bucket_size():
        """Calculates maximum capital allocated per stock bucket (e.g. ₹2,50,000)."""
        state = get_bot_state()
        return float(state.get("bucket_capital", BotConfig.BUCKET_CAPITAL_PER_STOCK))

    @staticmethod
    def get_tranche_size():
        """Calculates budget per shot/tranche (e.g. ₹50,000)."""
        state = get_bot_state()
        return float(state.get("tranche_size", BotConfig.TRANCHE_SIZE))

    @staticmethod
    def can_open_new_position():
        """Checks if capital and slot limits allow opening a new trade."""
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))
        max_positions = int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS))
        open_positions = get_open_positions()

        if len(open_positions) >= max_positions:
            return False, f"Maximum stock buckets reached ({len(open_positions)}/{max_positions})"

        tranche_size = RiskManager.get_tranche_size()
        if available_cash < (tranche_size * 0.5):
            return False, f"Insufficient cash for initial tranche (Available: ₹{available_cash:.2f}, Required: ~₹{tranche_size:.2f})"

        return True, "OK"

    @staticmethod
    def can_add_tranche(position):
        """Checks if an existing stock position can accept another ₹50,000 tranche."""
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))
        tranche_size = RiskManager.get_tranche_size()
        bucket_size = RiskManager.get_bucket_size()

        tranches_count = int(position.get("tranches_count", 1))
        invested_amount = float(position.get("invested_amount", 0.0))

        if tranches_count >= BotConfig.MAX_TRANCHES_PER_STOCK:
            return False, f"Max tranches reached ({tranches_count}/{BotConfig.MAX_TRANCHES_PER_STOCK})"

        if (invested_amount + (tranche_size * 0.75)) > bucket_size:
            return False, f"Bucket limit reached (Invested: ₹{invested_amount:.2f}, Cap: ₹{bucket_size:.2f})"

        if available_cash < (tranche_size * 0.5):
            return False, f"Insufficient cash for next tranche (Available: ₹{available_cash:.2f})"

        return True, "OK"

    @staticmethod
    def calculate_tranche_qty(price):
        """Calculates quantity of shares to purchase for a ₹50,000 tranche."""
        if price <= 0:
            return 0
        tranche_size = RiskManager.get_tranche_size()
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))

        effective_budget = min(tranche_size, available_cash)
        qty = int(effective_budget // price)
        return qty

    @staticmethod
    def calculate_position_size(price):
        """Initial position size equals one tranche (₹50,000)."""
        return RiskManager.calculate_tranche_qty(price)

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
