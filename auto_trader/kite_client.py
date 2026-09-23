"""
Kite Connect Client Wrapper with Seamless Paper Trading Simulation
Allows execution in either LIVE (real broker orders) or PAPER (simulated fills).
"""
import time
from .config import BotConfig
from .db import log_event

class KiteTraderClient:
    def __init__(self, mode=None):
        self.mode = mode or BotConfig.get_effective_mode()
        self.kite = None
        self._init_client()

    def _init_client(self):
        if self.mode == "LIVE":
            try:
                from kiteconnect import KiteConnect
                if not BotConfig.KITE_API_KEY:
                    log_event("WARNING", "KITE_API_KEY is not set. Falling back to PAPER mode.")
                    self.mode = "PAPER"
                    return

                self.kite = KiteConnect(api_key=BotConfig.KITE_API_KEY)
                
                # Check for existing access token or generate session
                if BotConfig.KITE_ACCESS_TOKEN:
                    self.kite.set_access_token(BotConfig.KITE_ACCESS_TOKEN)
                    log_event("SUCCESS", "Kite Connect authenticated using KITE_ACCESS_TOKEN.")
                else:
                    log_event("WARNING", "KITE_ACCESS_TOKEN not found. In LIVE mode, generate session token daily.")
            except ImportError:
                log_event("WARNING", "kiteconnect library not installed. Falling back to PAPER mode.")
                self.mode = "PAPER"
            except Exception as e:
                log_event("ERROR", f"Failed to initialize Kite client: {e}. Falling back to PAPER mode.")
                self.mode = "PAPER"

    def get_margins(self):
        """Returns available equity cash balance."""
        if self.mode == "LIVE" and self.kite:
            try:
                margins = self.kite.margins("equity")
                return float(margins.get("available", {}).get("live_balance", 0.0))
            except Exception as e:
                log_event("ERROR", f"Error fetching live margins: {e}")
                return 0.0
        # In Paper mode, margins are tracked by local database
        return None

    def place_buy_order(self, symbol, quantity, price):
        """
        Executes a delivery (CNC) BUY order.
        In LIVE mode: calls kite.place_order.
        In PAPER mode: simulates immediate fill at market price.
        """
        if quantity <= 0:
            return {"status": "FAILED", "reason": "Quantity must be > 0"}

        if self.mode == "LIVE" and self.kite:
            try:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                    quantity=int(quantity),
                    product=self.kite.PRODUCT_CNC,
                    order_type=self.kite.ORDER_TYPE_LIMIT,
                    price=round(float(price) * 1.001, 2) # Slight marketable buffer
                )
                log_event("SUCCESS", f"Live BUY order placed: {symbol} x {quantity} @ ₹{price}", {"order_id": order_id})
                return {"status": "SUCCESS", "order_id": str(order_id), "executed_price": price, "mode": "LIVE"}
            except Exception as e:
                err_msg = str(e)
                log_event("ERROR", f"Live BUY order failed for {symbol}: {err_msg}")
                return {"status": "FAILED", "reason": err_msg}

        # Simulated Paper fill
        simulated_id = f"PAPER_BUY_{symbol}_{int(time.time())}"
        log_event("SUCCESS", f"Paper BUY executed: {symbol} x {quantity} @ ₹{price:.2f}", {"order_id": simulated_id})
        return {"status": "SUCCESS", "order_id": simulated_id, "executed_price": price, "mode": "PAPER"}

    def place_sell_order(self, symbol, quantity, price, reason=""):
        """
        Executes a delivery (CNC) SELL order.
        In LIVE mode: calls kite.place_order (requires DDPI on Zerodha).
        In PAPER mode: simulates immediate fill at market price.
        """
        if quantity <= 0:
            return {"status": "FAILED", "reason": "Quantity must be > 0"}

        if self.mode == "LIVE" and self.kite:
            try:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=int(quantity),
                    product=self.kite.PRODUCT_CNC,
                    order_type=self.kite.ORDER_TYPE_MARKET
                )
                log_event("SUCCESS", f"Live SELL order placed: {symbol} x {quantity} @ ₹{price} ({reason})", {"order_id": order_id})
                return {"status": "SUCCESS", "order_id": str(order_id), "executed_price": price, "mode": "LIVE"}
            except Exception as e:
                err_msg = str(e)
                log_event("ERROR", f"Live SELL order failed for {symbol}: {err_msg}")
                return {"status": "FAILED", "reason": err_msg}

        # Simulated Paper fill
        simulated_id = f"PAPER_SELL_{symbol}_{int(time.time())}"
        log_event("SUCCESS", f"Paper SELL executed: {symbol} x {quantity} @ ₹{price:.2f} ({reason})", {"order_id": simulated_id})
        return {"status": "SUCCESS", "order_id": simulated_id, "executed_price": price, "mode": "PAPER"}
