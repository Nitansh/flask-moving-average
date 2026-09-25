"""
SQLite Database Persistence for Auto-Trader
Tracks bot runtime configuration, open positions, completed trades, and audit logs.
"""
import sqlite3
import os
import json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "autotrader.sqlite")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    with conn:
        # 1. Bot State / Config
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                id INTEGER PRIMARY KEY,
                is_running INTEGER DEFAULT 0,
                mode TEXT DEFAULT 'PAPER',
                total_capital REAL DEFAULT 500000.0,
                available_cash REAL DEFAULT 500000.0,
                bucket_capital REAL DEFAULT 100000.0,
                tranche_size REAL DEFAULT 100000.0,
                max_positions INTEGER DEFAULT 5,
                partial_profit_pct REAL DEFAULT 30.0,
                stagnation_days INTEGER DEFAULT 3,
                min_headroom_to_100_dema REAL DEFAULT 4.0,
                updated_at TEXT
            )
        """)

        # Add bucket_capital / tranche_size / min_headroom columns if missing in existing table
        try:
            conn.execute("ALTER TABLE bot_state ADD COLUMN bucket_capital REAL DEFAULT 100000.0")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_state ADD COLUMN tranche_size REAL DEFAULT 100000.0")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_state ADD COLUMN min_headroom_to_100_dema REAL DEFAULT 4.0")
        except Exception: pass

        # Seed initial row if empty, or migrate legacy 20L default if no active positions
        row = conn.execute("SELECT id, total_capital FROM bot_state WHERE id = 1").fetchone()
        if not row:
            conn.execute("""
                INSERT INTO bot_state (id, is_running, mode, total_capital, available_cash, bucket_capital, tranche_size, max_positions, partial_profit_pct, stagnation_days, min_headroom_to_100_dema, updated_at)
                VALUES (1, 0, 'PAPER', 500000.0, 500000.0, 100000.0, 100000.0, 5, 30.0, 3, 4.0, ?)
            """, (datetime.now(timezone.utc).isoformat(),))
        elif row["total_capital"] == 2000000.0:
            open_pos = conn.execute("SELECT count(*) as cnt FROM bot_positions").fetchone()
            if not open_pos or open_pos["cnt"] == 0:
                conn.execute("""
                    UPDATE bot_state
                    SET total_capital = 500000.0,
                        available_cash = 500000.0,
                        bucket_capital = 100000.0,
                        tranche_size = 100000.0,
                        max_positions = 5,
                        updated_at = ?
                    WHERE id = 1
                """, (datetime.now(timezone.utc).isoformat(),))

        # 2. Open Positions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE,
                strategy_type TEXT DEFAULT 'TRANCHE_AVERAGING', -- TRANCHE_AVERAGING, ONE_SHOT
                initial_qty INTEGER,
                current_qty INTEGER,
                buy_price REAL,
                current_price REAL,
                stop_loss REAL,
                dema_100 REAL,
                dema_200 REAL,
                dema_20 REAL,
                dema_50 REAL,
                phase TEXT DEFAULT 'ENTRY', -- ENTRY, TARGET_1_LOCKED, RUNNER_ACTIVE
                tranches_count INTEGER DEFAULT 1,
                invested_amount REAL DEFAULT 0.0,
                days_at_100_dema INTEGER DEFAULT 0,
                last_dema_100_check_date TEXT,
                entry_date TEXT,
                updated_at TEXT
            )
        """)

        # Add tranches_count, invested_amount, strategy_type if missing in existing table
        try:
            conn.execute("ALTER TABLE bot_positions ADD COLUMN tranches_count INTEGER DEFAULT 1")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_positions ADD COLUMN invested_amount REAL DEFAULT 0.0")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_positions ADD COLUMN strategy_type TEXT DEFAULT 'TRANCHE_AVERAGING'")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_positions ADD COLUMN last_tranche_time TEXT")
        except Exception: pass

        # 3. Completed Trades
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                strategy_type TEXT DEFAULT 'TRANCHE_AVERAGING', -- TRANCHE_AVERAGING, ONE_SHOT
                trade_type TEXT, -- BUY, PARTIAL_SELL, FULL_SELL, BUY_TRANCHE
                quantity INTEGER,
                entry_price REAL,
                exit_price REAL,
                gross_pnl REAL DEFAULT 0.0,
                total_charges REAL DEFAULT 0.0,
                net_pnl REAL DEFAULT 0.0,
                charges_breakdown TEXT,
                realized_pnl REAL,
                pnl_percent REAL,
                reason TEXT,
                executed_at TEXT
            )
        """)

        try:
            conn.execute("ALTER TABLE bot_trades ADD COLUMN strategy_type TEXT DEFAULT 'TRANCHE_AVERAGING'")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_trades ADD COLUMN gross_pnl REAL DEFAULT 0.0")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_trades ADD COLUMN total_charges REAL DEFAULT 0.0")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_trades ADD COLUMN net_pnl REAL DEFAULT 0.0")
        except Exception: pass
        try:
            conn.execute("ALTER TABLE bot_trades ADD COLUMN charges_breakdown TEXT")
        except Exception: pass

        # 4. Chronological Audit Logs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT DEFAULT 'INFO', -- INFO, SUCCESS, WARNING, ERROR
                message TEXT,
                details TEXT,
                created_at TEXT
            )
        """)

        # 5. Opportunity Rankings Leaderboard
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rank INTEGER,
                symbol TEXT,
                rank_score REAL,
                mcap_tier TEXT,
                price REAL,
                headroom_pct REAL,
                dema_100 REAL,
                rsi REAL,
                volume INTEGER,
                strategy_type TEXT,
                status TEXT, -- SELECTED_TO_BUY, BOUGHT, QUEUED_CAPACITY, QUALIFIED
                action_reason TEXT,
                details TEXT,
                created_at TEXT
            )
        """)

init_db()

def log_event(level, message, details=None):
    """Inserts a log entry into bot_logs and trims older logs."""
    try:
        conn = get_connection()
        with conn:
            details_str = json.dumps(details) if details and not isinstance(details, str) else details
            conn.execute(
                "INSERT INTO bot_logs (level, message, details, created_at) VALUES (?, ?, ?, ?)",
                (level, message, details_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            # Retain last 300 logs
            conn.execute("DELETE FROM bot_logs WHERE id NOT IN (SELECT id FROM bot_logs ORDER BY id DESC LIMIT 300)")
    except Exception as e:
        print(f"Error logging bot event: {e}")

def get_bot_state():
    conn = get_connection()
    row = conn.execute("SELECT * FROM bot_state WHERE id = 1").fetchone()
    if row:
        return dict(row)
    return {}

def update_bot_state(**kwargs):
    conn = get_connection()
    fields = []
    values = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    fields.append("updated_at = ?")
    values.append(datetime.now(timezone.utc).isoformat())
    values.append(1)
    query = f"UPDATE bot_state SET {', '.join(fields)} WHERE id = ?"
    with conn:
        conn.execute(query, values)

def get_open_positions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM bot_positions").fetchall()
    return [dict(r) for r in rows]

def save_open_position(pos):
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO bot_positions 
            (symbol, strategy_type, initial_qty, current_qty, buy_price, current_price, stop_loss, dema_100, dema_200, dema_20, dema_50, phase, tranches_count, invested_amount, days_at_100_dema, last_dema_100_check_date, entry_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pos["symbol"], pos.get("strategy_type", "TRANCHE_AVERAGING"),
            pos["initial_qty"], pos["current_qty"], pos["buy_price"], pos["current_price"],
            pos["stop_loss"], pos.get("dema_100"), pos.get("dema_200"), pos.get("dema_20"), pos.get("dema_50"),
            pos.get("phase", "ENTRY"), pos.get("tranches_count", 1), pos.get("invested_amount", 0.0),
            pos.get("days_at_100_dema", 0), pos.get("last_dema_100_check_date"),
            pos.get("entry_date", datetime.now().strftime("%Y-%m-%d")), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

def delete_open_position(symbol):
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM bot_positions WHERE symbol = ?", (symbol,))

def record_trade(symbol, trade_type, quantity, entry_price, exit_price, pnl=None, pnl_pct=None, reason="", strategy_type="TRANCHE_AVERAGING", gross_pnl=None, total_charges=None, net_pnl=None, charges_breakdown=None):
    from .charges import calculate_charges
    
    qty = int(quantity) if quantity else 0
    ep = float(entry_price) if entry_price else 0.0
    xp = float(exit_price) if exit_price else 0.0

    if ("SELL" in str(trade_type).upper() or "EXIT" in str(trade_type).upper() or xp > 0) and ep > 0 and xp > 0 and qty > 0:
        calculated_gross = round((xp - ep) * qty, 2)
        charges_data = calculate_charges(ep, xp, qty, is_delivery=True)
        calculated_charges = charges_data["total_charges"]
        calculated_net = round(calculated_gross - calculated_charges, 2)
        calc_pct = round((calculated_net / (ep * qty)) * 100.0, 2)

        final_gross = round(gross_pnl if gross_pnl is not None else calculated_gross, 2)
        final_charges = round(total_charges if total_charges is not None else calculated_charges, 2)
        final_net = round(net_pnl if net_pnl is not None else calculated_net, 2)
        final_pct = pnl_pct if pnl_pct is not None else calc_pct
        final_breakdown = charges_breakdown if charges_breakdown is not None else json.dumps(charges_data)
        final_realized = final_net
    else:
        final_gross = round(pnl if pnl is not None else 0.0, 2)
        final_charges = 0.0
        final_net = final_gross
        final_pct = pnl_pct if pnl_pct is not None else 0.0
        final_breakdown = json.dumps({})
        final_realized = final_gross

    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO bot_trades (
                symbol, strategy_type, trade_type, quantity, entry_price, exit_price, 
                gross_pnl, total_charges, net_pnl, charges_breakdown, realized_pnl, pnl_percent, reason, executed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, strategy_type, trade_type, qty, ep, xp,
            final_gross, final_charges, final_net, final_breakdown, final_realized, final_pct, reason,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

def get_trades(limit=50):
    conn = get_connection()
    if limit and int(limit) > 0:
        rows = conn.execute("SELECT * FROM bot_trades ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM bot_trades ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

def get_trade_analytics():
    """
    Computes comprehensive performance and execution analytics across all completed trades
    for fine-tuning the trading algorithm.
    """
    trades = get_trades(limit=None)
    
    total_trades = len(trades)
    completed_exits = [t for t in trades if t.get("trade_type") not in ("BUY", "BUY_TRANCHE")]
    buys = [t for t in trades if t.get("trade_type") in ("BUY", "BUY_TRANCHE")]

    exit_count = len(completed_exits)
    winning_trades = [t for t in completed_exits if (t.get("net_pnl") or t.get("realized_pnl") or 0.0) > 0]
    losing_trades = [t for t in completed_exits if (t.get("net_pnl") or t.get("realized_pnl") or 0.0) < 0]
    scratch_trades = [t for t in completed_exits if (t.get("net_pnl") or t.get("realized_pnl") or 0.0) == 0]

    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    win_rate_pct = round((win_count / exit_count) * 100.0, 1) if exit_count > 0 else 0.0

    total_gross_pnl = round(sum(float(t.get("gross_pnl") or 0.0) for t in completed_exits), 2)
    total_charges_paid = round(sum(float(t.get("total_charges") or 0.0) for t in completed_exits), 2)
    total_net_pnl = round(sum(float(t.get("net_pnl") or t.get("realized_pnl") or 0.0) for t in completed_exits), 2)

    total_gains = sum(float(t.get("net_pnl") or t.get("realized_pnl") or 0.0) for t in winning_trades)
    total_losses = abs(sum(float(t.get("net_pnl") or t.get("realized_pnl") or 0.0) for t in losing_trades))

    profit_factor = round(total_gains / total_losses, 2) if total_losses > 0 else (99.9 if total_gains > 0 else 0.0)

    avg_trade_pnl = round(total_net_pnl / exit_count, 2) if exit_count > 0 else 0.0
    avg_win = round(total_gains / win_count, 2) if win_count > 0 else 0.0
    avg_loss = round(-total_losses / loss_count, 2) if loss_count > 0 else 0.0
    win_loss_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0.0

    pnl_pcts = [float(t.get("pnl_percent") or 0.0) for t in completed_exits]
    avg_return_pct = round(sum(pnl_pcts) / exit_count, 2) if exit_count > 0 else 0.0

    best_trade = max(completed_exits, key=lambda t: float(t.get("net_pnl") or t.get("realized_pnl") or 0.0), default=None)
    worst_trade = min(completed_exits, key=lambda t: float(t.get("net_pnl") or t.get("realized_pnl") or 0.0), default=None)

    strategy_breakdown = {}
    for st in ("ONE_SHOT", "TRANCHE_AVERAGING"):
        st_exits = [t for t in completed_exits if t.get("strategy_type") == st]
        st_wins = [t for t in st_exits if (t.get("net_pnl") or t.get("realized_pnl") or 0.0) > 0]
        st_cnt = len(st_exits)
        st_net = round(sum(float(t.get("net_pnl") or t.get("realized_pnl") or 0.0) for t in st_exits), 2)
        st_charges = round(sum(float(t.get("total_charges") or 0.0) for t in st_exits), 2)
        strategy_breakdown[st] = {
            "total_exits": st_cnt,
            "win_count": len(st_wins),
            "loss_count": st_cnt - len(st_wins),
            "win_rate_pct": round((len(st_wins) / st_cnt) * 100.0, 1) if st_cnt > 0 else 0.0,
            "net_pnl": st_net,
            "total_charges": st_charges
        }

    return {
        "total_recorded_records": total_trades,
        "total_buys": len(buys),
        "completed_exits": exit_count,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "scratch_trades": len(scratch_trades),
        "win_rate_pct": win_rate_pct,
        "gross_realized_pnl": total_gross_pnl,
        "total_charges_paid": total_charges_paid,
        "net_realized_pnl": total_net_pnl,
        "profit_factor": profit_factor,
        "avg_trade_pnl": avg_trade_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "win_loss_ratio": win_loss_ratio,
        "avg_return_pct": avg_return_pct,
        "best_trade": {
            "symbol": best_trade.get("symbol") if best_trade else None,
            "net_pnl": float(best_trade.get("net_pnl") or best_trade.get("realized_pnl") or 0.0) if best_trade else 0.0,
            "pnl_pct": float(best_trade.get("pnl_percent") or 0.0) if best_trade else 0.0,
            "date": best_trade.get("executed_at") if best_trade else None
        } if best_trade else None,
        "worst_trade": {
            "symbol": worst_trade.get("symbol") if worst_trade else None,
            "net_pnl": float(worst_trade.get("net_pnl") or worst_trade.get("realized_pnl") or 0.0) if worst_trade else 0.0,
            "pnl_pct": float(worst_trade.get("pnl_percent") or 0.0) if worst_trade else 0.0,
            "date": worst_trade.get("executed_at") if worst_trade else None
        } if worst_trade else None,
        "strategy_breakdown": strategy_breakdown
    }

def generate_trades_csv(trades=None):
    """
    Generates an RFC-4180 compliant CSV string for trade history and algo fine-tuning.
    """
    import csv
    import io
    
    if trades is None:
        trades = get_trades(limit=None)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Trade ID",
        "Executed At",
        "Symbol",
        "Action / Type",
        "Strategy",
        "Quantity",
        "Entry Price (INR)",
        "Exit Price (INR)",
        "Turnover (INR)",
        "Gross PnL (INR)",
        "Brokerage (INR)",
        "STT (INR)",
        "Exchange Txn (INR)",
        "GST (INR)",
        "SEBI Fees (INR)",
        "Stamp Duty (INR)",
        "DP Charges (INR)",
        "Total Charges (INR)",
        "Net Realized PnL (INR)",
        "Return (%)",
        "Execution Reason / Trigger"
    ])

    for t in trades:
        qty = int(t.get("quantity") or 0)
        ep = float(t.get("entry_price") or 0.0)
        xp = float(t.get("exit_price") or 0.0)
        turnover = round((xp * qty) if xp > 0 else (ep * qty), 2)
        gross = float(t.get("gross_pnl") or 0.0)
        charges = float(t.get("total_charges") or 0.0)
        net = float(t.get("net_pnl") or t.get("realized_pnl") or 0.0)
        pnl_pct = float(t.get("pnl_percent") or 0.0)

        cb = {}
        raw_cb = t.get("charges_breakdown")
        if raw_cb:
            try:
                cb = json.loads(raw_cb) if isinstance(raw_cb, str) else raw_cb
            except Exception:
                pass

        writer.writerow([
            t.get("id"),
            t.get("executed_at"),
            t.get("symbol"),
            t.get("trade_type"),
            t.get("strategy_type", "ONE_SHOT"),
            qty,
            f"{ep:.2f}",
            f"{xp:.2f}" if xp > 0 else "",
            f"{turnover:.2f}",
            f"{gross:.2f}",
            f"{float(cb.get('brokerage', 0.0)):.2f}",
            f"{float(cb.get('stt', 0.0)):.2f}",
            f"{float(cb.get('exchange_txn', 0.0)):.2f}",
            f"{float(cb.get('gst', 0.0)):.2f}",
            f"{float(cb.get('sebi_charges', 0.0)):.2f}",
            f"{float(cb.get('stamp_duty', 0.0)):.2f}",
            f"{float(cb.get('dp_charges', 0.0)):.2f}",
            f"{charges:.2f}",
            f"{net:.2f}",
            f"{pnl_pct:.2f}%" if xp > 0 else "",
            t.get("reason", "")
        ])

    return output.getvalue()

def get_recent_logs(limit=100):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM bot_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]

def save_rankings(rankings_list):
    """Saves the latest multi-factor ranked opportunities into bot_rankings."""
    try:
        conn = get_connection()
        with conn:
            conn.execute("DELETE FROM bot_rankings")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for r in rankings_list:
                details_json = json.dumps(r.get("breakdown") or {})
                conn.execute("""
                    INSERT INTO bot_rankings (rank, symbol, rank_score, mcap_tier, price, headroom_pct, dema_100, rsi, volume, strategy_type, status, action_reason, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r.get("rank", 0),
                    r.get("symbol", ""),
                    float(r.get("rank_score", 0.0)),
                    r.get("mcap_tier", "Smallcap"),
                    float(r.get("price", 0.0)),
                    float(r.get("headroom_pct", 0.0)),
                    float(r.get("dema_100", 0.0)),
                    float(r.get("rsi", 0.0)),
                    int(r.get("volume", 0)),
                    r.get("strategy_type", "TRANCHE_AVERAGING"),
                    r.get("status", "QUALIFIED"),
                    r.get("action_reason", ""),
                    details_json,
                    now_str
                ))
    except Exception as e:
        print(f"Error saving rankings: {e}")

