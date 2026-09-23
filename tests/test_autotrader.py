"""
Unit Tests for Auto-Trader Submodule (DEMA Stage-Rider with Tranche Averaging)
"""
import pytest
from auto_trader.config import BotConfig
from auto_trader.strategy import StrategyEngine
from auto_trader.risk_manager import RiskManager
from auto_trader.kite_client import KiteTraderClient
from auto_trader.db import init_db, get_bot_state, update_bot_state

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    update_bot_state(
        total_capital=2000000.0,
        available_cash=2000000.0,
        bucket_capital=250000.0,
        tranche_size=50000.0,
        max_positions=8,
        is_running=0
    )

def test_strategy_entry_valid():
    """Stock meeting all criteria should qualify for BUY entry."""
    valid_stock = {
        "symbol": "TRENT",
        "price": 5000.0,
        "DMA_20": 4850.0,
        "DMA_50": 4600.0,
        "DMA_100": 5300.0, # +6.0% headroom to 100 DEMA (>= 4%)
        "rsi": 55.0 # within 48-62 range
    }
    is_valid, reason = StrategyEngine.evaluate_entry(valid_stock)
    assert is_valid is True

def test_strategy_entry_rejected_on_rsi():
    """Stock with overbought RSI (> 62) should be rejected."""
    overbought_stock = {
        "symbol": "TRENT",
        "price": 5000.0,
        "DMA_20": 4850.0,
        "DMA_50": 4600.0,
        "DMA_100": 5500.0,
        "rsi": 72.0 # Too high
    }
    is_valid, reason = StrategyEngine.evaluate_entry(overbought_stock)
    assert is_valid is False
    assert "RSI" in reason

def test_strategy_entry_rejected_on_headroom():
    """Stock already within 2% of 100 DEMA should be rejected (insufficient risk-reward)."""
    close_to_target = {
        "symbol": "TRENT",
        "price": 5000.0,
        "DMA_20": 4850.0,
        "DMA_50": 4600.0,
        "DMA_100": 5100.0, # only +2% away (< 4%)
        "rsi": 55.0
    }
    is_valid, reason = StrategyEngine.evaluate_entry(close_to_target)
    assert is_valid is False
    assert "Insufficient headroom" in reason

def test_tranche_scale_in_pullback_to_20_dema():
    """Stock pulling back to 20 DEMA support should trigger an averaging tranche."""
    position = {
        "symbol": "TRENT",
        "initial_qty": 10,
        "current_qty": 10,
        "buy_price": 5000.0,
        "tranches_count": 1,
        "invested_amount": 50000.0
    }
    current_dema = {
        "dema_20": 4980.0,
        "dema_50": 4700.0,
        "dema_100": 5400.0,
        "dema_200": 5800.0
    }
    # Price is 5010.0 (which is +0.6% above 20 DEMA 4980.0)
    should_scale, reason = StrategyEngine.evaluate_scale_in(position, 5010.0, current_dema)
    assert should_scale is True
    assert "Dip-Buy Tranche" in reason

def test_tranche_scale_in_pyramiding_momentum():
    """Stock gaining +2.5% with upside to 100 DEMA should qualify for pyramiding tranche."""
    position = {
        "symbol": "BEL",
        "initial_qty": 200,
        "current_qty": 200,
        "buy_price": 250.0,
        "tranches_count": 1,
        "invested_amount": 50000.0
    }
    current_dema = {
        "dema_20": 248.0,
        "dema_50": 240.0,
        "dema_100": 280.0,
        "dema_200": 300.0
    }
    # Price moved to 257.0 (+2.8% gain)
    should_scale, reason = StrategyEngine.evaluate_scale_in(position, 257.0, current_dema)
    assert should_scale is True
    assert "Pyramid Tranche" in reason

def test_tranche_bucket_cap_enforcement():
    """Cannot add more than 5 tranches or exceed ₹2.5L bucket cap."""
    position = {
        "symbol": "BEL",
        "initial_qty": 1000,
        "current_qty": 1000,
        "buy_price": 250.0,
        "tranches_count": 5, # already 5 tranches
        "invested_amount": 250000.0
    }
    can_add, reason = RiskManager.can_add_tranche(position)
    assert can_add is False
    assert "Max tranches reached" in reason

def test_risk_manager_tranche_sizing():
    """For ₹50,000 tranche and stock at ₹1,000, tranche size is 50 shares."""
    qty = RiskManager.calculate_position_size(price=1000.0)
    assert qty == 50 # 50000 / 1000 = 50 shares

def test_exit_100_dema_resistance_locks_profit():
    """When price reaches 99.9% of 100 DEMA, sell 30% and move SL to breakeven."""
    position = {
        "symbol": "INFY",
        "initial_qty": 100,
        "current_qty": 100,
        "buy_price": 1500.0,
        "stop_loss": 1447.5,
        "phase": "ENTRY",
        "days_at_100_dema": 0
    }
    current_dema = {
        "dema_20": 1540.0,
        "dema_50": 1510.0,
        "dema_100": 1600.0,
        "dema_200": 1750.0
    }
    # Price is 1599.0 (which is 99.93% of 100 DEMA)
    eval_res = StrategyEngine.evaluate_exit(position, 1599.0, current_dema)
    assert eval_res["action"] == "PARTIAL_SELL"
    assert eval_res["quantity"] == 30 # 30% of 100
    assert eval_res["new_phase"] == "TARGET_1_LOCKED"
    assert eval_res["new_stop_loss"] >= 1500.0 * 1.005 # Breakeven + buffer

