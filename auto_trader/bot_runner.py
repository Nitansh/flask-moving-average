"""
Auto-Trader Background Runner & Scheduler
Orchestrates market scans, position monitoring, order execution, and GUI state updates.
"""
import time
import os
import json
import sqlite3
import threading
from datetime import datetime, timedelta
import pytz

from .config import BotConfig
from .db import (
    get_bot_state, update_bot_state, get_open_positions, save_open_position,
    delete_open_position, record_trade, log_event, get_trades, get_recent_logs,
    reset_autotrader
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

    def reset(self, initial_capital=2000000.0):
        with self.lock:
            self.stop_requested = True
            reset_autotrader(initial_capital=initial_capital)
            self.last_scan_time = None
            return True, "Auto-Trader reset to initial testing state."

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
                    strat_type = pos.get("strategy_type", "TRANCHE_AVERAGING")
                    record_trade(symbol, "PARTIAL_SELL", sell_qty, pos["buy_price"], live_price, pnl, pnl_pct, eval_res.get("reason"), strategy_type=strat_type)
                    
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
                    strat_type = pos.get("strategy_type", "TRANCHE_AVERAGING")
                    record_trade(symbol, "FULL_SELL", sell_qty, pos["buy_price"], live_price, pnl, pnl_pct, eval_res.get("reason"), strategy_type=strat_type)

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
            # Tranche Averaging & Scaling In (Allowed only for TRANCHE_AVERAGING)
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
                                record_trade(symbol, "BUY_TRANCHE", add_qty, exec_price, 0.0, 0.0, 0.0, f"Tranche #{new_tranches}: {scale_reason}", strategy_type="TRANCHE_AVERAGING")

                                state = get_bot_state()
                                update_bot_state(available_cash=max(0.0, state.get("available_cash", 0) - add_cost))
                                log_event("SUCCESS", f"Added Tranche #{new_tranches} for {symbol}: {add_qty} shares @ ₹{exec_price:.2f}. Total: ₹{new_invested:.2f}/{RiskManager.get_bucket_size():.0f} (Avg: ₹{new_avg_price:.2f})")

    def fetch_live_scan_candidates(self, wait_for_completion=True, max_wait_seconds=1800, poll_interval_seconds=60.0):
        """
        Retrieves candidate stocks EXCLUSIVELY from moving-average's universe scanner.
        NO FALLBACKS: Only the official moving-average universe pipeline is used.
        If a scan is in progress, waits until all stocks are 100% scanned and processed.
        Waits for 1 minute (poll_interval_seconds=60.0) between scan progress checks.
        Returns: (candidates_list, source_description)
        """
        import requests
        import time

        ports = [3000, 8080]

        def _interruptible_sleep(seconds):
            step = 1.0
            elapsed = 0.0
            while elapsed < seconds:
                if self.stop_requested:
                    break
                to_sleep = min(step, seconds - elapsed)
                time.sleep(to_sleep)
                elapsed += to_sleep

        # Helper to check scan status on Node.js
        def get_scan_status():
            for port in ports:
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}/api/scan/status", timeout=2.5)
                    if resp.status_code == 200:
                        return port, resp.json()
                except Exception:
                    pass
            return None, None

        # Helper to fetch completed results
        def get_scan_results(port):
            for endpoint in ["/api/scan/results", "/api/full-list"]:
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}{endpoint}", timeout=15.0)
                    if resp.status_code == 200:
                        stocks = resp.json()
                        if isinstance(stocks, list) and len(stocks) > 0:
                            return stocks, f"movingAverage live universe cache (port {port}{endpoint}, {len(stocks)} stocks)"
                except Exception:
                    pass
            return None, None

        # Helper to query SQLite auth.db
        def get_db_results():
            possible_db_paths = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "movingAverage", "auth.db")),
                os.path.abspath("c:/moving-average/movingAverage/auth.db"),
                os.path.abspath(os.path.join(os.getcwd(), "movingAverage", "auth.db")),
            ]
            for db_path in possible_db_paths:
                if os.path.exists(db_path):
                    try:
                        conn = sqlite3.connect(db_path, timeout=5.0)
                        cursor = conn.cursor()
                        cursor.execute("SELECT data FROM scan_results")
                        rows = cursor.fetchall()
                        conn.close()
                        if rows:
                            stocks = []
                            for r in rows:
                                try:
                                    if r[0]:
                                        stocks.append(json.loads(r[0]))
                                except Exception:
                                    pass
                            if stocks:
                                return stocks, f"movingAverage SQLite DB (auth.db:scan_results, {len(stocks)} stocks)"
                    except Exception:
                        pass
            return None, None

        active_port, status_data = get_scan_status()

        if status_data:
            is_scanning = status_data.get("isScanning", False)
            processed = status_data.get("processedCount", 0)
            total = status_data.get("totalStocks", 0)

            # 1. If currently scanning, wait until complete if wait_for_completion=True
            if is_scanning:
                if not wait_for_completion:
                    log_event("INFO", f"Moving-average scan is currently in progress ({processed}/{total} stocks). Awaiting 100% completion before ranking and trading.")
                    return [], f"moving-average scan in progress ({processed}/{total})"

                log_event("INFO", f"Moving-average universe scan is currently in progress ({processed}/{total} stocks). Bot will wait until all stocks are scanned (waiting 1 minute between checks)...")
                start_wait = time.time()
                while time.time() - start_wait < max_wait_seconds and not self.stop_requested:
                    _interruptible_sleep(poll_interval_seconds)
                    if self.stop_requested:
                        break
                    _, cur_status = get_scan_status()
                    if not cur_status:
                        break
                    cur_proc = cur_status.get("processedCount", 0)
                    cur_scanning = cur_status.get("isScanning", False)
                    if not cur_scanning:
                        log_event("SUCCESS", f"Universe scan completed! {cur_proc}/{total} stocks processed. Compiling full list for ranking...")
                        break
                    log_event("INFO", f"Still waiting for scan completion: {cur_proc}/{total} stocks processed...")

            # 2. If scan hasn't been started yet (0 stocks in cache), trigger universe scan and wait
            elif processed == 0:
                if wait_for_completion:
                    log_event("INFO", f"No scan data found in universe pipeline. Initiating full scan across all {total} stocks and awaiting completion (waiting 1 minute between checks)...")
                    try:
                        requests.post(f"http://127.0.0.1:{active_port}/api/scan/start", timeout=5.0)
                    except Exception:
                        pass
                    start_wait = time.time()
                    _interruptible_sleep(min(5.0, poll_interval_seconds))
                    while time.time() - start_wait < max_wait_seconds and not self.stop_requested:
                        _interruptible_sleep(poll_interval_seconds)
                        if self.stop_requested:
                            break
                        _, cur_status = get_scan_status()
                        if not cur_status:
                            break
                        cur_proc = cur_status.get("processedCount", 0)
                        cur_scanning = cur_status.get("isScanning", False)
                        if not cur_scanning and cur_proc > 0:
                            log_event("SUCCESS", f"Universe scan completed! {cur_proc}/{total} stocks processed. Compiling full list for ranking...")
                            break
                        log_event("INFO", f"Still waiting for scan completion: {cur_proc}/{total} stocks processed...")

        # 3. Retrieve completed scan results from Node.js in-memory live scan API
        if active_port:
            stocks, desc = get_scan_results(active_port)
            if stocks:
                return stocks, desc

        # 4. Try SQLite DB scan_results table in movingAverage/auth.db
        stocks, desc = get_db_results()
        if stocks:
            return stocks, desc

        # NO FALLBACK: strictly use universe code
        log_event("WARNING", "Universe scan feed returned 0 stocks. The bot requires a completed moving-average universe scan before opening trades.")
        return [], "No universe scan data available"

    def _scan_and_enter(self, candidate_stocks=None):
        """
        Full-Scan-First Multi-Factor Ranking Engine:
        1. Evaluates ALL candidates across the scan universe first before opening any trades.
        2. Ranks passing candidates by composite score (Headroom 35%, Market Cap 25%, RSI 20%, Volume 20%).
        3. Logs the top opportunities leaderboard for full transparency.
        4. Prioritizes buying the highest-ranked candidates first up to portfolio capacity.
        """
        source_label = "GUI payload"
        stocks_to_scan = candidate_stocks or []

        if not stocks_to_scan:
            stocks_to_scan, source_label = self.fetch_live_scan_candidates()

        if not stocks_to_scan:
            log_event("WARNING", "Live scan feed is currently empty. Start the moving-average scanner or provide candidate stocks.")
            return

        log_event("INFO", f"Live scan feed: Initiating full scan across {len(stocks_to_scan)} candidate stocks from {source_label}.")

        # PHASE 1: Full Candidate Evaluation Scan
        open_symbols = {p["symbol"] for p in get_open_positions()}
        qualifying_candidates = []
        rejection_samples = []

        for stock in stocks_to_scan:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            # Skip stocks already held in open positions
            if symbol in open_symbols:
                continue

            is_valid, reason = StrategyEngine.evaluate_entry(stock)
            if is_valid:
                rank_score, breakdown = StrategyEngine.calculate_rank_score(stock)
                qualifying_candidates.append({
                    "stock": stock,
                    "symbol": symbol,
                    "reason": reason,
                    "rank_score": rank_score,
                    "breakdown": breakdown
                })
            else:
                if len(rejection_samples) < 4:
                    rejection_samples.append(f"{symbol}: {reason}")

        if not qualifying_candidates:
            sample_txt = " | ".join(rejection_samples) if rejection_samples else "all evaluated"
            log_event("INFO", f"Full scan complete: Evaluated {len(stocks_to_scan)} stocks. 0 met entry criteria. Examples: {sample_txt}")
            return

        # PHASE 2: Multi-Factor Ranking & Leaderboard Prioritization
        qualifying_candidates.sort(key=lambda c: c["rank_score"], reverse=True)

        leaderboard_items = []
        for idx, c in enumerate(qualifying_candidates[:5], 1):
            b = c["breakdown"]
            hr_str = f"+{b['headroom_pct']:.1f}%" if b['headroom_pct'] else "N/A"
            rsi_str = f"{b['rsi']:.1f}" if b['rsi'] else "N/A"
            leaderboard_items.append(f"#{idx} {c['symbol']} ({b['total_score']} pts | {b['mcap_tier']} | Room: {hr_str} | RSI: {rsi_str})")

        log_event("INFO", f"Full scan ranked {len(qualifying_candidates)} qualified opportunities. Leaderboard: " + " | ".join(leaderboard_items))

        # PHASE 3: Prioritized Execution for Highest-Ranked Candidates First
        trades_opened = 0
        for rank_idx, candidate in enumerate(qualifying_candidates, 1):
            strategy_type, strat_reason = RiskManager.determine_next_strategy()
            if not strategy_type:
                log_event("INFO", f"Strategy capacity reached: {strat_reason}")
                break

            stock = candidate["stock"]
            symbol = candidate["symbol"]
            rank_score = candidate["rank_score"]
            breakdown = candidate["breakdown"]

            # Re-check active open symbols to avoid concurrent race conditions
            current_open = {p["symbol"] for p in get_open_positions()}
            if symbol in current_open:
                continue

            price = float(stock.get("price") or stock.get("currentPrice") or 0.0)
            qty = RiskManager.calculate_position_size(price, strategy_type=strategy_type)
            if qty <= 0:
                continue

            order_res = self.client.place_buy_order(symbol, qty, price)
            if order_res.get("status") == "SUCCESS":
                exec_price = float(order_res.get("executed_price", price))
                stop_loss = round(exec_price * (1.0 - (BotConfig.HARD_STOP_LOSS_PCT / 100.0)), 2)
                invested = round(qty * exec_price, 2)

                pos = {
                    "symbol": symbol,
                    "strategy_type": strategy_type,
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
                    "entry_date": datetime.now(IST).strftime("%Y-%m-%d"),
                    "rank_score": rank_score
                }
                save_open_position(pos)

                hr_note = f"+{breakdown['headroom_pct']:.1f}%" if breakdown.get("headroom_pct") else "N/A"
                trade_note = f"A/B [{strategy_type}] (Rank #{rank_idx} Score: {rank_score:.1f}, {breakdown['mcap_tier']}, Room: {hr_note}): {candidate['reason']}"
                record_trade(symbol, "BUY", qty, exec_price, 0.0, 0.0, 0.0, trade_note, strategy_type=strategy_type)

                state = get_bot_state()
                new_cash = max(0.0, state.get("available_cash", BotConfig.INITIAL_CAPITAL) - invested)
                update_bot_state(available_cash=new_cash)

                strat_label = "One-Shot Lump Sum (₹2.5L)" if strategy_type == "ONE_SHOT" else "Tranche Averaging (Shot 1/5, ₹50k)"
                log_event("SUCCESS", f"Opened new [{strat_label}] in #{rank_idx}-Ranked {symbol} (Rank Score: {rank_score:.1f}, Tier: {breakdown['mcap_tier']}, Headroom: {hr_note}, RSI: {breakdown.get('rsi')}): {qty} shares @ ₹{exec_price:.2f} (Total: ₹{invested:.2f}). SL set at ₹{stop_loss:.2f}")
                trades_opened += 1

    def compute_performance_matrix(self):
        """
        Computes side-by-side performance analytics for A/B Testing:
        Tranche Averaging (₹50k shots up to ₹2.5L) vs One-Shot (₹2.5L lump-sum).
        """
        all_trades = get_trades(limit=500)
        open_positions = get_open_positions()

        def analyze_strategy(strat_key):
            strat_trades = [t for t in all_trades if t.get("strategy_type", "TRANCHE_AVERAGING") == strat_key]
            strat_positions = [p for p in open_positions if p.get("strategy_type", "TRANCHE_AVERAGING") == strat_key]

            # Closed/Partial sell trades
            sell_trades = [t for t in strat_trades if "SELL" in t.get("trade_type", "")]
            winning_trades = [t for t in sell_trades if (t.get("realized_pnl") or 0.0) > 0]
            losing_trades = [t for t in sell_trades if (t.get("realized_pnl") or 0.0) < 0]

            total_trades_count = len(sell_trades)
            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            win_rate = round((win_count / total_trades_count * 100.0), 1) if total_trades_count > 0 else 0.0

            realized_pnl = sum((t.get("realized_pnl") or 0.0) for t in sell_trades)
            gross_pnl = sum((t.get("gross_pnl") or t.get("realized_pnl") or 0.0) for t in sell_trades)
            total_charges = sum((t.get("total_charges") or 0.0) for t in sell_trades)
            gross_profit = sum((t.get("realized_pnl") or 0.0) for t in winning_trades)
            gross_loss = abs(sum((t.get("realized_pnl") or 0.0) for t in losing_trades))

            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)
            avg_return_pct = round(sum((t.get("pnl_percent") or 0.0) for t in sell_trades) / total_trades_count, 2) if total_trades_count > 0 else 0.0

            # Unrealized P&L from open positions
            unrealized_pnl = sum(((p["current_price"] - p["buy_price"]) * p["current_qty"]) for p in strat_positions)
            active_invested = sum(p.get("invested_amount") or (p["buy_price"] * p["current_qty"]) for p in strat_positions)

            net_pnl = realized_pnl + unrealized_pnl

            # Best & worst trade
            best_trade = max([t.get("realized_pnl", 0.0) for t in sell_trades], default=0.0)
            worst_trade = min([t.get("realized_pnl", 0.0) for t in sell_trades], default=0.0)

            return {
                "strategyType": strat_key,
                "activePositions": len(strat_positions),
                "maxSlots": 4,
                "capitalInvested": round(active_invested, 2),
                "investedCapital": round(active_invested, 2),
                "totalCompletedTrades": total_trades_count,
                "winningTrades": win_count,
                "losingTrades": loss_count,
                "winRatePct": win_rate or 0.0,
                "grossPnl": round(gross_pnl, 2),
                "totalCharges": round(total_charges, 2),
                "realizedPnl": round(realized_pnl, 2),
                "unrealizedPnl": round(unrealized_pnl, 2),
                "netPnl": round(net_pnl, 2),
                "grossProfit": round(gross_profit, 2),
                "grossLoss": round(gross_loss, 2),
                "profitFactor": profit_factor or 0.0,
                "avgReturnPct": avg_return_pct or 0.0,
                "bestTradePnl": round(best_trade, 2) if best_trade is not None else 0.0,
                "worstTradePnl": round(worst_trade, 2) if worst_trade is not None else 0.0
            }

        tranche_metrics = analyze_strategy("TRANCHE_AVERAGING")
        one_shot_metrics = analyze_strategy("ONE_SHOT")

        # Determine leader
        if tranche_metrics["netPnl"] > one_shot_metrics["netPnl"]:
            leader = "TRANCHE_AVERAGING"
            leader_label = "Tranche Averaging (Scaling In)"
            delta_pnl = round(tranche_metrics["netPnl"] - one_shot_metrics["netPnl"], 2)
        elif one_shot_metrics["netPnl"] > tranche_metrics["netPnl"]:
            leader = "ONE_SHOT"
            leader_label = "One-Shot (Lump Sum)"
            delta_pnl = round(one_shot_metrics["netPnl"] - tranche_metrics["netPnl"], 2)
        else:
            leader = "TIE"
            leader_label = "Performance Equal / Tie"
            delta_pnl = 0.0

        return {
            "trancheAveraging": tranche_metrics,
            "oneShot": one_shot_metrics,
            "leader": leader,
            "leaderLabel": leader_label,
            "deltaPnl": delta_pnl,
            "sampleDaysCount": 0 # Increments as bot runs
        }

    def get_status(self):
        """Returns full snapshot of Auto-Trader state for the frontend GUI with charges details."""
        from .charges import calculate_charges

        state = get_bot_state()
        positions = get_open_positions()
        trades = get_trades(limit=50)
        logs = get_recent_logs(limit=40)
        perf_matrix = self.compute_performance_matrix()

        # Enrich active positions with live estimated charges and net floating PnL
        enriched_positions = []
        for p in positions:
            p_dict = dict(p)
            bp = float(p_dict.get("buy_price") or 0.0)
            cp = float(p_dict.get("current_price") or bp)
            qty = int(p_dict.get("current_qty") or 0)
            
            charges_data = calculate_charges(bp, cp, qty, is_delivery=True)
            gross_float = round((cp - bp) * qty, 2)
            net_float = round(gross_float - charges_data["total_charges"], 2)
            net_float_pct = round((net_float / (bp * qty)) * 100.0, 2) if (bp * qty) > 0 else 0.0

            p_dict["estimated_charges"] = charges_data["total_charges"]
            p_dict["charges_breakdown"] = charges_data
            p_dict["gross_pnl"] = gross_float
            p_dict["net_pnl"] = net_float
            p_dict["net_pnl_percent"] = net_float_pct
            p_dict["breakeven_price"] = round(bp + charges_data["breakeven_diff"], 2)
            enriched_positions.append(p_dict)

        # Aggregate financial metrics
        total_invested = sum(p["current_price"] * p["current_qty"] for p in enriched_positions)
        gross_unrealized_pnl = sum(p["gross_pnl"] for p in enriched_positions)
        est_open_charges = sum(p["estimated_charges"] for p in enriched_positions)
        net_unrealized_pnl = sum(p["net_pnl"] for p in enriched_positions)

        sell_trades = [t for t in trades if "SELL" in t.get("trade_type", "")]
        gross_realized_pnl = sum((t.get("gross_pnl") or t.get("realized_pnl") or 0.0) for t in sell_trades)
        total_charges_paid = sum((t.get("total_charges") or 0.0) for t in sell_trades)
        net_realized_pnl = sum((t.get("net_pnl") or t.get("realized_pnl") or 0.0) for t in sell_trades)

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
            "unrealizedPnl": round(net_unrealized_pnl, 2),
            "grossUnrealizedPnl": round(gross_unrealized_pnl, 2),
            "estimatedOpenCharges": round(est_open_charges, 2),
            "realizedPnl": round(net_realized_pnl, 2),
            "grossRealizedPnl": round(gross_realized_pnl, 2),
            "totalChargesPaid": round(total_charges_paid, 2),
            "netTotalPnl": round(net_realized_pnl + net_unrealized_pnl, 2),
            "maxPositions": int(state.get("max_positions", BotConfig.MAX_ACTIVE_POSITIONS)),
            "partialProfitPct": float(state.get("partial_profit_pct", 30.0)),
            "stagnationDays": int(state.get("stagnation_days", 3)),
            "minHeadroomTo100Dema": float(state.get("min_headroom_to_100_dema", BotConfig.MIN_HEADROOM_TO_100_DEMA)),
            "lastScanTime": self.last_scan_time,
            "positions": enriched_positions,
            "trades": trades,
            "logs": logs,
            "performanceMatrix": perf_matrix
        }

# Global singleton runner instance
bot_runner = BotRunner()
