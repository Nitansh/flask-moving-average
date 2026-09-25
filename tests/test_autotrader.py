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
    from auto_trader.db import get_connection
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM bot_positions")
        conn.execute("DELETE FROM bot_trades")
        conn.execute("DELETE FROM bot_logs")
    update_bot_state(
        total_capital=BotConfig.INITIAL_CAPITAL,
        available_cash=BotConfig.INITIAL_CAPITAL,
        bucket_capital=BotConfig.BUCKET_CAPITAL_PER_STOCK,
        tranche_size=BotConfig.TRANCHE_SIZE,
        max_positions=BotConfig.MAX_ACTIVE_POSITIONS,
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

def test_strategy_entry_rejected_when_price_above_100_dema():
    """Stock with price already above 100 DEMA has no Target 1 headroom and MUST be rejected."""
    above_100_dema = {
        "symbol": "TRENT",
        "price": 5200.0, # Price is above 100 DEMA
        "DMA_20": 4850.0,
        "DMA_50": 4600.0,
        "DMA_100": 5000.0,
        "rsi": 55.0
    }
    is_valid, reason = StrategyEngine.evaluate_entry(above_100_dema)
    assert is_valid is False
    assert "above 100 DEMA" in reason

def test_strategy_entry_scanner_flagged_still_checks_headroom():
    """Even if flagged isBullish by scanner, must have at least 4% headroom to 100 DEMA."""
    scanner_stock_low_headroom = {
        "symbol": "TRENT",
        "price": 5000.0,
        "DMA_20": 4850.0,
        "DMA_50": 4600.0,
        "DMA_100": 5100.0, # only +2.0% away (< 4.0%)
        "rsi": 55.0,
        "isBullish": "true"
    }
    is_valid, reason = StrategyEngine.evaluate_entry(scanner_stock_low_headroom)
    assert is_valid is False
    assert "Insufficient headroom" in reason

    scanner_stock_good_headroom = {
        "symbol": "TRENT",
        "price": 5000.0,
        "DMA_20": 4850.0,
        "DMA_50": 4600.0,
        "DMA_100": 5250.0, # +5.0% headroom (>= 4.0%)
        "rsi": 55.0,
        "isBullish": "true"
    }
    is_valid, reason = StrategyEngine.evaluate_entry(scanner_stock_good_headroom)
    assert is_valid is True
    assert "Live Scanner Confirmed" in reason

def test_strategy_entry_rejected_on_death_cross():
    """Stock in a Death Cross regime (20 DEMA < 50 DEMA with gap > 3%) MUST be rejected."""
    death_cross_stock = {
        "symbol": "BEARISH_STOCK",
        "marketType": "Large Cap",
        "price": 105.0,
        "DMA_20": 90.0,
        "DMA_50": 100.0, # 20 DEMA is 10% below 50 DEMA
        "DMA_100": 120.0,
        "rsi": 52.0
    }
    is_valid, reason = StrategyEngine.evaluate_entry(death_cross_stock)
    assert is_valid is False
    assert "No Golden Crossover" in reason
    assert "Death Cross regime" in reason

def test_strategy_entry_rejected_when_price_below_20_dema():
    """Stock where price has fallen below 20 DEMA lacks breakout momentum and MUST be rejected."""
    breakdown_stock = {
        "symbol": "WEAK_STOCK",
        "marketType": "Large Cap",
        "price": 95.0,
        "DMA_20": 100.0, # Price < 20 DEMA
        "DMA_50": 98.0,
        "DMA_100": 115.0,
        "rsi": 50.0
    }
    is_valid, reason = StrategyEngine.evaluate_entry(breakdown_stock)
    assert is_valid is False
    assert "Price" in reason and "below 20 DEMA" in reason

def test_strategy_entry_qualifies_on_approaching_golden_cross():
    """Stock with 20 DEMA converging <= 3% of 50 DEMA with price > 20 DEMA MUST qualify."""
    approaching_stock = {
        "symbol": "APPROACHING_STOCK",
        "marketType": "Large Cap",
        "price": 102.0,
        "DMA_20": 99.0,
        "DMA_50": 100.0, # Gap is 1.0% (<= 3.0%)
        "DMA_100": 115.0,
        "rsi": 52.0,
        "goldenCrossGap": 1.0
    }
    is_valid, reason = StrategyEngine.evaluate_entry(approaching_stock)
    assert is_valid is True
    assert "Approaching Golden Cross" in reason

def test_strategy_entry_rejected_on_small_cap():
    """Small Cap stocks must be excluded from AutoTrader entry."""
    small_cap_stock = {
        "symbol": "PENNY_STOCK",
        "marketType": "Small Cap",
        "price": 100.0,
        "DMA_20": 95.0,
        "DMA_50": 90.0,
        "DMA_100": 110.0,
        "rsi": 55.0
    }
    is_valid, reason = StrategyEngine.evaluate_entry(small_cap_stock)
    assert is_valid is False
    assert "Small Cap" in reason

def test_tranche_scale_in_requires_minimum_price_dip(monkeypatch):
    """Stock must pull back at least -3.0% below average buy price to add an averaging tranche."""
    monkeypatch.setattr(BotConfig, "MAX_TRANCHES_PER_STOCK", 5)
    position = {
        "symbol": "TRENT",
        "initial_qty": 10,
        "current_qty": 10,
        "buy_price": 5000.0,
        "tranches_count": 1,
        "invested_amount": 50000.0,
        "stop_loss": 4650.0
    }
    current_dema = {
        "dema_20": 4800.0,
        "dema_50": 4700.0,
        "dema_100": 5400.0,
        "dema_200": 5800.0
    }
    # Case 1: Insufficient dip (4950.0 is only -1.0% dip from 5000.0) -> MUST REJECT
    should_scale, reason = StrategyEngine.evaluate_scale_in(position, 4950.0, current_dema)
    assert should_scale is False
    assert "minimum -3.0% pullback" in reason

    # Case 2: Genuine dip (4820.0 is -3.6% dip below 5000.0, holding above 50 DEMA 4700) -> MUST QUALIFY
    should_scale, reason = StrategyEngine.evaluate_scale_in(position, 4820.0, current_dema)
    assert should_scale is True
    assert "Dip-Buy Tranche" in reason

def test_tranche_bucket_cap_enforcement():
    """Cannot add tranches in One-Shot mode or when bucket cap is reached."""
    position = {
        "symbol": "BEL",
        "initial_qty": 400,
        "current_qty": 400,
        "buy_price": 250.0,
        "tranches_count": 1,
        "invested_amount": 100000.0
    }
    can_add, reason = RiskManager.can_add_tranche(position)
    assert can_add is False
    assert "One-Shot" in reason or "Max tranches" in reason

def test_risk_manager_one_shot_sizing():
    """For ₹100,000 One-Shot allocation and stock at ₹1,000, size is 100 shares."""
    qty = RiskManager.calculate_position_size(price=1000.0)
    assert qty == 100 # 100000 / 1000 = 100 shares

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

def test_exit_100_dema_not_triggered_without_profit():
    """If stock is near 100 DEMA but trade has negligible profit (< 2%), do not initiate profit booking."""
    position = {
        "symbol": "INFY",
        "initial_qty": 100,
        "current_qty": 100,
        "buy_price": 1595.0, # Bought almost at 100 DEMA
        "stop_loss": 1539.0,
        "phase": "ENTRY",
        "days_at_100_dema": 0
    }
    current_dema = {
        "dema_20": 1580.0,
        "dema_50": 1560.0,
        "dema_100": 1600.0,
        "dema_200": 1750.0
    }
    # Price is 1599.0 (gain is only +0.25%, not enough to justify partial profit booking)
    eval_res = StrategyEngine.evaluate_exit(position, 1599.0, current_dema)
    assert eval_res["action"] == "NONE"

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

def test_ab_strategy_determination_and_balancing(monkeypatch):
    """Bot should assign ONE_SHOT exclusively in pure mode, and balance positions when A/B is enabled."""
    from auto_trader.db import save_open_position, delete_open_position, get_open_positions

    # Clear open positions
    for p in get_open_positions():
        delete_open_position(p["symbol"])

    # 1. Pure One-Shot Mode (Current Default)
    strat, reason = RiskManager.determine_next_strategy()
    assert strat == "ONE_SHOT"

    # Fill 5 ONE_SHOT positions
    for i in range(5):
        save_open_position({
            "symbol": f"OS_STOCK_{i}",
            "strategy_type": "ONE_SHOT",
            "initial_qty": 100,
            "current_qty": 100,
            "buy_price": 500.0,
            "current_price": 500.0,
            "stop_loss": 480.0
        })

    # All 5 slots are full
    strat, reason = RiskManager.determine_next_strategy()
    assert strat is None
    assert "Maximum stock buckets reached" in reason

    # 2. When A/B Testing is explicitly enabled
    for p in get_open_positions():
        delete_open_position(p["symbol"])

    monkeypatch.setattr(BotConfig, "AB_TEST_ENABLED", True)
    monkeypatch.setattr(BotConfig, "MAX_TRANCHE_POSITIONS", 4)
    monkeypatch.setattr(BotConfig, "MAX_ONE_SHOT_POSITIONS", 4)
    monkeypatch.setattr(BotConfig, "MAX_ACTIVE_POSITIONS", 8)
    update_bot_state(max_positions=8)

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

def test_one_shot_position_sizing_and_no_scaling():
    """ONE_SHOT positions receive full ₹1.0L lump sum and reject scale-in attempts."""
    from auto_trader.db import delete_open_position, get_open_positions

    for p in get_open_positions():
        delete_open_position(p["symbol"])

    # Stock at ₹1000: One-shot receives 100,000 / 1000 = 100 shares
    os_qty = RiskManager.calculate_position_size(price=1000.0, strategy_type="ONE_SHOT")
    assert os_qty == 100

    # Tranche receives 100,000 / 1000 = 100 shares
    tr_qty = RiskManager.calculate_position_size(price=1000.0, strategy_type="TRANCHE_AVERAGING")
    assert tr_qty == 100

    # ONE_SHOT position cannot add tranches
    os_pos = {
        "symbol": "TRENT",
        "strategy_type": "ONE_SHOT",
        "initial_qty": 100,
        "current_qty": 100,
        "buy_price": 1000.0,
        "tranches_count": 1,
        "invested_amount": 100000.0
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
    assert matrix["trancheAveraging"]["grossPnl"] == 1000.0
    assert matrix["trancheAveraging"]["totalCharges"] > 0.0
    assert matrix["trancheAveraging"]["realizedPnl"] == round(1000.0 - matrix["trancheAveraging"]["totalCharges"], 2)
    assert matrix["trancheAveraging"]["winRatePct"] == 100.0
    assert matrix["oneShot"]["grossPnl"] == -1000.0
    assert matrix["oneShot"]["winRatePct"] == 0.0
    assert matrix["leader"] == "TRANCHE_AVERAGING"
    assert matrix["deltaPnl"] > 0.0

def test_live_scan_candidates_pulling(monkeypatch):
    """BotRunner should automatically pull candidates from live scan sources when candidate_stocks is empty."""
    from auto_trader.bot_runner import bot_runner
    
    mock_scanned_stocks = [
        {
            "symbol": "TRENT",
            "price": 5000.0,
            "DMA_20": 4850.0,
            "DMA_50": 4600.0,
            "DMA_100": 5350.0,
            "DMA_200": 4300.0,
            "rsi": 55.0
        }
    ]
    
    monkeypatch.setattr(bot_runner, "fetch_live_scan_candidates", lambda: (mock_scanned_stocks, "Mock Live Scan Feed"))
    
    # Run cycle with None / empty candidate_stocks
    bot_runner.evaluate_cycle(candidate_stocks=None)
    
def test_performance_matrix_keys_and_defaults():
    """Performance matrix should safely include both investedCapital and capitalInvested with safe numeric defaults even with zero trades."""
    from auto_trader.bot_runner import bot_runner
    matrix = bot_runner.compute_performance_matrix()
    
    for key in ["trancheAveraging", "oneShot"]:
        data = matrix[key]
        assert "investedCapital" in data
        assert "capitalInvested" in data
        assert isinstance(data["investedCapital"], (int, float))
        assert isinstance(data["capitalInvested"], (int, float))
        assert isinstance(data["bestTradePnl"], (int, float))
        assert isinstance(data["worstTradePnl"], (int, float))
        assert isinstance(data["realizedPnl"], (int, float))
        assert isinstance(data["unrealizedPnl"], (int, float))
        assert isinstance(data["netPnl"], (int, float))
        assert isinstance(data["grossPnl"], (int, float))

def test_bot_reset():
    """Bot reset should wipe all positions, trades, and reset bot state to initial capital."""
    from auto_trader.bot_runner import bot_runner
    from auto_trader.db import save_open_position, record_trade, log_event, get_open_positions, get_trades, get_bot_state

    # Add mock position, trade, log
    save_open_position({
        "symbol": "TESTSTOCK",
        "strategy_type": "TRANCHE_AVERAGING",
        "initial_qty": 10,
        "current_qty": 10,
        "buy_price": 100.0,
        "current_price": 105.0,
        "stop_loss": 95.0
    })
    record_trade("TESTSTOCK", "BUY", 10, 100.0, 0.0)
    log_event("INFO", "Test log message")

    assert len(get_open_positions()) == 1
    assert len(get_trades()) >= 1

    success, msg = bot_runner.reset(initial_capital=500000.0)
    assert success is True
    assert "reset" in msg.lower()

    # Verify positions and trades are wiped
    assert len(get_open_positions()) == 0
    assert len(get_trades()) == 0
    state = get_bot_state()
    assert state["is_running"] == 0
    assert state["available_cash"] == 500000.0
    assert state["total_capital"] == 500000.0

def test_calculate_rank_score_mcap_tiers():
    """Validates market cap tier scoring: Largecap (25) > Midcap (18) > Smallcap (8)."""
    large_stock = {
        "symbol": "RELIANCE",
        "price": 2500.0,
        "DMA_20": 2400.0,
        "DMA_50": 2300.0,
        "DMA_100": 2750.0,
        "rsi": 50.0,
        "volume": 2000000,
        "marketType": "Large Cap"
    }
    mid_stock = {
        "symbol": "ACC",
        "price": 2500.0,
        "DMA_20": 2400.0,
        "DMA_50": 2300.0,
        "DMA_100": 2750.0,
        "rsi": 50.0,
        "volume": 2000000,
        "marketType": "Mid Cap"
    }
    small_stock = {
        "symbol": "TINYCO",
        "price": 2500.0,
        "DMA_20": 2400.0,
        "DMA_50": 2300.0,
        "DMA_100": 2750.0,
        "rsi": 50.0,
        "volume": 2000000,
        "marketType": "Small Cap"
    }

    large_score, large_b = StrategyEngine.calculate_rank_score(large_stock)
    mid_score, mid_b = StrategyEngine.calculate_rank_score(mid_stock)
    small_score, small_b = StrategyEngine.calculate_rank_score(small_stock)

    assert large_b["mcap_score"] == 25.0
    assert mid_b["mcap_score"] == 18.0
    assert small_b["mcap_score"] == 8.0
    assert large_score > mid_score > small_score

def test_calculate_rank_score_rsi_and_volume():
    """RSI sweet spot (48-55) and high volume (>= 1M) should get maximum points."""
    sweet_spot = {
        "symbol": "TCS",
        "price": 3500.0,
        "DMA_20": 3400.0,
        "DMA_50": 3300.0,
        "DMA_100": 3900.0,
        "rsi": 52.0,
        "volume": 1500000
    }
    score, b = StrategyEngine.calculate_rank_score(sweet_spot)
    assert b["rsi_score"] == 20.0
    assert b["volume_score"] == 20.0
    assert b["mcap_score"] == 25.0  # TCS is in LARGECAP_SYMBOLS

def test_scan_and_enter_prioritizes_top_ranked_candidate():
    """Bot must scan all candidates first and pick the highest-ranked stock, not the first element in the list."""
    from auto_trader.bot_runner import bot_runner
    from auto_trader.db import get_open_positions

    # Limit max positions to 1 to test prioritization
    update_bot_state(max_positions=1)

    candidates = [
        # Candidate 0: Low-ranked Midcap (lower headroom, low volume, sub-optimal RSI)
        {
            "symbol": "LOWRANK",
            "price": 100.0,
            "DMA_20": 98.0,
            "DMA_50": 95.0,
            "DMA_100": 104.5, # +4.5% headroom (barely above 4%)
            "rsi": 65.0,
            "volume": 20000,
            "marketType": "Mid Cap"
        },
        # Candidate 1: High-ranked Largecap (high headroom, high volume, optimal RSI)
        {
            "symbol": "RELIANCE",
            "price": 2500.0,
            "DMA_20": 2400.0,
            "DMA_50": 2300.0,
            "DMA_100": 2850.0, # +14.0% headroom
            "rsi": 51.0,
            "volume": 3000000,
            "marketType": "Large Cap"
        },
        # Candidate 2: Mid-ranked Midcap
        {
            "symbol": "MIDRANK",
            "price": 500.0,
            "DMA_20": 480.0,
            "DMA_50": 460.0,
            "DMA_100": 535.0, # +7.0% headroom
            "rsi": 56.0,
            "volume": 400000,
            "marketType": "Mid Cap"
        },
        # Candidate 3: Disqualified Smallcap (must never qualify or enter)
        {
            "symbol": "PENNY_SMALL",
            "price": 50.0,
            "DMA_20": 48.0,
            "DMA_50": 45.0,
            "DMA_100": 60.0,
            "rsi": 50.0,
            "volume": 1000000,
            "marketType": "Small Cap"
        }
    ]

    # Run scan_and_enter with candidates
    bot_runner._scan_and_enter(candidates)

    open_pos = get_open_positions()
    assert len(open_pos) == 1
    # MUST have selected RELIANCE (top-ranked), not LOWRANK (first candidate in list)
    assert open_pos[0]["symbol"] == "RELIANCE"
    assert all(p["symbol"] != "PENNY_SMALL" for p in open_pos)
    assert all(r["symbol"] != "PENNY_SMALL" for r in bot_runner.ranked_opportunities)

def test_fetch_live_scan_candidates_blocks_while_scanning(monkeypatch):
    """When moving-average scanner reports isScanning=True and wait_for_completion=False, candidate fetch must return empty."""
    from auto_trader.bot_runner import bot_runner
    import requests

    class MockResponse:
        status_code = 200
        def json(self):
            return {"isScanning": True, "processedCount": 120, "totalStocks": 2246}

    monkeypatch.setattr(requests, "get", lambda url, timeout=None: MockResponse())
    candidates, source = bot_runner.fetch_live_scan_candidates(wait_for_completion=False)
    assert candidates == []
    assert "incomplete" in source or "scan in progress" in source

def test_fetch_live_scan_candidates_waits_and_retrieves_completed_universe(monkeypatch):
    """Bot should wait until isScanning becomes False, then fetch completed results."""
    from auto_trader.bot_runner import bot_runner
    import requests

    call_count = {"status": 0}

    class MockStatusResponse:
        status_code = 200
        def json(self):
            call_count["status"] += 1
            # First call: scanning; second call: complete!
            if call_count["status"] <= 1:
                return {"isScanning": True, "isComplete": False, "processedCount": 0, "totalStocks": 1}
            return {"isScanning": False, "isComplete": True, "processedCount": 1, "totalStocks": 1}

    class MockResultsResponse:
        status_code = 200
        def json(self):
            return [{"symbol": "RELIANCE", "price": 2500.0, "DMA_20": 2400.0, "DMA_50": 2300.0, "DMA_100": 2800.0}]

    def mock_get(url, timeout=None):
        if "status" in url:
            return MockStatusResponse()
        elif "results" in url or "full-list" in url:
            return MockResultsResponse()
        return MockStatusResponse()

    monkeypatch.setattr(requests, "get", mock_get)
    candidates, source = bot_runner.fetch_live_scan_candidates(wait_for_completion=True, max_wait_seconds=10, poll_interval_seconds=0.01)
    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "RELIANCE"
    assert "live universe cache" in source

def test_get_trade_analytics_and_csv_export():
    """Verify calculation of performance analytics and CSV export generation with technical indicators."""
    from auto_trader.db import record_trade, get_trade_analytics, generate_trades_csv, get_trades

    # Record winning trade with full technical indicators & NIFTY benchmark
    record_trade(
        "TRENT", "TARGET_1_SELL", 10, 5000.0, 5500.0,
        reason="Target 1 booked", strategy_type="ONE_SHOT",
        rsi=52.4, volume=850000,
        dema_20=5120.0, dema_50=4980.0, dema_100=4800.0, dema_200=4500.0,
        nifty_price=23450.0, nifty_dema_20=23200.0, nifty_dema_50=23100.0, nifty_dema_100=22800.0, nifty_dema_200=22200.0
    )
    # Record losing trade
    record_trade(
        "INFY", "STOP_LOSS_EXIT", 20, 1500.0, 1420.0,
        reason="Stop loss hit", strategy_type="ONE_SHOT",
        rsi=41.2, volume=1200000,
        dema_20=1480.0, dema_50=1510.0, dema_100=1550.0, dema_200=1600.0,
        nifty_price=23300.0, nifty_dema_20=23200.0, nifty_dema_50=23100.0, nifty_dema_100=22800.0, nifty_dema_200=22200.0
    )

    trades = get_trades(limit=2)
    trent = [t for t in trades if t["symbol"] == "TRENT"][0]
    assert trent["rsi"] == 52.4
    assert trent["volume"] == 850000
    assert trent["dema_20"] == 5120.0
    assert trent["nifty_price"] == 23450.0

    analytics = get_trade_analytics()
    assert analytics["completed_exits"] == 2
    assert analytics["winning_trades"] == 1
    assert analytics["losing_trades"] == 1
    assert analytics["win_rate_pct"] == 50.0
    assert analytics["best_trade"]["symbol"] == "TRENT"
    assert analytics["worst_trade"]["symbol"] == "INFY"
    assert analytics["profit_factor"] > 0
    assert analytics["indicator_insights"]["avg_win_rsi"] == 52.4
    assert analytics["indicator_insights"]["avg_loss_rsi"] == 41.2

    csv_data = generate_trades_csv()
    assert "Trade ID" in csv_data
    assert "RSI" in csv_data
    assert "Volume" in csv_data
    assert "DEMA 20 (INR)" in csv_data
    assert "NIFTY 50 Price (INR)" in csv_data
    assert "TRENT" in csv_data
    assert "52.4" in csv_data
    assert "23450.00" in csv_data
    assert "INFY" in csv_data
    assert "Target 1 booked" in csv_data






