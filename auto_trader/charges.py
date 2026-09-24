"""
Indian Equity (NSE / Zerodha) Brokerage & Regulatory Charges Calculator
Calculates exact statutory and broker charges for delivery & swing trading:
1. STT / CTT (0.1% on buy & sell for delivery)
2. Exchange Txn Charge (NSE: 0.00297% on turnover)
3. SEBI Turnover Fee (₹10 per crore = 0.0001%)
4. Stamp Duty (0.015% on buy side)
5. DP (Depository Participant) Charges (₹13.50 + 18% GST = ₹15.93 per sell debit)
6. Brokerage (₹0 for Zerodha Equity Delivery)
7. GST (18% on Brokerage + Exchange Txn + SEBI charges)
"""

def calculate_charges(buy_price: float, sell_price: float, quantity: int, is_delivery: bool = True) -> dict:
    """
    Computes statutory taxes and brokerage for an equity swing/delivery trade.
    """
    if quantity <= 0 or buy_price <= 0 or sell_price <= 0:
        return {
            "brokerage": 0.0,
            "stt": 0.0,
            "exchange_txn": 0.0,
            "sebi_charges": 0.0,
            "stamp_duty": 0.0,
            "dp_charges": 0.0,
            "gst": 0.0,
            "total_charges": 0.0,
            "breakeven_diff": 0.0,
            "breakeven_pct": 0.0
        }

    buy_turnover = round(buy_price * quantity, 2)
    sell_turnover = round(sell_price * quantity, 2)
    total_turnover = buy_turnover + sell_turnover

    # 1. Brokerage: ₹0 for Zerodha Delivery
    brokerage = 0.0

    # 2. STT: 0.1% on Buy and 0.1% on Sell
    stt_buy = round(buy_turnover * 0.001, 2)
    stt_sell = round(sell_turnover * 0.001, 2)
    stt = round(stt_buy + stt_sell, 2)

    # 3. Exchange Transaction Charges: NSE 0.00297%
    exchange_txn = round(total_turnover * 0.0000297, 2)

    # 4. Stamp Duty: 0.015% on Buy turnover only
    stamp_duty = round(buy_turnover * 0.00015, 2)

    # 5. SEBI Turnover Charges: ₹10 per Crore (0.0001%)
    sebi_charges = round(total_turnover * 0.000001, 2)

    # 6. DP Charges: ₹13.50 + 18% GST (flat ₹15.93 per stock sell debit)
    dp_charges = 15.93 if is_delivery else 0.0

    # 7. GST: 18% on (Brokerage + Exchange Txn + SEBI)
    gst_taxable = brokerage + exchange_txn + sebi_charges
    gst = round(gst_taxable * 0.18, 2)

    # Total statutory and broker deductions
    total_charges = round(brokerage + stt + exchange_txn + stamp_duty + sebi_charges + dp_charges + gst, 2)

    # Breakeven calculation
    breakeven_diff = round(total_charges / quantity, 2)
    breakeven_pct = round((total_charges / buy_turnover) * 100.0, 2)

    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_txn": exchange_txn,
        "stamp_duty": stamp_duty,
        "sebi_charges": sebi_charges,
        "dp_charges": dp_charges,
        "gst": gst,
        "total_charges": total_charges,
        "breakeven_diff": breakeven_diff,
        "breakeven_pct": breakeven_pct,
        "buy_turnover": buy_turnover,
        "sell_turnover": sell_turnover,
        "total_turnover": total_turnover
    }