def test_exit_200_dema_breakout_activates_runner():
    """When price bisects > 101% of 200 DEMA, transition to Mega-Runner."""
    position = {
        "symbol": "RELIANCE",
        "initial_qty": 50,
        "current_qty": 35,
        "buy_price": 2800.0,
        "stop_loss": 2814.0,
        "phase": "TARGET_1_LOCKED",
        "days_at_100_dema": 0
    }
    current_dema = {
        "dema_20": 2980.0,
        "dema_50": 2900.0,
        "dema_100": 2950.0,
        "dema_200": 3000.0
    }
    eval_res = StrategyEngine.evaluate_exit(position, 3035.0, current_dema)
    assert eval_res["action"] == "NONE" # Hold and let run!
    assert eval_res["new_phase"] == "RUNNER_ACTIVE"

def test_kite_client_paper_execution():
    """KiteTraderClient in PAPER mode should simulate order placement successfully."""
    client = KiteTraderClient(mode="PAPER")
    buy_res = client.place_buy_order("SBIN", 50, 800.0)
    assert buy_res["status"] == "SUCCESS"
    assert "PAPER" in buy_res["order_id"]

    sell_res = client.place_sell_order("SBIN", 50, 850.0, "Target Reached")
    assert sell_res["status"] == "SUCCESS"
    assert "PAPER" in sell_res["order_id"]

def test_ab_strategy_determination_and_balancing():
    """Bot should balance positions between TRANCHE_AVERAGING and ONE_SHOT (max 4 each)."""
    from auto_trader.db import save_open_position, delete_open_position, get_open_positions

    # Clear open positions
    for p in get_open_positions():
        delete_open_position(p["symbol"])

    # Initially empty, starts with TRANCHE_AVERAGING or ONE_SHOT
    strat, reason = RiskManager.determine_next_strategy()
    assert strat in ["TRANCHE_AVERAGING", "ONE_SHOT"]

    # If 4 TRANCHE positions exist, next should strictly be ONE_SHOT
    for i in range(4):
        save_open_position({
            "symbol": f"TR_STOCK_{i}",
            "strategy_type": "TRANCHE_AVERAGING",
            "initial_qty": 10,
            "current_qty": 10,
            "buy_price": 500.0,
            "current_price": 500.0,
            "stop_loss": 480.0
        })

    strat, _ = RiskManager.determine_next_strategy()
    assert strat == "ONE_SHOT"

    # Fill 4 ONE_SHOT positions as well (4 + 4 = 8 total)
    for i in range(4):
        save_open_position({
            "symbol": f"OS_STOCK_{i}",
            "strategy_type": "ONE_SHOT",
            "initial_qty": 100,
            "current_qty": 100,
            "buy_price": 500.0,
            "current_price": 500.0,
            "stop_loss": 480.0
        })

    # Now all 8 slots are full
    strat, reason = RiskManager.determine_next_strategy()
    assert strat is None
    assert "Maximum stock buckets reached" in reason

def test_one_shot_position_sizing_and_no_scaling():
    """ONE_SHOT positions receive full ₹2.5L lump sum and reject scale-in attempts."""
    from auto_trader.db import delete_open_position, get_open_positions

    for p in get_open_positions():
        delete_open_position(p["symbol"])

    # Stock at ₹1000: One-shot receives 250,000 / 1000 = 250 shares
    os_qty = RiskManager.calculate_position_size(price=1000.0, strategy_type="ONE_SHOT")
    assert os_qty == 250

    # Tranche receives 50,000 / 1000 = 50 shares
    tr_qty = RiskManager.calculate_position_size(price=1000.0, strategy_type="TRANCHE_AVERAGING")
    assert tr_qty == 50

    # ONE_SHOT position cannot add tranches
    os_pos = {
        "symbol": "TRENT",
        "strategy_type": "ONE_SHOT",
        "initial_qty": 250,
        "current_qty": 250,
        "buy_price": 1000.0,
        "tranches_count": 1,
        "invested_amount": 250000.0
    }
    can_scale, reason = RiskManager.can_add_tranche(os_pos)
    assert can_scale is False
    assert "One-Shot" in reason

def test_performance_matrix_computation():
    """BotRunner compute_performance_matrix should accurately compare both strategies."""
    from auto_trader.bot_runner import bot_runner
    from auto_trader.db import record_trade, save_open_position, delete_open_position, get_open_positions

    for p in get_open_positions():
        delete_open_position(p["symbol"])

    # Record 1 winning trade for Tranche Averaging
    record_trade("STOCK_A", "FULL_SELL", 100, 100.0, 110.0, 1000.0, 10.0, "Target Reached", strategy_type="TRANCHE_AVERAGING")
    # Record 1 losing trade for One-Shot
    record_trade("STOCK_B", "FULL_SELL", 200, 100.0, 95.0, -1000.0, -5.0, "Stop Loss", strategy_type="ONE_SHOT")

    matrix = bot_runner.compute_performance_matrix()
    assert "trancheAveraging" in matrix
    assert "oneShot" in matrix
    assert matrix["trancheAveraging"]["realizedPnl"] == 1000.0
    assert matrix["trancheAveraging"]["winRatePct"] == 100.0
    assert matrix["oneShot"]["realizedPnl"] == -1000.0
    assert matrix["oneShot"]["winRatePct"] == 0.0
    assert matrix["leader"] == "TRANCHE_AVERAGING"
    assert matrix["deltaPnl"] == 2000.0

