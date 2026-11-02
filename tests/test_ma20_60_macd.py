import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import backtrader as bt
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from core import strategy,engine
from core.execution_delay import SignalDelayBroker

NAME='MA20MA60DailyMACDStrategy'
def frame():
    rng=np.random.default_rng(7)
    prices=1000+np.cumsum(rng.normal(0,8,900))+30*np.sin(np.arange(900)/13)
    return pd.DataFrame({'Open':prices+.5,'Close':prices,'High':prices+2,'Low':prices-2,'Volume':100},index=pd.date_range('2023-01-01',periods=900))

def seeded_ema(series,period):
    result=pd.Series(np.nan,index=series.index)
    valid=series.dropna()
    if len(valid)<period:return result
    start=valid.index[period-1]
    source=series.loc[start:].copy()
    source.iloc[0]=valid.iloc[:period].mean()
    result.loc[start:]=source.ewm(span=period,adjust=False).mean()
    return result

def indicators(data):
    dif=seeded_ema(data.Close,12)-seeded_ema(data.Close,26)
    dea=seeded_ema(dif,9)
    signs=np.sign(data.Close.rolling(20).mean()-data.Close.rolling(60).mean()).replace(0,np.nan).ffill()
    cross=signs.diff().fillna(0)/2
    return dif,dea,cross