def get_rankings(limit=100):
    """Retrieves the latest ranked opportunities from bot_rankings."""
    try:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM bot_rankings ORDER BY rank ASC LIMIT ?", (limit,)).fetchall()
        rankings = []
        for r in rows:
            d = dict(r)
            d["composite_score"] = d.get("rank_score", 0.0)
            d["current_price"] = d.get("price", 0.0)
            d["rationale"] = d.get("action_reason", "")
            try:
                d["breakdown"] = json.loads(d["details"]) if d.get("details") else {}
            except Exception:
                d["breakdown"] = {}
            d["crossover_type"] = d["breakdown"].get("crossover_type", "NO_CROSSOVER")
            d["crossover_label"] = d["breakdown"].get("crossover_label", "")
            d["has_golden_cross"] = d["crossover_type"] in ["GOLDEN_CROSS", "GOLDEN_CROSS_APPROACHING"]
            d["mcap_tier"] = str(d.get("mcap_tier") or d["breakdown"].get("mcap_tier", "SMALLCAP")).upper()
            hr_val = float(d.get("headroom_pct") or 0.0)
            if d["has_golden_cross"] and hr_val >= 4.0 and d["mcap_tier"] in ["LARGECAP", "MIDCAP"]:
                rankings.append(d)
        for idx, item in enumerate(rankings, 1):
            item["rank"] = idx
        return rankings
    except Exception as e:
        print(f"Error getting rankings: {e}")
        return []

