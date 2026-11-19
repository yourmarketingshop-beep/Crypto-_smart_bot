from __future__ import annotations
import os, sqlite3
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv('BOT_DB_PATH', Path(__file__).resolve().parents[1] / 'bot.db'))
STARTING_CASH = 1000.0
FEE_RATE = 0.001
app = FastAPI(title='Crypto Smart Bot', version='24.0.0', description='Paper trading only')


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL);
        INSERT OR IGNORE INTO account(id,cash) VALUES(1,1000.0);
        CREATE TABLE IF NOT EXISTS positions (
          symbol TEXT PRIMARY KEY, quantity REAL NOT NULL, avg_price REAL NOT NULL,
          stop_loss REAL, take_profit REAL);
        CREATE TABLE IF NOT EXISTS trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL,
          quantity REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')

init_db()

class TradeRequest(BaseModel):
    symbol: str = Field(pattern=r'^(BTCUSDT|ETHUSDT|SOLUSDT)$')
    quantity: float = Field(gt=0, le=1000000)
    price: float = Field(gt=0, le=100000000)

class RiskRequest(BaseModel):
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)

class RiskSizeRequest(BaseModel):
    symbol: str = Field(pattern=r'^(BTCUSDT|ETHUSDT|SOLUSDT)$')
    entry_price: float = Field(gt=0, le=100000000)
    stop_loss: float = Field(gt=0, le=100000000)
    risk_percent: float = Field(gt=0, le=2.0)


def account_row(c): return c.execute('SELECT cash FROM account WHERE id=1').fetchone()

def execute_trade(symbol: str, side: str, qty: float, price: float):
    fee = qty * price * FEE_RATE
    with db() as c:
        cash = float(account_row(c)['cash'])
        pos = c.execute('SELECT * FROM positions WHERE symbol=?', (symbol,)).fetchone()
        if side == 'BUY':
            cost = qty * price + fee
            if cost > cash: raise HTTPException(400, 'Insufficient paper cash')
            old_qty = float(pos['quantity']) if pos else 0.0
            old_avg = float(pos['avg_price']) if pos else 0.0
            new_qty = old_qty + qty
            avg = ((old_qty * old_avg) + qty * price) / new_qty
            sl = pos['stop_loss'] if pos else None
            tp = pos['take_profit'] if pos else None
            c.execute('INSERT OR REPLACE INTO positions VALUES(?,?,?,?,?)', (symbol,new_qty,avg,sl,tp))
            cash -= cost
        else:
            if not pos or qty > float(pos['quantity']) + 1e-10: raise HTTPException(400, 'Insufficient paper position')
            cash += qty * price - fee
            remaining = float(pos['quantity']) - qty
            if remaining <= 1e-10: c.execute('DELETE FROM positions WHERE symbol=?',(symbol,))
            else: c.execute('UPDATE positions SET quantity=? WHERE symbol=?',(remaining,symbol))
        c.execute('UPDATE account SET cash=? WHERE id=1',(cash,))
        c.execute('INSERT INTO trades(symbol,side,quantity,price,fee) VALUES(?,?,?,?,?)',(symbol,side,qty,price,fee))
        return {'symbol':symbol,'side':side,'quantity':qty,'price':price,'fee':fee,'cash':cash}

@app.get('/health')
def health(): return {'status':'ok','mode':'paper_only','version':'24.0.0'}

@app.get('/paper/account')
def get_account():
    with db() as c: return {'cash':float(account_row(c)['cash']),'starting_cash':STARTING_CASH,'mode':'paper_only'}

@app.get('/paper/positions')
def positions():
    with db() as c: return [dict(r) for r in c.execute('SELECT * FROM positions ORDER BY symbol').fetchall()]

@app.post('/paper/buy')
def buy(req: TradeRequest): return execute_trade(req.symbol,'BUY',req.quantity,req.price)

@app.post('/paper/sell')
def sell(req: TradeRequest): return execute_trade(req.symbol,'SELL',req.quantity,req.price)

