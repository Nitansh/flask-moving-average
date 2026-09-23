"""
Auto-Trader Background Runner & Scheduler
Orchestrates market scans, position monitoring, order execution, and GUI state updates.
"""
import time
import threading
from datetime import datetime
import pytz

from .config import BotConfig
from .db import (
    get_bot_state, update_bot_state, get_open_positions, save_open_position,
    delete_open_position, record_trade, log_event, get_trades, get_recent_logs
)
from .kite_client import KiteTraderClient
from .risk_manager import RiskManager
from .strategy import StrategyEngine

IST = pytz.timezone("Asia/Kolkata")

class BotRunner:
    def __init__(self):
        self.running_thread = None
        self.stop_requested = False
        self.client = None
        self.lock = threading.Lock()
        self.last_scan_time = None

    def is_market_open(self):
        """Checks if current time is within Indian Stock Market hours (09:15 - 15:30 IST, Mon-Fri)."""
        now = datetime.now(IST)
        # Weekdays: 0 (Monday) to 4 (Friday)
        if now.weekday() > 4:
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close

    def start(self):
        with self.lock:
            state = get_bot_state()
            if state.get("is_running") and self.running_thread and self.running_thread.is_alive():
                return True, "Bot is already running"

            self.stop_requested = False
            self.client = KiteTraderClient(mode=state.get("mode", BotConfig.get_effective_mode()))
            update_bot_state(is_running=1)
            self.running_thread = threading.Thread(target=self._run_loop, daemon=True)
            self.running_thread.start()
            log_event("SUCCESS", f"Auto-Trader started in {self.client.mode} mode.")
            return True, f"Auto-Trader started in {self.client.mode} mode"

    def stop(self):
        with self.lock:
            self.stop_requested = True
            update_bot_state(is_running=0)
            log_event("INFO", "Auto-Trader stopped by user.")
            return True, "Auto-Trader stopped"

    def _run_loop(self):
        """Continuous background loop running during market hours."""
        while not self.stop_requested:
            try:
                # Check circuit breaker
                if not RiskManager.check_daily_drawdown():
                    log_event("WARNING", "Auto-Trader halted due to daily drawdown circuit breaker.")
                    update_bot_state(is_running=0)
                    break

                self.evaluate_cycle()
            except Exception as e:
                log_event("ERROR", f"Error in Auto-Trader execution cycle: {e}")

            # Sleep for 60 seconds between evaluations
            for _ in range(60):
                if self.stop_requested:
                    break
                time.sleep(1)

    def evaluate_cycle(self, candidate_stocks=None):
        """
        Executes one complete evaluation cycle:
        1. Evaluates all open positions against exits (Targets, SL, Trailing).
        2. If slots are available, scans candidate stocks for new BUY entries.
        """
        self.last_scan_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        if not self.client:
            self.client = KiteTraderClient()

        # Step 1: Monitor Active Positions
        self._monitor_positions()

        # Step 2: Search for New Entries if Capacity Exists
        can_open, reason = RiskManager.can_open_new_position()
        if can_open:
            self._scan_and_enter(candidate_stocks)
        else:
            log_event("INFO", f"Capacity full: {reason}")

    def _monitor_positions(self):
        """Checks open positions for target locks, trailing stops, and exits."""
        positions = get_open_positions()
        if not positions:
            return

        for pos in positions:
            symbol = pos["symbol"]
            current_price = pos["current_price"] # Updated via live fetch
            
            # Fetch fresh quote and DEMA indicators for symbol
            try:
                import yfinance as yf
                ticker = yf.Ticker(f"{symbol}.NS")
                fast_info = ticker.fast_info
                live_price = float(fast_info.last_price or current_price)
            except Exception:
                live_price = current_price

            dema_data = {
                "dema_20": pos.get("dema_20"),
                "dema_50": pos.get("dema_50"),
                "dema_100": pos.get("dema_100"),
                "dema_200": pos.get("dema_200")
            }

            # Update current price in DB
            pos["current_price"] = live_price
            save_open_position(pos)

            eval_res = StrategyEngine.evaluate_exit(pos, live_price, dema_data)
            action = eval_res.get("action", "NONE")

            if action == "PARTIAL_SELL":
                sell_qty = eval_res.get("quantity", 1)
                order_res = self.client.place_sell_order(symbol, sell_qty, live_price, eval_res.get("reason", ""))
                if order_res.get("status") == "SUCCESS":
                    # Record partial trade
                    pnl = (live_price - pos["buy_price"]) * sell_qty
                    pnl_pct = ((live_price - pos["buy_price"]) / pos["buy_price"]) * 100.0
                    record_trade(symbol, "PARTIAL_SELL", sell_qty, pos["buy_price"], live_price, pnl, pnl_pct, eval_res.get("reason"))
                    
                    # Update position and available cash
                    pos["current_qty"] -= sell_qty
                    pos["phase"] = eval_res.get("new_phase", pos.get("phase"))
                    if eval_res.get("new_stop_loss"):
                        pos["stop_loss"] = eval_res["new_stop_loss"]
                    save_open_position(pos)

                    state = get_bot_state()
                    update_bot_state(available_cash=state.get("available_cash", 0) + (sell_qty * live_price))

            elif action == "FULL_SELL":
                sell_qty = pos["current_qty"]
                order_res = self.client.place_sell_order(symbol, sell_qty, live_price, eval_res.get("reason", ""))
                if order_res.get("status") == "SUCCESS":
                    pnl = (live_price - pos["buy_price"]) * sell_qty
                    pnl_pct = ((live_price - pos["buy_price"]) / pos["buy_price"]) * 100.0
                    record_trade(symbol, "FULL_SELL", sell_qty, pos["buy_price"], live_price, pnl, pnl_pct, eval_res.get("reason"))

                    delete_open_position(symbol)
                    state = get_bot_state()
                    update_bot_state(available_cash=state.get("available_cash", 0) + (sell_qty * live_price))

            elif eval_res.get("new_phase") or eval_res.get("new_stop_loss"):
                if eval_res.get("new_phase"):
                    pos["phase"] = eval_res["new_phase"]
                if eval_res.get("new_stop_loss"):
                    pos["stop_loss"] = eval_res["new_stop_loss"]
                save_open_position(pos)
                log_event("INFO", f"{symbol}: {eval_res.get('reason')}")

            # -----------------------------------------------------------------
            # Tranche Averaging & Scaling In (Add ₹50k shots up to ₹2.5L bucket)
            # -----------------------------------------------------------------
            if action == "NONE" and pos.get("phase") in ["ENTRY", "TARGET_1_LOCKED"]:
                can_scale, _ = RiskManager.can_add_tranche(pos)
                if can_scale:
                    should_scale, scale_reason = StrategyEngine.evaluate_scale_in(pos, live_price, dema_data)
                    if should_scale:
                        add_qty = RiskManager.calculate_tranche_qty(live_price)
                        if add_qty > 0:
                            order_res = self.client.place_buy_order(symbol, add_qty, live_price)
                            if order_res.get("status") == "SUCCESS":
                                exec_price = float(order_res.get("executed_price", live_price))
                                old_qty = pos["current_qty"]
                                old_invested = pos.get("invested_amount") or (old_qty * pos["buy_price"])
                                add_cost = add_qty * exec_price

                                new_total_qty = old_qty + add_qty
                                new_invested = old_invested + add_cost
                                new_avg_price = new_invested / new_total_qty
                                new_tranches = int(pos.get("tranches_count", 1)) + 1

                                pos["current_qty"] = new_total_qty
                                pos["initial_qty"] = int(pos.get("initial_qty", old_qty)) + add_qty
                                pos["buy_price"] = round(new_avg_price, 2)
                                pos["invested_amount"] = round(new_invested, 2)
                                pos["tranches_count"] = new_tranches
                                pos["stop_loss"] = round(new_avg_price * (1.0 - (BotConfig.HARD_STOP_LOSS_PCT / 100.0)), 2)

                                save_open_position(pos)
                                record_trade(symbol, "BUY_TRANCHE", add_qty, exec_price, 0.0, 0.0, 0.0, f"Tranche #{new_tranches}: {scale_reason}")

                                state = get_bot_state()
                                update_bot_state(available_cash=max(0.0, state.get("available_cash", 0) - add_cost))
                                log_event("SUCCESS", f"Added Tranche #{new_tranches} for {symbol}: {add_qty} shares @ ₹{exec_price:.2f}. Total: ₹{new_invested:.2f}/{RiskManager.get_bucket_size():.0f} (Avg: ₹{new_avg_price:.2f})")

    def _scan_and_enter(self, candidate_stocks=None):
        """Scans candidate stocks meeting strategy criteria and places initial ₹50,000 BUY order."""
        stocks_to_scan = candidate_stocks or []
        if not stocks_to_scan:
            return

        for stock in stocks_to_scan:
            can_open, _ = RiskManager.can_open_new_position()
            if not can_open:
                break

            symbol = stock.get("symbol")
            if not symbol:
                continue

            # Don't buy if already holding
            open_symbols = [p["symbol"] for p in get_open_positions()]
            if symbol in open_symbols:
                continue

            is_valid, reason = StrategyEngine.evaluate_entry(stock)
            if is_valid:
                price = float(stock.get("price") or stock.get("currentPrice") or 0.0)
                qty = RiskManager.calculate_position_size(price)
                if qty <= 0:
                    continue

                order_res = self.client.place_buy_order(symbol, qty, price)
                if order_res.get("status") == "SUCCESS":
                    exec_price = float(order_res.get("executed_price", price))
                    stop_loss = round(exec_price * (1.0 - (BotConfig.HARD_STOP_LOSS_PCT / 100.0)), 2)
                    invested = round(qty * exec_price, 2)

                    pos = {
                        "symbol": symbol,
                        "initial_qty": qty,
                        "current_qty": qty,
                        "buy_price": exec_price,
                        "current_price": exec_price,
                        "stop_loss": stop_loss,
                        "dema_100": stock.get("DMA_100") or stock.get("dema_100"),
                        "dema_200": stock.get("DMA_200") or stock.get("dema_200"),
                        "dema_20": stock.get("DMA_20") or stock.get("dema_20"),
                        "dema_50": stock.get("DMA_50") or stock.get("dema_50"),
                        "phase": "ENTRY",
                        "tranches_count": 1,
                        "invested_amount": invested,
                        "days_at_100_dema": 0,
                        "entry_date": datetime.now(IST).strftime("%Y-%m-%d")
                    }
                    save_open_position(pos)
                    record_trade(symbol, "BUY", qty, exec_price, 0.0, 0.0, 0.0, f"Tranche #1 (Initial): {reason}")

                    state = get_bot_state()
                    new_cash = max(0.0, state.get("available_cash", BotConfig.INITIAL_CAPITAL) - invested)
                    update_bot_state(available_cash=new_cash)
                    log_event("SUCCESS", f"Opened new bucket in {symbol} [Tranche 1/5]: {qty} shares @ ₹{exec_price:.2f} (₹{invested:.2f}/₹{RiskManager.get_bucket_size():.0f}). SL set at ₹{stop_loss:.2f}")

    def get_status(self):
        """Returns full snapshot of Auto-Trader state for the frontend GUI."""
        state = get_bot_state()
        positions = get_open_positions()
        trades = get_trades(limit=20)
        logs = get_recent_logs(limit=40)

        # Calculate metrics
        total_invested = sum(p["current_price"] * p["current_qty"] for p in positions)
        unrealized_pnl = sum((p["current_price"] - p["buy_price"]) * p["current_qty"] for p in positions)
        realized_pnl = sum(t["realized_pnl"] for t in trades if "SELL" in t.get("trade_type", ""))

        return {
            "isRunning": bool(state.get("is_running", 0)),
            "mode": state.get("mode", "PAPER"),
            "hasLiveCredentials": BotConfig.has_live_credentials(),
            "totalCapital": float(state.get("total_capital", BotConfig.INITIAL_CAPITAL)),
            "availableCash": float(state.get("available_cash", BotConfig.INITIAL_CAPITAL)),
            "bucketCapital": float(state.get("bucket_capital", BotConfig.BUCKET_CAPITAL_PER_STOCK)),
            "trancheSize": float(state.get("tranche_size", BotConfig.TRANCHE_SIZE)),
            "maxTranches": BotConfig.MAX_TRANCHES_PER_STOCK,
            "investedCapital": round(total_invested, 2),
            "unrealizedPnl": round(unrealized_pnl, 2),
            "realizedPnl": round(realized_pnl, 2),
            "maxPositions": int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS)),
            "partialProfitPct": float(state.get("partial_profit_pct", 30.0)),
            "stagnationDays": int(state.get("stagnation_days", 3)),
            "lastScanTime": self.last_scan_time,
            "positions": positions,
            "trades": trades,
            "logs": logs
        }

# Global singleton runner instance
bot_runner = BotRunner()
