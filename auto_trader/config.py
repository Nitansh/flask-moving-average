"""
Auto-Trader Configuration & Environment Settings
Handles environment secrets (Kite Connect API) and strategy defaults.
"""
import os

class BotConfig:
    # --- Kite Connect Credentials (Injected via Environment / heartbeat.sh / Cloud Console) ---
    KITE_API_KEY = os.environ.get("KITE_API_KEY", "")
    KITE_API_SECRET = os.environ.get("KITE_API_SECRET", "")
    KITE_ACCESS_TOKEN = os.environ.get("KITE_ACCESS_TOKEN", "")
    KITE_USER_ID = os.environ.get("KITE_USER_ID", "")
    KITE_TOTP_KEY = os.environ.get("KITE_TOTP_KEY", "")

    # Mode: 'PAPER' (Virtual simulation) or 'LIVE' (Real Zerodha Kite Connect)
    # Default to PAPER if live credentials are not set
    MODE = os.environ.get("AUTOTRADER_MODE", "PAPER").upper()

    # --- Capital & Risk Management Defaults ---
    INITIAL_CAPITAL = float(os.environ.get("AUTOTRADER_CAPITAL", 2000000.0)) # ₹20,00,000 (20 Lac pool)
    BUCKET_CAPITAL_PER_STOCK = float(os.environ.get("AUTOTRADER_BUCKET_CAPITAL", 250000.0)) # ₹2,50,000 (2.5 Lac max per stock)
    TRANCHE_SIZE = float(os.environ.get("AUTOTRADER_TRANCHE_SIZE", 50000.0)) # ₹50,000 per shot (averaging / scaling in)
    MAX_TRANCHES_PER_STOCK = int(os.environ.get("AUTOTRADER_MAX_TRANCHES", 5)) # Up to 5 tranches (5 x 50k = 2.5L)
    MAX_ACTIVE_POSITIONS = int(os.environ.get("AUTOTRADER_MAX_POSITIONS", 8)) # Up to 8 stocks (20L / 2.5L)
    MAX_DAILY_LOSS_PCT = 5.0 # Stop trading if daily portfolio drawdown reaches -5% (-₹1,00,000)
    HARD_STOP_LOSS_PCT = 3.5 # Hard stop loss per trade (-3.5%)

    # --- A/B Testing Strategy Split (Half Tranche Averaging vs Half One-Shot) ---
    AB_TEST_ENABLED = True
    MAX_TRANCHE_POSITIONS = 4 # 4 slots for 50k Tranche Averaging (up to ₹2.5L each)
    MAX_ONE_SHOT_POSITIONS = 4 # 4 slots for ₹2.5L One-Shot Lump Sum

    # --- Strategy Parameters (DEMA Stage-Rider) ---
    MIN_HEADROOM_TO_100_DEMA = 3.0 # Minimum +3.0% distance from price to 100 DEMA to enter
    RSI_MIN = 45.0 # Minimum RSI (14) for entry
    RSI_MAX = 68.0 # Maximum RSI (14) for entry (healthy momentum zone)

    # 100 DEMA Resistance & Partial Booking
    DEMA_100_RESISTANCE_PCT = 99.9 # % of 100 DEMA to trigger Target 1
    PARTIAL_PROFIT_PCT = 30.0 # Sell 30% of position at 100 DEMA
    STAGNATION_DAYS = 3 # If stalled at 100 DEMA for > 3 days, exit trade

    # 200 DEMA Breakout & Mega-Runner
    DEMA_200_BREAKOUT_PCT = 101.0 # % of 200 DEMA to trigger Mega-Runner mode
    RUNNER_TRAILING_MA = '20_DEMA' # Trail with 20 DEMA (close below 20 DEMA exits)

    @classmethod
    def has_live_credentials(cls):
        """Checks if minimum live Kite credentials exist in environment."""
        return bool(cls.KITE_API_KEY and (cls.KITE_ACCESS_TOKEN or cls.KITE_API_SECRET))

    @classmethod
    def get_effective_mode(cls):
        """Returns LIVE only if explicitly requested AND credentials exist; else PAPER."""
        if cls.MODE == "LIVE" and cls.has_live_credentials():
            return "LIVE"
        return "PAPER"
