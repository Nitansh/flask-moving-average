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
    def get_min_headroom():
        """Returns the configured minimum % distance from entry price to 100 DEMA."""
        try:
            from .db import get_bot_state
            state = get_bot_state()
            if state and "min_headroom_to_100_dema" in state and state["min_headroom_to_100_dema"] is not None:
                return float(state["min_headroom_to_100_dema"])
        except Exception:
            pass
        return BotConfig.MIN_HEADROOM_TO_100_DEMA

    @classmethod
    def get_crossover_type(cls, stock_data):
        """
        Evaluates Golden Crossover status:
        - GOLDEN_CROSS: 20 DEMA >= 50 DEMA and Price >= 20 DEMA
        - GOLDEN_CROSS_APPROACHING: 20 DEMA < 50 DEMA, gap <= 3.0%, Price > 20 DEMA
        - NO_CROSSOVER: Death Cross regime or Price < 20 DEMA
        """
        price, dema_20, dema_50, _, _, _ = cls._extract_stock_values(stock_data)
        if not (price and dema_20 and dema_50):
            return "NO_CROSSOVER", 999.0, "Missing required Price, 20 DEMA, or 50 DEMA values"

        is_gc_flag = stock_data.get("isGoldenCrossApproaching") in [True, "true"]
        gc_gap = stock_data.get("goldenCrossGap")
        if gc_gap is not None:
            try:
                gc_gap_val = float(gc_gap)
            except (ValueError, TypeError):
                gc_gap_val = ((dema_50 - dema_20) / dema_50) * 100.0 if dema_50 > 0 else 999.0
        else:
            gc_gap_val = ((dema_50 - dema_20) / dema_50) * 100.0 if dema_50 > 0 else 999.0

        if dema_20 >= dema_50 and price >= dema_20 and dema_50 > 0:
            return "GOLDEN_CROSS", gc_gap_val, "Confirmed Golden Cross (20 DEMA >= 50 DEMA)"
        elif is_gc_flag or (dema_20 < dema_50 and 0.0 <= gc_gap_val <= 3.0 and price > dema_20):
            return "GOLDEN_CROSS_APPROACHING", gc_gap_val, f"Approaching Golden Cross (Gap: {gc_gap_val:.1f}%)"
        elif dema_20 < dema_50:
            return "NO_CROSSOVER", gc_gap_val, f"No Golden Crossover: 20 DEMA (₹{dema_20:.1f}) is {gc_gap_val:.1f}% below 50 DEMA (₹{dema_50:.1f}) (Death Cross regime)"
        else:
            return "NO_CROSSOVER", gc_gap_val, f"No Golden Crossover breakout: Price (₹{price:.1f}) is below 20 DEMA (₹{dema_20:.1f})"

    @classmethod
    def evaluate_entry(cls, stock_data):
        """
        Evaluates whether a stock meets all BUY entry criteria:
        1. Golden Crossover structure: Confirmed Golden Cross (20 DEMA >= 50 DEMA & Price >= 20 DEMA)
           OR Approaching Golden Cross (20 DEMA converging <= 3.0% of 50 DEMA & Price > 20 DEMA).
        2. Upside room to 100 DEMA is at least min_headroom (default >= 4.0%).
        3. RSI in momentum expansion zone (40-70, and strictly not > 75).
        """
        price, dema_20, dema_50, dema_100, dema_200, rsi = cls._extract_stock_values(stock_data)

        if not (price and dema_20 and dema_50):
            return False, "Missing required Price, 20 DEMA, or 50 DEMA values"

        # Market Cap Tier Enforcement (Only LargeCap & MidCap allowed; SmallCap excluded)
        mcap_tier, _ = cls.get_market_cap_tier(stock_data)
        if mcap_tier not in getattr(BotConfig, "ALLOWED_MCAP_TIERS", ["LARGECAP", "MIDCAP"]):
            return False, f"Small Cap stocks are excluded from Auto-Trader (Current tier: {mcap_tier})"

        min_headroom = cls.get_min_headroom()

        # Enforce Minimum Headroom to 100 DEMA Resistance
        # Current price MUST be lower than 100 DEMA by at least min_headroom (default >= 4.0% to 5.0%)
        # to provide sufficient profit runway up to Target 1 resistance.
        if dema_100 and dema_100 > 0:
            if price >= dema_100:
                return False, f"Current price (₹{price:.1f}) is at or above 100 DEMA (₹{dema_100:.1f}). Strategy requires price to be lower than 100 DEMA by at least {min_headroom:.1f}% to ride to Target 1 resistance."
            headroom_pct = ((dema_100 - price) / price) * 100.0
            if headroom_pct < min_headroom:
                return False, f"Insufficient headroom to 100 DEMA (+{headroom_pct:.1f}% < minimum +{min_headroom:.1f}%). Current price must be lower than 100 DEMA by at least {min_headroom:.1f}% for profitable target booking."
        else:
            return False, f"Missing 100 DEMA value (required: current price must be lower than 100 DEMA by at least {min_headroom:.1f}%)"

        # STRICT GOLDEN CROSSOVER ENFORCEMENT
        # Disqualifies any stock in Death Cross regime (20 DEMA < 50 DEMA without approaching convergence)
        # or where price has broken below 20 DEMA.
        gc_type, gc_gap_val, gc_desc = cls.get_crossover_type(stock_data)
        if gc_type == "NO_CROSSOVER":
            return False, gc_desc

        # RSI Momentum Filter
        if rsi and rsi > 75.0:
            return False, f"RSI {rsi:.1f} indicates extreme overbought exhaustion (> 75)"
        if rsi and gc_type == "GOLDEN_CROSS" and not (BotConfig.RSI_MIN <= rsi <= BotConfig.RSI_MAX):
            return False, f"RSI {rsi:.1f} outside optimal momentum range ({BotConfig.RSI_MIN}-{BotConfig.RSI_MAX})"
        if rsi and gc_type == "GOLDEN_CROSS_APPROACHING" and not (35.0 <= rsi <= 68.0):
            return False, f"RSI {rsi:.1f} outside optimal momentum range (35-68) for Golden Cross approach"

        headroom_str = f" (+{((dema_100 - price)/price)*100.0:.1f}% room to 100 DEMA)" if (dema_100 and dema_100 > price) else ""

        is_bullish_flag = stock_data.get("isBullish") in [True, "true"]
        if is_bullish_flag:
            return True, f"Moving-Average Live Scanner Confirmed: {gc_desc}{headroom_str}"

        return True, f"{gc_desc} with favorable momentum{headroom_str}"

    # Prominent NIFTY 100 Largecap constituents
    LARGECAP_SYMBOLS = {
        "RELIANCE", "TCS", "HDFCBANK", "BHARTIARTL", "ICICIBANK", "INFY", "SBIN", "LICI",
        "ITC", "HINDUNILVR", "LT", "BAJFINANCE", "HCLTECH", "MARUTI", "SUNPHARMA", "ADANIENT",
        "KOTAKBANK", "TITAN", "ONGC", "TATAMOTORS", "NTPC", "AXISBANK", "DMART", "ADANIPORTS",
        "POWERGRID", "COALINDIA", "BAJAJFINSV", "ULTRACEMCO", "SIEMENS", "ASIANPAINT", "BEL",
        "HAL", "NESTLEIND", "IOC", "DLF", "VBL", "ZOMATO", "GRASIM", "JSWSTEEL", "TRENT",
        "IRFC", "VEDL", "PFC", "RECLTD", "TECHM", "ADANIPOWER", "HINDALCO", "INDUSINDBK",
        "CHOLAFIN", "TATASTEEL", "JIOFIN", "MOTHERSON", "EICHERMOT", "BPCL", "GODREJCP",
        "DIVISLAB", "SHRIRAMFIN", "BAJAJ-AUTO", "TORNTPHARM", "ABB", "BRITANNIA", "GAIL",
        "CIPLA", "HAVELLS", "INDIGO", "TATACONSUM", "AMBUJACEM", "UNITDSPR", "PIDILITIND",
        "DABUR", "MAXHEALTH", "BANKBARODA", "PNB", "LTIM", "POLYCAB", "CANBK", "BOSCHLTD",
        "SHREECEM", "CGPOWER", "TVSMOTOR", "ICICIPRULI", "HEROMOTOCO", "ICICIGI", "COLPAL",
        "APOLLOHOSP", "BERGEPAINT", "MARICO", "DRREDDY", "SRF", "NAUKRI", "LUPIN", "AUROPHARMA",
        "IOB", "SBILIFE", "HDFCLIFE", "JSWENERGY", "CUMMINSIND", "PERSISTENT"
    }

    # Prominent NIFTY Midcap 150 constituents
    MIDCAP_SYMBOLS = {
        "ACC", "AUBANK", "FEDERALBNK", "IDFCFIRSTB", "YESBANK", "BANDHANBNK", "CONCOR",
        "PETRONET", "SAIL", "NMDC", "VOLTAS", "MUTHOOTFIN", "ASHOKLEY", "BALKRISIND", "ASTRAL",
        "DEEPAKNTR", "ESCORTS", "EXIDEIND", "GLAND", "GLENMARK", "GMRINFRA", "GUJGASLTD",
        "HINDPETRO", "IPCALAB", "JUBLFOOD", "LICHSGFIN", "L&TFH", "MFSL", "MPHASIS",
        "OBEROIRLTY", "PAGEIND", "PEL", "PRESTIGE", "RAMCOCEM", "STARHEALTH", "SUNTV",
        "SYNGENE", "TATACHEM", "TATAPOWER", "TORNTPOWER", "UBL", "M&MFIN", "METROPOLIS",
        "NATIONALUM", "NAVINFLUOR", "PAYTM", "QUESS", "RADICO", "SUZLON", "DIXON",
        "BHEL", "KALYANKJIL", "SUPREMEIND", "PHOENIXLTD", "KPITTECH", "COFORGE", "FORTIS",
        "GLAXO", "KIMS", "LALPATHLAB", "APARINDS", "AARTIIND", "ABCAPITAL", "ABFRL", "ANGELONE"
    }

    @classmethod
    def get_market_cap_tier(cls, stock_data):
        """Categorizes stock into LARGECAP, MIDCAP, or SMALLCAP with associated score."""
        symbol = str(stock_data.get("symbol") or "").upper().replace("-EQ", "").strip()
        market_type = str(stock_data.get("marketType") or stock_data.get("marketCap") or "").strip().lower()

        if "large" in market_type:
            return "LARGECAP", 25.0
        if "mid" in market_type:
            return "MIDCAP", 18.0
        if "small" in market_type:
            return "SMALLCAP", 8.0

        # Check numerical MCAP
        mcap = stock_data.get("mcap")
        if mcap is not None:
            try:
                mcap_clean = str(mcap).replace(",", "").strip()
                mcap_val = float(mcap_clean)
                if mcap_val > 1e8:  # Raw rupees to Crores conversion
                    mcap_val = mcap_val / 1e7
                if mcap_val > 20000.0:
                    return "LARGECAP", 25.0
                elif mcap_val > 5000.0:
                    return "MIDCAP", 18.0
                elif mcap_val > 0.0:
                    return "SMALLCAP", 8.0
            except (ValueError, TypeError):
                pass

        if symbol in cls.LARGECAP_SYMBOLS:
            return "LARGECAP", 25.0
        if symbol in cls.MIDCAP_SYMBOLS:
            return "MIDCAP", 18.0

        return "SMALLCAP", 8.0

    @staticmethod
    def _extract_volume(stock_data):
        """Extracts numerical volume safely."""
        for k in ("volume", "vol", "VOLUME", "totalTradedVolume"):
            val = stock_data.get(k)
            if val is not None and val != "":
                try:
                    return float(str(val).replace(",", "").strip())
                except (ValueError, TypeError):
                    pass
        return 0.0

    @classmethod
    def calculate_rank_score(cls, stock_data):
        """
        Calculates a multi-factor ranking score (0 to 100) for prioritizing trade entries:
        1. Headroom / Maximum Profit Potential (35 pts): Room from current price to 100 DEMA.
        2. Market Cap Tier (25 pts): Largecap (25 pts) > Midcap (18 pts) > Smallcap (8 pts).
        3. RSI Sweet Spot (20 pts): Fresh breakout / momentum zone (48-55 optimal).
        4. Volume / Liquidity (20 pts): High liquidity ensures clean execution without slippage.

        Returns:
            (total_score, breakdown_dict)
        """
        price, dema_20, dema_50, dema_100, dema_200, rsi = cls._extract_stock_values(stock_data)

        # 1. Headroom / Profit Potential (35 pts)
        headroom_pct = 0.0
        if dema_100 and dema_100 > price and price > 0:
            headroom_pct = ((dema_100 - price) / price) * 100.0
            if headroom_pct >= 12.0:
                headroom_score = 35.0
            elif headroom_pct >= 8.0:
                headroom_score = 25.0 + ((headroom_pct - 8.0) / 4.0) * 10.0
            elif headroom_pct >= 4.0:
                headroom_score = 15.0 + ((headroom_pct - 4.0) / 4.0) * 10.0
            else:
                headroom_score = max(5.0, (headroom_pct / 4.0) * 15.0)
        elif dema_200 and dema_200 > price and price > 0:
            # Stage 2 breakout targeting 200 DEMA
            headroom_pct = ((dema_200 - price) / price) * 100.0
            if headroom_pct >= 10.0:
                headroom_score = 30.0
            elif headroom_pct >= 5.0:
                headroom_score = 22.0
            else:
                headroom_score = 14.0
        else:
            headroom_pct = 0.0
            headroom_score = 10.0

        # 2. Market Cap Tier (25 pts)
        mcap_tier, mcap_score = cls.get_market_cap_tier(stock_data)

        # 3. RSI Sweet Spot (20 pts)
        # Fresh breakouts in 48-55 zone have the highest continuation runway
        if not rsi or rsi <= 0:
            rsi_score = 12.0
        elif 48.0 <= rsi <= 55.0:
            rsi_score = 20.0
        elif 55.0 < rsi <= 60.0:
            rsi_score = 16.0
        elif 42.0 <= rsi < 48.0:
            rsi_score = 12.0
        elif 60.0 < rsi <= 68.0:
            rsi_score = 8.0
        else:
            rsi_score = 4.0

        # 4. Volume / Liquidity (20 pts)
        vol = cls._extract_volume(stock_data)
        if vol >= 1_000_000:
            vol_score = 20.0
        elif vol >= 500_000:
            vol_score = 15.0
        elif vol >= 100_000:
            vol_score = 10.0
        elif vol > 0:
            vol_score = 6.0
        else:
            vol_score = 8.0

        total_score = round(headroom_score + mcap_score + rsi_score + vol_score, 1)

        gc_type, gc_gap_val, gc_desc = cls.get_crossover_type(stock_data)

        breakdown = {
            "total_score": total_score,
            "headroom_pct": round(headroom_pct, 2),
            "headroom_score": round(headroom_score, 1),
            "mcap_tier": mcap_tier,
            "mcap_score": round(mcap_score, 1),
            "rsi": round(rsi, 1) if rsi else None,
            "rsi_score": round(rsi_score, 1),
            "volume": int(vol),
            "volume_score": round(vol_score, 1),
            "crossover_type": gc_type,
            "crossover_label": gc_desc,
            "golden_cross_gap": round(gc_gap_val, 2) if gc_gap_val < 900 else None
        }

        return total_score, breakdown

    @staticmethod
    def evaluate_scale_in(position, current_price, current_dema, rsi=None):
        """
        Evaluates whether an active position qualifies for an additional averaging tranche.
        STRICT TRUE PRICE-DIP AVERAGING RULES:
        1. Position has not reached max tranches (5 tranches = ₹2.5L).
        2. Real Price Dip Required: Current price MUST be at least 3.0% below the average buy_price
           (dip_pct >= 3.0%). Adding tranches at the same or slightly different price is strictly rejected.
        3. Structural Safety Floor: Current price must remain above 50 DEMA and above stop_loss.
           Never average down into a broken structure.
        """
        tranches_count = int(position.get("tranches_count", 1))
        if tranches_count >= BotConfig.MAX_TRANCHES_PER_STOCK:
            return False, "Maximum 5 tranches (₹2.5L) already deployed"

        buy_price = float(position.get("buy_price") or 0.0)
        if buy_price <= 0:
            return False, "Invalid buy price"

        # Mandatory rule: Current price MUST have dropped at least 3.0% below average buy price
        dip_pct = ((buy_price - current_price) / buy_price) * 100.0
        if dip_pct < 3.0:
            return False, f"Price only dipped {dip_pct:.2f}% (minimum -3.0% pullback from ₹{buy_price:.2f} required to average down)"

        dema_20 = current_dema.get("dema_20") or position.get("dema_20")
        dema_50 = current_dema.get("dema_50") or position.get("dema_50")
        stop_loss = float(position.get("stop_loss", 0.0))

        if not dema_50:
            return False, "Missing 50 DEMA indicator"

        # Safety floor 1: Must be above stop-loss
        if stop_loss > 0 and current_price <= stop_loss:
            return False, f"Price (₹{current_price:.2f}) is at or below stop loss (₹{stop_loss:.2f}); averaging blocked"

        # Safety floor 2: Must stay above 50 DEMA support
        if current_price < dema_50:
            return False, f"Price (₹{current_price:.2f}) broke below 50 DEMA (₹{dema_50:.2f}); cannot average into a breakdown"

        return True, f"Dip-Buy Tranche #{tranches_count + 1}: Real price dip of -{dip_pct:.1f}% below avg buy price (₹{buy_price:.2f} -> ₹{current_price:.2f}), holding 50 DEMA support"

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
        # 1. HARD STOP-LOSS
        # ----------------------------------------------------
        if current_price <= stop_loss:
            return {
                "action": "FULL_SELL",
                "ratio": 1.0,
                "reason": f"Stop-Loss hit at ₹{current_price:.2f} (SL: ₹{stop_loss:.2f})",
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
            # Only trigger 100 DEMA target booking if position was entered below 100 DEMA
            # (If entered above 100 DEMA, stock is riding towards 200 DEMA, not hitting 100 DEMA resistance)
            if buy_price < dema_100:
                resistance_price = dema_100 * (BotConfig.DEMA_100_RESISTANCE_PCT / 100.0)
                breakout_price = dema_100 * (BotConfig.DEMA_200_BREAKOUT_PCT / 100.0)

                # Check if stock has reached 100 DEMA Resistance (99.9%)
                # AND ensure trade has achieved meaningful positive profit (>= 2.0% gain)
                gain_pct = ((current_price - buy_price) / buy_price) * 100.0
                min_headroom = StrategyEngine.get_min_headroom()
                min_gain_for_booking = max(2.0, min_headroom * 0.6)

                if current_price >= resistance_price and current_price < breakout_price and gain_pct >= min_gain_for_booking:
                    # Sell 30% of the position to lock in profit
                    sell_qty = max(1, int(round(initial_qty * (BotConfig.PARTIAL_PROFIT_PCT / 100.0))))
                    # Move Stop Loss to Breakeven (+0.5% buffer for brokerage/DP charges)
                    breakeven_sl = buy_price * 1.005

                    return {
                        "action": "PARTIAL_SELL",
                        "quantity": min(sell_qty, current_qty),
                        "new_phase": "TARGET_1_LOCKED",
                        "new_stop_loss": max(stop_loss, breakeven_sl),
                        "reason": f"💰 Reached 100 DEMA Resistance (₹{dema_100:.2f}) with +{gain_pct:.1f}% gain. Locked {BotConfig.PARTIAL_PROFIT_PCT}% profit & moved SL to breakeven (₹{breakeven_sl:.2f})"
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