class MACDStrategyTests(unittest.TestCase):
    def simulate(self,data,entry=1,exit=1,auto=False):
        class Recorder(getattr(strategy,NAME)):
            def __init__(self):
                super().__init__();self.fills=[]
            def notify_order(self,order):
                if order.status==order.Completed:self.fills.append((len(self)-1,order.executed.size,order.executed.price,dict(order.info)))
                super().notify_order(order)
        cerebro=bt.Cerebro();cerebro.setbroker(SignalDelayBroker(entry_delay_bars=entry,exit_delay_bars=exit));cerebro.broker.setcash(10000000)
        cerebro.adddata(bt.feeds.PandasData(dataname=data));cerebro.addstrategy(Recorder,print_log=False,fixed_size=2,disable_auto_close=not auto)
        return cerebro.run()[0]

    def test_real_crosses_and_macd_states_match_independent_next_open_oracle(self):
        data=frame();dif,dea,cross=indicators(data);position=0;expected=[];filtered=0
        for i in range(60,len(data)-1):
            direction=int(cross.iloc[i])
            if not direction:continue
            allowed=(dif.iloc[i]-dea.iloc[i])*direction>0
            if allowed:target=direction*2
            else:
                filtered+=1
                target=0 if position*direction<0 else position
            if target!=position:expected.append((i+1,target-position));position=target
        result=self.simulate(data)
        self.assertGreater(filtered,0)
        self.assertTrue(any(size>0 for _,size in expected));self.assertTrue(any(size<0 for _,size in expected))
        self.assertEqual([(bar,size) for bar,size,_,_ in result.fills],expected)
        for bar,_,price,_ in result.fills:self.assertAlmostEqual(price,data.iloc[bar].Open)
        # State is DIF>DEA, not a required same-day MACD crossover.
        self.assertTrue(any(cross.iloc[bar-1]!=0 and np.sign((dif-dea).iloc[bar-1])==np.sign((dif-dea).iloc[bar-2]) for bar,_,_,_ in result.fills))

    def test_delayed_orders_keep_signal_time_and_distinguish_reversals(self):
        data=frame();result=self.simulate(data,entry=2,exit=3)
        self.assertTrue(result.fills)
        self.assertTrue(any(info['execution_kind']=='reversal' for *_,info in result.fills))
        for bar,_,price,info in result.fills:
            delay=2 if info['execution_kind']=='entry' else 3
            signal=data.index.get_loc(pd.Timestamp(info['signal_time']))
            self.assertEqual(bar,signal+delay);self.assertEqual(price,data.iloc[bar].Open)

    def test_hourly_uses_separate_daily_source_and_replay_keeps_daily_history(self):
        hourly=frame();hourly.index=pd.date_range('2024-01-01',periods=len(hourly),freq='h')
        daily=frame()
        def load(*args,**kwargs):return daily if kwargs.get('period')=='daily' else hourly
        with patch.object(engine,'fetch_data',side_effect=load) as fetch,contextlib.redirect_stdout(io.StringIO()):
            result=engine.BacktestEngine().analyze_detail('JM2701','60',{'fixed_size':2},strategy_name=NAME,data_provider='tqsdk')
            self.assertNotIn('error',result)
            self.assertEqual([call.kwargs['period'] for call in fetch.call_args_list],['60','daily'])
            self.assertTrue(all(call.kwargs['symbol']=='JM2701' for call in fetch.call_args_list))
            self.assertEqual(result['analysis_request']['daily_history_start'],str(daily.index[0]))
            replay=engine.BacktestEngine().analyze_detail(**result['analysis_request'])
        self.assertNotIn('error',replay)
        self.assertEqual(result['position_state'],replay['position_state'])
        dif,dea,_=indicators(daily)
        for i in [100,200,500,899]:
            decision=hourly.index[i]+pd.Timedelta(hours=1)
            known=daily.loc[daily.index+pd.Timedelta(hours=15,minutes=15)<=decision].index[-1]
            self.assertAlmostEqual(result['kline_data']['macd']['dif'][i],dif.loc[known])
            self.assertAlmostEqual(result['kline_data']['macd']['dea'][i],dea.loc[known])

    def test_unfinished_same_day_macd_cannot_change_intraday_signals(self):
        from core.daily_macd import align_daily_macd
        daily=frame();times=pd.to_datetime(['2024-01-01 10:00','2024-01-01 14:00','2024-01-01 21:00'])
        bars=daily.iloc[:3].copy();bars.index=times
        base=align_daily_macd(bars,daily,'60')
        changed=daily.copy();changed.loc['2024-01-01','Close']*=5
        other=align_daily_macd(bars,changed,'60')
        np.testing.assert_allclose(base.daily_dif.iloc[:2],other.daily_dif.iloc[:2])
        self.assertNotEqual(base.daily_dif.iloc[2],other.daily_dif.iloc[2])
        self.assertEqual(base.daily_macd_date.tolist(),['2023-12-31','2023-12-31','2024-01-01'])

    def test_missing_daily_history_fails_instead_of_using_hourly_macd(self):
        hourly=frame();hourly.index=pd.date_range('2024-01-01',periods=len(hourly),freq='h')
        for daily in [None,frame().iloc[:20]]:
            with patch.object(engine,'fetch_data',side_effect=[hourly,daily]),contextlib.redirect_stdout(io.StringIO()):
                result=engine.BacktestEngine().run('JM0','60',{},strategy_name=NAME,data_provider='tqsdk')
            self.assertIn('日线MACD',result['error'])

    def test_daily_history_seed_cannot_silently_change_on_replay(self):
        from core.daily_macd import align_daily_macd
        hourly=frame();hourly.index=pd.date_range('2024-01-01',periods=len(hourly),freq='h')
        with self.assertRaisesRegex(ValueError,'历史起点'):
            align_daily_macd(hourly,frame().iloc[10:],'60',history_start='2023-01-01')

    def test_short_history_returns_clear_requirement(self):
        with patch.object(engine,'fetch_data',return_value=frame().iloc[:60]),contextlib.redirect_stdout(io.StringIO()):
            result=engine.BacktestEngine().run('JM0','daily',{},strategy_name=NAME)
        self.assertIn('61',result['error'])

    def test_engine_chart_matches_actual_daily_macd_and_sma(self):
        data=frame();dif,dea,_=indicators(data)
        with patch.object(engine,'fetch_data',return_value=data),contextlib.redirect_stdout(io.StringIO()):
            result=engine.BacktestEngine().run('JM0','daily',{'fixed_size':2},strategy_name=NAME,start_date='2023-06-01')
        self.assertNotIn('error',result)
        chart=result['kline_data'];positions=data.index.get_indexer(pd.to_datetime(chart['dates']))
        np.testing.assert_allclose(chart['macd']['dif'],dif.iloc[positions].to_numpy(),rtol=0,atol=1e-8)
        np.testing.assert_allclose(chart['macd']['dea'],dea.iloc[positions].to_numpy(),rtol=0,atol=1e-8)
        self.assertEqual(chart['ma']['strategy_fast_label'],'MA20');self.assertEqual(chart['ma']['strategy_slow_label'],'MA60')

    def test_future_prices_do_not_change_earlier_signal_fills(self):
        data=frame();cut=500
        original=self.simulate(data)
        changed=data.copy();changed.iloc[cut:,:4]*=2
        other=self.simulate(changed)
        self.assertEqual([fill[:3] for fill in original.fills if fill[0]<cut],[fill[:3] for fill in other.fills if fill[0]<cut])

if __name__=='__main__':unittest.main()
