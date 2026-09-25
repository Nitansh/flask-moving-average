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
    def get_strategy_counts():
        """Returns the number of active positions under TRANCHE_AVERAGING and ONE_SHOT."""
        positions = get_open_positions()
        tranche_count = sum(1 for p in positions if p.get("strategy_type", "TRANCHE_AVERAGING") == "TRANCHE_AVERAGING")
        one_shot_count = sum(1 for p in positions if p.get("strategy_type") == "ONE_SHOT")
        return tranche_count, one_shot_count

    @staticmethod
    def determine_next_strategy():
        """
        Determines whether the next entry should use TRANCHE_AVERAGING or ONE_SHOT.
        Maintains a 50/50 balance (max 4 TRANCHE, max 4 ONE_SHOT out of 8 total).
        """
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))
        max_positions = int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS))
        positions = get_open_positions()

        if len(positions) >= max_positions:
            return None, f"Maximum stock buckets reached ({len(positions)}/{max_positions})"

        tranche_count, one_shot_count = RiskManager.get_strategy_counts()
        bucket_size = RiskManager.get_bucket_size()
        tranche_size = RiskManager.get_tranche_size()

        # Pure One-Shot mode (no tranche averaging)
        if not getattr(BotConfig, "AB_TEST_ENABLED", True) or getattr(BotConfig, "MAX_TRANCHE_POSITIONS", 0) == 0:
            max_os = getattr(BotConfig, "MAX_ONE_SHOT_POSITIONS", max_positions)
            if one_shot_count >= max_os:
                return None, f"Maximum One-Shot positions reached ({one_shot_count}/{max_os})"
            if available_cash < (bucket_size * 0.4):
                return None, f"Insufficient cash for One-Shot entry (Available: ₹{available_cash:.2f})"
            return "ONE_SHOT", "OK"

        max_tranche_slots = getattr(BotConfig, "MAX_TRANCHE_POSITIONS", 4)
        max_one_shot_slots = getattr(BotConfig, "MAX_ONE_SHOT_POSITIONS", 4)

        can_do_tranche = (tranche_count < max_tranche_slots) and (available_cash >= tranche_size * 0.5)
        can_do_one_shot = (one_shot_count < max_one_shot_slots) and (available_cash >= bucket_size * 0.4)

        if not can_do_tranche and not can_do_one_shot:
            return None, "No available slots or insufficient cash for both strategies"

        # Balance strategies: pick whichever has fewer active positions
        if can_do_tranche and can_do_one_shot:
            if one_shot_count < tranche_count:
                return "ONE_SHOT", "OK"
            return "TRANCHE_AVERAGING", "OK"
        elif can_do_tranche:
            return "TRANCHE_AVERAGING", "OK"
        else:
            return "ONE_SHOT", "OK"

    @staticmethod
    def can_open_new_position(strategy_type=None):
        """Checks if capital and slot limits allow opening a new trade."""
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))
        max_positions = int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS))
        open_positions = get_open_positions()

        if len(open_positions) >= max_positions:
            return False, f"Maximum stock buckets reached ({len(open_positions)}/{max_positions})"

        if strategy_type:
            tranche_count, one_shot_count = RiskManager.get_strategy_counts()
            if strategy_type == "ONE_SHOT":
                max_os = getattr(BotConfig, "MAX_ONE_SHOT_POSITIONS", max_positions)
                if one_shot_count >= max_os:
                    return False, f"Maximum One-Shot positions reached ({one_shot_count}/{max_os})"
                bucket_size = RiskManager.get_bucket_size()
                if available_cash < (bucket_size * 0.4):
                    return False, f"Insufficient cash for One-Shot entry (Available: ₹{available_cash:.2f}, Needed: ~₹{bucket_size * 0.4:.2f})"
                return True, "OK"
            else:
                max_tr = getattr(BotConfig, "MAX_TRANCHE_POSITIONS", 0)
                if not getattr(BotConfig, "AB_TEST_ENABLED", True) or max_tr == 0:
                    return False, "Tranche Averaging strategy is disabled in current config"
                if tranche_count >= max_tr:
                    return False, f"Maximum Tranche Averaging positions reached ({tranche_count}/{max_tr})"
                tranche_size = RiskManager.get_tranche_size()
                if available_cash < (tranche_size * 0.5):
                    return False, f"Insufficient cash for Tranche entry (Available: ₹{available_cash:.2f})"
                return True, "OK"

        strat, reason = RiskManager.determine_next_strategy()
        return (strat is not None), reason

    @staticmethod
    def can_add_tranche(position):
        """Checks if an existing stock position can accept another tranche."""
        # ONE_SHOT positions are lump-sum and never scaled into; also reject if MAX_TRANCHES_PER_STOCK <= 1
        if position.get("strategy_type") == "ONE_SHOT" or getattr(BotConfig, "MAX_TRANCHES_PER_STOCK", 1) <= 1:
            return False, "One-Shot strategy does not allow additional averaging tranches"

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
    def calculate_position_size(price, strategy_type=None):
        """Calculates initial entry size based on strategy type (One-Shot ₹1.0L vs Tranche)."""
        if price <= 0:
            return 0
        state = get_bot_state()
        available_cash = float(state.get("available_cash", 0.0))
        strat = strategy_type or getattr(BotConfig, "STRATEGY_MODE", "ONE_SHOT")

        if strat == "ONE_SHOT":
            budget = min(RiskManager.get_bucket_size(), available_cash)
            return int(budget // price)
        else:
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
