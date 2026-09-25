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
    INITIAL_CAPITAL = float(os.environ.get("AUTOTRADER_CAPITAL", 500000.0)) # ₹5,00,000 (5 Lac pool)
    BUCKET_CAPITAL_PER_STOCK = float(os.environ.get("AUTOTRADER_BUCKET_CAPITAL", 100000.0)) # ₹1,00,000 (1 Lac max per stock)
    TRANCHE_SIZE = float(os.environ.get("AUTOTRADER_TRANCHE_SIZE", 100000.0)) # ₹1,00,000 One-Shot allocation
    MAX_TRANCHES_PER_STOCK = int(os.environ.get("AUTOTRADER_MAX_TRANCHES", 1)) # 1 shot only (no tranche averaging)
    MAX_ACTIVE_POSITIONS = int(os.environ.get("AUTOTRADER_MAX_POSITIONS", 5)) # Exactly 5 stocks (5L / 1L)
    MAX_DAILY_LOSS_PCT = 5.0 # Stop trading if daily portfolio drawdown reaches -5% (-₹25,000)
    HARD_STOP_LOSS_PCT = 3.5 # Hard stop loss per trade (-3.5%)

    # --- Strategy Mode (One-Shot Lump Sum Only) ---
    STRATEGY_MODE = os.environ.get("AUTOTRADER_STRATEGY_MODE", "ONE_SHOT").upper() # 'ONE_SHOT'
    AB_TEST_ENABLED = False # Pure One-Shot entry (Tranche Averaging disabled)
    MAX_TRANCHE_POSITIONS = 0 # 0 slots for Tranche Averaging
    MAX_ONE_SHOT_POSITIONS = 5 # 5 slots for ₹1.0L One-Shot Lump Sum

    # --- Strategy Parameters (DEMA Stage-Rider) ---
    MIN_HEADROOM_TO_100_DEMA = float(os.environ.get("AUTOTRADER_MIN_HEADROOM_100_DEMA", 4.0)) # Minimum +4.0% distance from entry price to 100 DEMA
    RSI_MIN = 40.0 # Minimum RSI (14) for entry
    RSI_MAX = 70.0 # Maximum RSI (14) for entry (healthy momentum zone)

    # 100 DEMA Resistance & Partial Booking
    DEMA_100_RESISTANCE_PCT = 99.9 # % of 100 DEMA to trigger Target 1
    PARTIAL_PROFIT_PCT = 30.0 # Sell 30% of position at 100 DEMA
    STAGNATION_DAYS = 3 # If stalled at 100 DEMA for > 3 days, exit trade

    # Market Cap Eligibility (Only LargeCap & MidCap allowed; SmallCap excluded)
    ALLOWED_MCAP_TIERS = ["LARGECAP", "MIDCAP"]

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
