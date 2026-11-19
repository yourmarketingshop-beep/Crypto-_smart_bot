import importlib
from fastapi.testclient import TestClient
import app.main as m


def setup_function():
    m.DB_PATH = m.Path(m.__file__).resolve().parents[1] / 'test_runtime.db'
    if m.DB_PATH.exists(): m.DB_PATH.unlink()
    m.init_db()

client=TestClient(m.app)

def test_health_is_paper_only():
    r=client.get('/health'); assert r.status_code==200 and r.json()['mode']=='paper_only'

def test_buy_and_sell_update_cash():
    b=client.post('/paper/buy',json={'symbol':'BTCUSDT','quantity':0.01,'price':50000})
    assert b.status_code==200
    assert round(b.json()['cash'],2)==499.50
    s=client.post('/paper/sell',json={'symbol':'BTCUSDT','quantity':0.01,'price':51000})
    assert s.status_code==200 and s.json()['cash']>499.50
    assert client.get('/paper/positions').json()==[]

def test_reject_overspend_and_invalid_symbol():
    assert client.post('/paper/buy',json={'symbol':'BTCUSDT','quantity':1,'price':50000}).status_code==400
    assert client.post('/paper/buy',json={'symbol':'DOGEUSDT','quantity':1,'price':1}).status_code==422

def test_risk_trigger_closes_position():
    client.post('/paper/buy',json={'symbol':'ETHUSDT','quantity':0.1,'price':2000})
    r=client.put('/paper/positions/ETHUSDT/risk',json={'stop_loss':1900,'take_profit':2200})
    assert r.status_code==200
    closed=client.post('/paper/monitor/ETHUSDT?price=1890')
    assert closed.status_code==200 and closed.json()['closed'] is True
    assert closed.json()['trigger']=='stop_loss'

def test_risk_levels_validate_against_entry():
    client.post('/paper/buy',json={'symbol':'SOLUSDT','quantity':1,'price':100})
    assert client.put('/paper/positions/SOLUSDT/risk',json={'stop_loss':101}).status_code==400
    assert client.put('/paper/positions/SOLUSDT/risk',json={'take_profit':99}).status_code==400

def test_report_has_fees_and_counts():
    client.post('/paper/buy',json={'symbol':'BTCUSDT','quantity':0.001,'price':50000})
    r=client.get('/paper/report').json()
    assert r['trade_count']==1 and r['fees_paid']>0 and r['mode']=='paper_only'


def test_indicator_calculation_on_flat_market():
    values = m.calculate_indicators([100.0] * 60)
    assert values['rsi_14'] == 50.0
    assert values['ema_12'] == 100.0
    assert values['ema_26'] == 100.0
    assert values['macd'] == 0.0
    assert values['macd_signal'] == 0.0
    assert values['ema_50'] == 100.0


def test_indicator_calculation_rejects_short_series():
    try:
        m.calculate_indicators([1.0] * 20)
        assert False, 'Expected insufficient-candles error'
    except ValueError as exc:
        assert '35' in str(exc)


def test_market_indicators_endpoint_uses_public_candle_data(monkeypatch):
    candles = {'symbol': 'BTCUSDT', 'interval': '1m', 'klines': [[0, '1', '1', '1', '100', '0']] * 60}
    monkeypatch.setattr(m, 'market_klines', lambda symbol, limit: candles)
    response = client.get('/market/indicators/BTCUSDT')
    assert response.status_code == 200
    body = response.json()
    assert body['mode'] == 'analysis_only_paper_trading'
    assert body['indicators']['rsi_14'] == 50.0
    assert body['source'] == 'Binance public market data'


def test_signal_requires_all_three_bullish_conditions():
    values = {'rsi_14': 60.0, 'macd': 2.0, 'macd_signal': 1.0, 'ema_12': 105.0, 'ema_26': 100.0}
    result = m.build_signal(values)
    assert result['signal'] == 'BUY'
    assert result['score'] == 100
    assert 'احتمال ربح' in result['score_label']