@app.put('/paper/positions/{symbol}/risk')
def set_risk(symbol: str, req: RiskRequest):
    with db() as c:
        p=c.execute('SELECT * FROM positions WHERE symbol=?',(symbol,)).fetchone()
        if not p: raise HTTPException(404,'Position not found')
        avg=float(p['avg_price'])
        if req.stop_loss is not None and req.stop_loss >= avg: raise HTTPException(400,'Stop loss must be below average entry')
        if req.take_profit is not None and req.take_profit <= avg: raise HTTPException(400,'Take profit must be above average entry')
        c.execute('UPDATE positions SET stop_loss=?,take_profit=? WHERE symbol=?',(req.stop_loss,req.take_profit,symbol))
        return dict(c.execute('SELECT * FROM positions WHERE symbol=?',(symbol,)).fetchone())

@app.post('/paper/monitor/{symbol}')
def monitor(symbol: str, price: float):
    if price <= 0: raise HTTPException(400,'Price must be positive')
    with db() as c: p=c.execute('SELECT * FROM positions WHERE symbol=?',(symbol,)).fetchone()
    if not p: return {'closed':False,'reason':'no_open_position'}
    reason = 'stop_loss' if p['stop_loss'] is not None and price <= p['stop_loss'] else ('take_profit' if p['take_profit'] is not None and price >= p['take_profit'] else None)
    if not reason: return {'closed':False,'reason':'no_trigger'}
    result=execute_trade(symbol,'SELL',float(p['quantity']),price)
    return {'closed':True,'trigger':reason,'trade':result}

@app.get('/paper/report')
def report():
    with db() as c:
        cash=float(account_row(c)['cash'])
        ps=[dict(r) for r in c.execute('SELECT * FROM positions').fetchall()]
        stats=c.execute("SELECT COUNT(*) n, COALESCE(SUM(fee),0) fees, COALESCE(SUM(CASE WHEN side='BUY' THEN quantity*price ELSE 0 END),0) buys, COALESCE(SUM(CASE WHEN side='SELL' THEN quantity*price ELSE 0 END),0) sells FROM trades").fetchone()
        return {'cash':cash,'open_positions':ps,'trade_count':stats['n'],'fees_paid':stats['fees'],'buy_notional':stats['buys'],'sell_notional':stats['sells'],'mode':'paper_only'}

@app.get('/market/klines/{symbol}')
def market_klines(symbol: str, limit: int = 100):
    if symbol not in {'BTCUSDT','ETHUSDT','SOLUSDT'}: raise HTTPException(400,'Unsupported symbol')
    if not 1 <= limit <= 500: raise HTTPException(400,'limit must be 1..500')
    # Public Binance data only. Network failures are reported, never replaced by fabricated prices.
    import json, urllib.request, urllib.error
    url=f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}'
    try:
        with urllib.request.urlopen(url, timeout=8) as response: rows=json.loads(response.read().decode())
        return {'symbol':symbol,'interval':'1m','klines':rows[:-1] if rows else [],'note':'last possibly-open candle excluded'}
    except Exception as exc:
        raise HTTPException(502, f'Public market data unavailable: {type(exc).__name__}')


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    result = [current]
    for value in values[period:]:
        current = (value * alpha) + (current * (1.0 - alpha))
        result.append(current)
    return result

