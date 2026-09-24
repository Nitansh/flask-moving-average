"""
DEMA Stage-Rider Strategy Engine
Implements the Asymmetric Profit Strategy:
- Locks 30% profit at 100 DEMA resistance & moves SL to breakeven
- Detects stagnation at 100 DEMA (> 3 days)
- Activates Mega-Runner mode upon 200 DEMA breakout (trailing 20 DEMA)
"""
from datetime import datetime
from .config import BotConfig

class StrategyEngine:
    @staticmethod
    def _extract_stock_values(stock_data):
        def _get_val(*keys):
            for k in keys:
                v = stock_data.get(k)
                if v is not None and v != "" and v != 0:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
            return 0.0

        price = _get_val("price", "currentPrice", "close", "ltp", "lastPrice")
        dema_20 = _get_val("DMA_20", "dema_20", "dma20", "DMA20", "20_DEMA")
        dema_50 = _get_val("DMA_50", "dema_50", "dma50", "DMA50", "50_DEMA")
        dema_100 = _get_val("DMA_100", "dema_100", "dma100", "DMA100", "100_DEMA")
        dema_200 = _get_val("DMA_200", "dema_200", "dma200", "DMA200", "200_DEMA")
        rsi = _get_val("rsi", "RSI", "rsi14", "RSI_14")
        return price, dema_20, dema_50, dema_100, dema_200, rsi

    @staticmethod
    def evaluate_entry(stock_data):
        """
        Evaluates whether a stock meets all BUY entry criteria:
        1. Price > 20 DEMA > 50 DEMA
        2. RSI between 45 and 68 (momentum expansion zone)
        3. Upside room to 100 DEMA (or 200 DEMA if above 100) is at least +3.0%
        """
        price, dema_20, dema_50, dema_100, dema_200, rsi = StrategyEngine._extract_stock_values(stock_data)

        if not (price and dema_20 and dema_50):
            return False, "Missing required Price, 20 DEMA, or 50 DEMA values"

        # 1. Scanner-Confirmed In-Range Setups (isBullish / isGoldenCrossApproaching)
        is_bullish_flag = stock_data.get("isBullish") in [True, "true"]
        is_gc_flag = stock_data.get("isGoldenCrossApproaching") in [True, "true"]

        if is_bullish_flag or is_gc_flag:
            if rsi and rsi > 75.0:
                return False, f"RSI {rsi:.1f} indicates extreme overbought exhaustion (> 75)"
            label = "Bullish In-Range" if is_bullish_flag else "Golden Cross Approaching"
            return True, f"Moving-Average Live Scanner Confirmed: {label}"

        # 2. General Technical Entry Filter (for stocks not explicitly flagged by scanner)
        trend_aligned = (price > dema_20 and price > dema_50) or (price > dema_20 > dema_50)
        if not trend_aligned:
            return False, f"Not in bullish alignment (Price: ₹{price:.1f}, 20D: ₹{dema_20:.1f}, 50D: ₹{dema_50:.1f})"

        # RSI Momentum Filter (40 to 70)
        if rsi and not (BotConfig.RSI_MIN <= rsi <= BotConfig.RSI_MAX):
            return False, f"RSI {rsi:.1f} outside optimal momentum range ({BotConfig.RSI_MIN}-{BotConfig.RSI_MAX})"

        # Minimum Headroom to Resistance (Risk-to-Reward)
        if dema_100 and dema_100 > price:
            headroom_pct = ((dema_100 - price) / price) * 100.0
            if headroom_pct < BotConfig.MIN_HEADROOM_TO_100_DEMA:
                return False, f"Insufficient headroom to 100 DEMA (+{headroom_pct:.1f}% < +{BotConfig.MIN_HEADROOM_TO_100_DEMA}%)"

        return True, "Strong momentum setup with favorable risk-to-reward"

    @staticmethod
    def evaluate_scale_in(position, current_price, current_dema, rsi=None):
        """
        Evaluates whether an active position qualifies for an additional ₹50,000 averaging tranche.
        Criteria:
        1. Position has not reached max tranches (5 tranches = ₹2.5L).
        2. Scenario A (Bounce on 20 DEMA Support): Price pulled back to within 0.0% - 1.5% of 20 DEMA while > 50 DEMA.
        3. Scenario B (Momentum Pyramiding): Price is >= +2.0% above current buy_price with upside headroom to 100 DEMA.
        4. Scenario C (100 DEMA Breakout): Price is breaking cleanly above 100 DEMA (> 101%) targeting 200 DEMA.
        """
        tranches_count = int(position.get("tranches_count", 1))
        if tranches_count >= BotConfig.MAX_TRANCHES_PER_STOCK:
            return False, "Maximum 5 tranches (₹2.5L) already deployed"

        dema_20 = current_dema.get("dema_20") or position.get("dema_20")
        dema_50 = current_dema.get("dema_50") or position.get("dema_50")
        dema_100 = current_dema.get("dema_100") or position.get("dema_100")
        dema_200 = current_dema.get("dema_200") or position.get("dema_200")
        buy_price = position["buy_price"]

        if not (dema_20 and dema_50):
            return False, "Missing DEMA indicators"

        # Never average down if price broke below 50 DEMA
        if current_price < dema_50:
            return False, "Price below 50 DEMA; cannot average into a breakdown"

        # Scenario A: Healthy pullback to rising 20 DEMA support
        dist_to_20_dema_pct = ((current_price - dema_20) / dema_20) * 100.0
        if 0.0 <= dist_to_20_dema_pct <= 1.5 and dema_20 > dema_50:
            return True, f"Dip-Buy Tranche #{tranches_count + 1}: Testing rising 20 DEMA support (+{dist_to_20_dema_pct:.1f}%)"

        # Scenario B: Pyramiding on strength (+2% from average buy price)
        pnl_pct = ((current_price - buy_price) / buy_price) * 100.0
        if pnl_pct >= 2.0:
            if dema_100 and current_price < (dema_100 * 0.985):
                return True, f"Pyramid Tranche #{tranches_count + 1}: Momentum continuation (+{pnl_pct:.1f}% gain with room to 100 DEMA)"

        # Scenario C: 100 DEMA Breakout confirmation
        if dema_100 and current_price >= (dema_100 * 1.01):
            if dema_200 and ((dema_200 - current_price) / current_price) >= 0.03:
                return True, f"Breakout Tranche #{tranches_count + 1}: Clean 100 DEMA bisect targeting 200 DEMA"

        return False, "No tranche averaging condition met"

    @staticmethod
    def evaluate_exit(position, current_price, current_dema):
        """
        Evaluates an active position against targets, resistances, trailing stops, and stop-loss.
        Returns:
            action: 'NONE', 'PARTIAL_SELL', 'FULL_SELL'
            quantity_ratio: float (0.0 to 1.0)
            new_stop_loss: float or None
            new_phase: str or None
            reason: str
        """
        buy_price = position["buy_price"]
        current_qty = position["current_qty"]
        initial_qty = position["initial_qty"]
        stop_loss = position.get("stop_loss", buy_price * (1 - BotConfig.HARD_STOP_LOSS_PCT / 100.0))
        phase = position.get("phase", "ENTRY")
        days_at_100 = position.get("days_at_100_dema", 0)

        dema_100 = current_dema.get("dema_100") or position.get("dema_100")
        dema_200 = current_dema.get("dema_200") or position.get("dema_200")
        dema_20 = current_dema.get("dema_20") or position.get("dema_20")
        dema_50 = current_dema.get("dema_50") or position.get("dema_50")

        # ----------------------------------------------------
        # 1. HARD STOP-LOSS or BREAK BELOW 50 DEMA
        # ----------------------------------------------------
        if current_price <= stop_loss:
            return {
                "action": "FULL_SELL",
                "ratio": 1.0,
                "reason": f"Stop-Loss hit at ₹{current_price:.2f} (SL: ₹{stop_loss:.2f})",
                "new_phase": "STOPPED_OUT"
            }

        if dema_50 and current_price < (dema_50 * 0.995):
            return {
                "action": "FULL_SELL",
                "ratio": 1.0,
                "reason": f"Trend breakdown: Price closed below 50 DEMA (₹{dema_50:.2f})",
                "new_phase": "STOPPED_OUT"
            }

        # ----------------------------------------------------
        # 2. MEGA-RUNNER MODE (Active after 200 DEMA Breakout)
        # ----------------------------------------------------
        if phase == "RUNNER_ACTIVE":
            # Trail with 20 DEMA: Exit only if price drops below 20 DEMA
            if dema_20 and current_price < dema_20:
                return {
                    "action": "FULL_SELL",
                    "ratio": 1.0,
                    "reason": f"Mega-Runner Exit: Closed below trailing 20 DEMA (₹{dema_20:.2f})",
                    "new_phase": "COMPLETED"
                }
            # Dynamically raise stop-loss as 20 DEMA climbs
            updated_sl = max(stop_loss, dema_20 * 0.99) if dema_20 else stop_loss
            return {
                "action": "NONE",
                "ratio": 0.0,
                "new_stop_loss": updated_sl,
                "reason": f"Mega-Runner Active: Riding above 20 DEMA (₹{dema_20:.2f})"
            }

        # ----------------------------------------------------
        # 3. 200 DEMA BREAKOUT CHECK (Trigger Mega-Runner)
        # ----------------------------------------------------
        if dema_200 and current_price >= (dema_200 * (BotConfig.DEMA_200_BREAKOUT_PCT / 100.0)):
            # Stock broke cleanly above 200 DEMA! Transition to Mega-Runner
            new_sl = max(stop_loss, dema_20 or dema_100 or buy_price)
            return {
                "action": "NONE",
                "ratio": 0.0,
                "new_phase": "RUNNER_ACTIVE",
                "new_stop_loss": new_sl,
                "reason": f"🚀 200 DEMA Breakout (> {BotConfig.DEMA_200_BREAKOUT_PCT}%). Activated Mega-Runner Mode trailing 20 DEMA!"
            }

        # ----------------------------------------------------
        # 4. 100 DEMA RESISTANCE & PARTIAL PROFIT LOCKING
        # ----------------------------------------------------
        if dema_100 and phase == "ENTRY":
            resistance_price = dema_100 * (BotConfig.DEMA_100_RESISTANCE_PCT / 100.0)
            breakout_price = dema_100 * (BotConfig.DEMA_200_BREAKOUT_PCT / 100.0)

            # Check if stock has reached 100 DEMA Resistance (99.9%)
            if current_price >= resistance_price and current_price < breakout_price:
                # Sell 30% of the position to lock in profit
                sell_qty = max(1, int(round(initial_qty * (BotConfig.PARTIAL_PROFIT_PCT / 100.0))))
                # Move Stop Loss to Breakeven (+0.5% buffer for brokerage/DP charges)
                breakeven_sl = buy_price * 1.005

                return {
                    "action": "PARTIAL_SELL",
                    "quantity": min(sell_qty, current_qty),
                    "new_phase": "TARGET_1_LOCKED",
                    "new_stop_loss": max(stop_loss, breakeven_sl),
                    "reason": f"💰 Reached 100 DEMA Resistance (₹{dema_100:.2f}). Locked {BotConfig.PARTIAL_PROFIT_PCT}% profit & moved SL to breakeven (₹{breakeven_sl:.2f})"
                }

        # ----------------------------------------------------
        # 5. 100 DEMA STAGNATION / TIME-DECAY EXIT
        # ----------------------------------------------------
        if phase == "TARGET_1_LOCKED" and days_at_100 >= BotConfig.STAGNATION_DAYS:
            # Stagnated near 100 DEMA for > 3 days without breaking out
            return {
                "action": "FULL_SELL",
                "ratio": 1.0,
                "reason": f"Stagnation Exit: Consolidating at 100 DEMA for {days_at_100} days without breakout. Freeing capital.",
                "new_phase": "COMPLETED"
            }

        # Default: Continue holding
        return {"action": "NONE", "ratio": 0.0, "reason": "Holding within active parameters"}
