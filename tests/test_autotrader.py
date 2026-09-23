"""
Unit Tests for Auto-Trader Submodule (DEMA Stage-Rider)
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
    update_bot_state(total_capital=10000.0, available_cash=10000.0, max_positions=2, is_running=0)

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

def test_exit_100_dema_resistance_locks_profit():
    """When price reaches 99.9% of 100 DEMA, sell 30% and move SL to breakeven."""
    position = {
        "symbol": "INFY",
        "initial_qty": 10,
        "current_qty": 10,
        "buy_price": 1500.0,
        "stop_loss": 1447.5, # -3.5%
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
    assert eval_res["quantity"] == 3 # 30% of 10
    assert eval_res["new_phase"] == "TARGET_1_LOCKED"
    assert eval_res["new_stop_loss"] >= 1500.0 * 1.005 # Breakeven + buffer

def test_exit_200_dema_breakout_activates_runner():
    """When price bisects > 101% of 200 DEMA, transition to Mega-Runner."""
    position = {
        "symbol": "RELIANCE",
        "initial_qty": 10,
        "current_qty": 7,
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
    # Price is 3035.0 (which is 101.16% of 200 DEMA)
    eval_res = StrategyEngine.evaluate_exit(position, 3035.0, current_dema)
    assert eval_res["action"] == "NONE" # Hold and let run!
    assert eval_res["new_phase"] == "RUNNER_ACTIVE"

def test_runner_exit_below_20_dema():
    """While in Mega-Runner mode, exit only when price drops below 20 DEMA."""
    position = {
        "symbol": "RELIANCE",
        "initial_qty": 10,
        "current_qty": 7,
        "buy_price": 2800.0,
        "stop_loss": 2950.0,
        "phase": "RUNNER_ACTIVE",
        "days_at_100_dema": 0
    }
    current_dema = {
        "dema_20": 3200.0,
        "dema_50": 3050.0,
        "dema_100": 2950.0,
        "dema_200": 3000.0
    }
    # Price fell to 3180.0 (below 20 DEMA 3200.0)
    eval_res = StrategyEngine.evaluate_exit(position, 3180.0, current_dema)
    assert eval_res["action"] == "FULL_SELL"
    assert "Mega-Runner Exit" in eval_res["reason"]

def test_risk_manager_position_sizing():
    """For ₹10,000 capital and 2 slots, each position budget is ₹5,000."""
    update_bot_state(total_capital=10000.0, available_cash=10000.0, max_positions=2)
    qty = RiskManager.calculate_position_size(price=1000.0)
    assert qty == 5 # 5000 / 1000 = 5 shares

def test_kite_client_paper_execution():
    """KiteTraderClient in PAPER mode should simulate order placement successfully."""
    client = KiteTraderClient(mode="PAPER")
    buy_res = client.place_buy_order("SBIN", 5, 800.0)
    assert buy_res["status"] == "SUCCESS"
    assert "PAPER" in buy_res["order_id"]

    sell_res = client.place_sell_order("SBIN", 5, 850.0, "Target Reached")
    assert sell_res["status"] == "SUCCESS"
    assert "PAPER" in sell_res["order_id"]