def rsi_value(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_indicators(closes: list[float]) -> dict:
    if len(closes) < 35:
        raise ValueError('At least 35 completed candles are required')
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    # Align EMA12 to the EMA26 series start before calculating MACD.
    macd_line = [fast - slow for fast, slow in zip(ema12[-len(ema26):], ema26)]
    signal_series = ema_series(macd_line, 9)
    macd = macd_line[-1]
    signal = signal_series[-1] if signal_series else None
    histogram = macd - signal if signal is not None else None
    rsi = rsi_value(closes, 14)
    ema50_series = ema_series(closes, 50)
    ema50 = ema50_series[-1] if ema50_series else None
    return {
        'rsi_14': round(rsi, 4) if rsi is not None else None,
        'ema_12': round(ema12[-1], 8),
        'ema_26': round(ema26[-1], 8),
        'ema_50': round(ema50, 8) if ema50 is not None else None,
        'macd': round(macd, 8),
        'macd_signal': round(signal, 8) if signal is not None else None,
        'macd_histogram': round(histogram, 8) if histogram is not None else None,
        'sample_size': len(closes),
    }

@app.get('/market/indicators/{symbol}')
def market_indicators(symbol: str):
    if symbol not in {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}:
        raise HTTPException(400, 'Unsupported symbol')
    candles = market_klines(symbol, 200)
    closes = [float(row[4]) for row in candles['klines']]
    try:
        values = calculate_indicators(closes)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    return {
        'symbol': symbol, 'interval': '1m', 'price': closes[-1],
        'indicators': values, 'source': 'Binance public market data',
        'mode': 'analysis_only_paper_trading',
    }


def build_signal(values: dict) -> dict:
    rsi = values.get('rsi_14')
    macd, signal = values.get('macd'), values.get('macd_signal')
    fast, slow = values.get('ema_12'), values.get('ema_26')
    if None in (rsi, macd, signal, fast, slow):
        raise ValueError('Insufficient indicator values for signal')
    checks = {
        'rsi_bullish_50_to_70': 50 <= rsi <= 70,
        'macd_above_signal': macd > signal,
        'ema12_above_ema26': fast > slow,
    }
    bearish = {
        'rsi_below_50': rsi < 50,
        'macd_below_signal': macd < signal,
        'ema12_below_ema26': fast < slow,
    }
    bull_count, bear_count = sum(checks.values()), sum(bearish.values())
    if bull_count == 3:
        action, reasons, score = 'BUY', list(checks), 100
    elif bear_count == 3:
        action, reasons, score = 'SELL', list(bearish), 100
    else:
        action, reasons, score = 'HOLD', [k for k,v in {**checks, **bearish}.items() if v], max(bull_count, bear_count) * 100 // 3
    return {'signal': action, 'score': score, 'score_label': 'عدد الشروط المتوافقة وليس احتمال ربح',
            'bullish_conditions': checks, 'bearish_conditions': bearish, 'reasons': reasons,
            'mode': 'analysis_only_paper_trading'}

@app.get('/market/signal/{symbol}')
def market_signal(symbol: str):
    if symbol not in {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}:
        raise HTTPException(400, 'Unsupported symbol')
    candles = market_klines(symbol, 200)
    closes = [float(row[4]) for row in candles['klines']]
    try:
        values = calculate_indicators(closes)
        signal = build_signal(values)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    return {'symbol': symbol, 'price': closes[-1], 'indicators': values, **signal,
            'source': 'Binance public market data', 'interval': '1m'}

def backtest_candles(candles: list, fee_rate: float = FEE_RATE) -> dict:
    if len(candles) < 37:
        raise ValueError('At least 37 completed candles are required for backtesting')
    cash, quantity, entry_price, entry_fee = 1000.0, 0.0, None, 0.0
    trades, equity_curve = [], []
    # Signal is calculated only from candles already closed; execution is at the NEXT candle open.
    for i in range(35, len(candles) - 1):
        closes = [float(row[4]) for row in candles[:i+1]]
        try:
            signal = build_signal(calculate_indicators(closes))['signal']
        except ValueError:
            continue
        execution_price = float(candles[i+1][1])
        if signal == 'BUY' and quantity == 0:
            quantity = cash / (execution_price * (1.0 + fee_rate))
            fee = quantity * execution_price * fee_rate
            cash -= quantity * execution_price + fee
            entry_price = execution_price
            entry_fee = fee
            trades.append({'side':'BUY','price':execution_price,'fee':fee,'signal_candle':i,'execution_candle':i+1})
        elif signal == 'SELL' and quantity > 0:
            fee = quantity * execution_price * fee_rate
            proceeds = quantity * execution_price - fee
            pnl = proceeds - (quantity * entry_price) - entry_fee
            cash += proceeds
            trades.append({'side':'SELL','price':execution_price,'fee':fee,'pnl':pnl,'signal_candle':i,'execution_candle':i+1})
            quantity, entry_price, entry_fee = 0.0, None, 0.0
        equity = cash + quantity * float(candles[i+1][4])
        equity_curve.append(round(equity, 8))
    last_price = float(candles[-1][4])
    final_equity = cash + quantity * last_price
    return {'starting_balance':1000.0,'final_equity':round(final_equity, 8),
            'net_profit':round(final_equity-1000.0, 8),
            'return_percent':round((final_equity/1000.0-1)*100, 6),
            'closed_trades':sum(1 for t in trades if t['side']=='SELL'),
            'open_position':{'quantity':round(quantity, 10),'mark_price':last_price} if quantity else None,
            'trades':trades,'equity_curve':equity_curve,'fee_rate':fee_rate,
            'assumptions':['رصيد افتراضي 1000 USDT','رسوم 0.1% لكل عملية شراء أو بيع','الإشارة من شمعة مغلقة والتنفيذ عند افتتاح الشمعة التالية','لا تشمل الانزلاق السعري أو فروق الأسعار','لا تستخدم هذه المحاكاة أموالاً أو أوامر حقيقية'],
            'mode':'historical_paper_backtest_only'}

@app.get('/paper/backtest/{symbol}')
def paper_backtest(symbol: str, limit: int = 500):
    if symbol not in {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}:
        raise HTTPException(400, 'Unsupported symbol')
    if not 38 <= limit <= 500:
        raise HTTPException(400, 'limit must be 38..500 (one candle is excluded as possibly open)')
    candles = market_klines(symbol, limit)['klines']
    try:
        result = backtest_candles(candles)
    except (ValueError, IndexError) as exc:
        raise HTTPException(502, str(exc))
    return {'symbol':symbol,'interval':'1m','candles':len(candles),'source':'Binance public market data',**result}


def calculate_position_size(cash: float, entry_price: float, stop_loss: float, risk_percent: float) -> dict:
    """Risk-based sizing only; does not submit or reserve an order."""
    if cash <= 0 or entry_price <= 0 or stop_loss <= 0:
        raise ValueError('Cash and prices must be positive')
    if stop_loss >= entry_price:
        raise ValueError('Stop loss must be below entry price for a long position')
    if not 0 < risk_percent <= 2.0:
        raise ValueError('Risk percent must be greater than 0 and at most 2%')
    risk_cash = cash * (risk_percent / 100.0)
    per_unit_loss = entry_price - stop_loss
    risk_limited_qty = risk_cash / per_unit_loss
    # Include estimated buy fee in the affordability cap; fee on exit is not included
    affordable_qty = cash / (entry_price * (1.0 + FEE_RATE))
    quantity = min(risk_limited_qty, affordable_qty)
    notional = quantity * entry_price
    estimated_fee = notional * FEE_RATE
    estimated_loss_at_stop = quantity * per_unit_loss + estimated_fee
    return {
        'risk_cash_target': round(risk_cash, 8),
        'quantity': round(quantity, 10),
        'notional': round(notional, 8),
        'estimated_entry_fee': round(estimated_fee, 8),
        'estimated_loss_at_stop': round(estimated_loss_at_stop, 8),
        'risk_percent_requested': risk_percent,
        'affordability_limited': affordable_qty < risk_limited_qty,
        'note': 'تقدير لمركز شراء افتراضي فقط؛ لا ينفذ صفقة ولا يشمل رسوم الخروج أو الانزلاق السعري أو فجوات الأسعار.',
        'mode': 'paper_risk_calculator_only',
    }

@app.post('/paper/risk/size')
def paper_risk_size(req: RiskSizeRequest):
    with db() as c:
        cash = float(account_row(c)['cash'])
    try:
        result = calculate_position_size(cash, req.entry_price, req.stop_loss, req.risk_percent)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {'symbol': req.symbol, 'available_cash': round(cash, 8), **result}