def reset_autotrader(initial_capital=None):
    """
    Resets the Auto-Trader database to pristine initial testing state:
    - Clears all open positions
    - Clears all completed trades
    - Clears all audit logs
    - Clears all opportunity rankings
    - Resets bot state: available_cash = initial_capital, total_capital = initial_capital, is_running = 0
    """
    from .config import BotConfig
    init_cap = float(initial_capital) if initial_capital is not None else BotConfig.INITIAL_CAPITAL
    bucket_cap = BotConfig.BUCKET_CAPITAL_PER_STOCK
    tranche_sz = BotConfig.TRANCHE_SIZE
    max_pos = BotConfig.MAX_ACTIVE_POSITIONS

    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM bot_positions")
        conn.execute("DELETE FROM bot_trades")
        conn.execute("DELETE FROM bot_logs")
        conn.execute("DELETE FROM bot_rankings")
        conn.execute("""
            UPDATE bot_state
            SET is_running = 0,
                available_cash = ?,
                total_capital = ?,
                bucket_capital = ?,
                tranche_size = ?,
                max_positions = ?,
                updated_at = ?
            WHERE id = 1
        """, (init_cap, init_cap, bucket_cap, tranche_sz, max_pos, datetime.now(timezone.utc).isoformat()))

    log_event("INFO", "Auto-Trader reset to initial testing state.", {"initial_capital": init_cap, "bucket_capital": bucket_cap, "max_positions": max_pos})
    return True