def test_signal_returns_hold_when_conditions_conflict():
    values = {'rsi_14': 75.0, 'macd': 2.0, 'macd_signal': 1.0, 'ema_12': 105.0, 'ema_26': 100.0}
    assert m.build_signal(values)['signal'] == 'HOLD'


def test_backtest_executes_on_next_candle_and_charges_fees(monkeypatch):
    candles = [[i, str(100+i), '0', '0', str(100+i), '0'] for i in range(40)]
    signals = iter(['BUY', 'SELL', 'HOLD', 'HOLD'])
    monkeypatch.setattr(m, 'calculate_indicators', lambda closes: {})
    monkeypatch.setattr(m, 'build_signal', lambda values: {'signal': next(signals)})
    result = m.backtest_candles(candles)
    assert result['trades'][0]['execution_candle'] == result['trades'][0]['signal_candle'] + 1
    assert result['trades'][0]['price'] == float(candles[result['trades'][0]['execution_candle']][1])
    assert result['trades'][0]['fee'] > 0
    assert result['closed_trades'] == 1


def test_backtest_endpoint_does_not_change_paper_account(monkeypatch):
    candles = [[i, '100', '101', '99', '100', '1'] for i in range(80)]
    monkeypatch.setattr(m, 'market_klines', lambda symbol, limit: {'klines': candles})
    before = client.get('/paper/account').json()['cash']
    response = client.get('/paper/backtest/BTCUSDT?limit=80')
    after = client.get('/paper/account').json()['cash']
    assert response.status_code == 200
    assert response.json()['mode'] == 'historical_paper_backtest_only'
    assert before == after


def test_backtest_rejects_insufficient_candles():
    try:
        m.backtest_candles([[i, '1', '1', '1', '1', '1'] for i in range(20)])
        assert False, 'Expected insufficient candles error'
    except ValueError as exc:
        assert '37' in str(exc)


def test_signal_endpoint_returns_analysis_only(monkeypatch):
    candles = {'symbol':'BTCUSDT','interval':'1m','klines':[[i,'100','101','99',str(100+i),'1'] for i in range(60)]}
    monkeypatch.setattr(m, 'market_klines', lambda symbol, limit: candles)
    response = client.get('/market/signal/BTCUSDT')
    assert response.status_code == 200
    assert response.json()['mode'] == 'analysis_only_paper_trading'
    assert response.json()['signal'] in {'BUY','SELL','HOLD'}


def test_backtest_endpoint_requires_room_for_excluded_open_candle():
    assert client.get('/paper/backtest/BTCUSDT?limit=37').status_code == 400


def test_risk_size_respects_risk_budget_and_is_calculation_only():
    before = client.get('/paper/account').json()['cash']
    response = client.post('/paper/risk/size', json={
        'symbol':'BTCUSDT','entry_price':100,'stop_loss':95,'risk_percent':1
    })
    assert response.status_code == 200
    body = response.json()
    assert body['quantity'] > 0
    assert body['estimated_loss_at_stop'] >= body['risk_cash_target']
    assert body['mode'] == 'paper_risk_calculator_only'
    assert client.get('/paper/account').json()['cash'] == before
    assert client.get('/paper/positions').json() == []

def test_risk_size_rejects_stop_above_entry_and_risk_over_two_percent():
    base = {'symbol':'ETHUSDT','entry_price':100,'stop_loss':95,'risk_percent':1}
    bad_stop = {**base, 'stop_loss':101}
    high_risk = {**base, 'risk_percent':2.1}
    assert client.post('/paper/risk/size', json=bad_stop).status_code == 400
    assert client.post('/paper/risk/size', json=high_risk).status_code == 422

def test_risk_size_is_capped_by_available_cash():
    result = m.calculate_position_size(10, 100, 99.99, 2)
    assert result['affordability_limited'] is True
    assert result['notional'] + result['estimated_entry_fee'] <= 10.000001
