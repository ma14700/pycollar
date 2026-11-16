import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from server.core.synthetic_hour import synthesize_hour
from server.core.data_loader import fetch_data


def bars(index):
    prices = np.arange(len(index), dtype=float) + 100
    return pd.DataFrame({'Open':prices, 'High':prices+2, 'Low':prices-1, 'Close':prices+1,
                         'Volume':np.ones(len(index)), 'OpenInterest':np.arange(len(index))}, index=index)


class SyntheticHourTests(unittest.TestCase):
    def test_commodity_respects_breaks_and_closes(self):
        index = pd.date_range('2026-11-16 09:00','2026-11-16 14:55',freq='5min')
        index = index[((index.hour < 10) | (index >= pd.Timestamp('2026-11-16 10:30')) | (index < pd.Timestamp('2026-11-16 10:15'))) &
                      ((index < pd.Timestamp('2026-11-16 11:30')) | (index >= pd.Timestamp('2026-11-16 13:30')))]
        data = bars(index)
        result = synthesize_hour(data,'JM2701',now='2026-11-16 15:00')
        self.assertEqual(result.index.strftime('%H:%M').tolist(), ['09:00','10:00','11:15','14:15'])
        self.assertEqual(result['Volume'].tolist(), [12,12,12,9])
        self.assertEqual(result.loc['2026-11-16 10:00','Close'], data.loc['2026-11-16 11:10','Close'])
        self.assertEqual(result.loc['2026-11-16 11:15','Close'], data.loc['2026-11-16 14:10','Close'])
        partial = synthesize_hour(data,'JM2701',now='2026-11-16 11:10')
        self.assertEqual(partial.index.strftime('%H:%M').tolist(), ['09:00'])
        with self.assertRaisesRegex(ValueError, '存在缺失'):
            synthesize_hour(data.drop(pd.Timestamp('2026-11-16 10:40')), 'JM2701',now='2026-11-16 15:00')

    def test_stock_and_akshare_end_timestamps(self):
        index = pd.date_range('2026-11-16 09:35','2026-11-16 11:30',freq='5min')
        result = synthesize_hour(bars(index),'sh600000',market_type='stock',provider='akshare',now='2026-11-16 12:00')
        self.assertEqual(result.index.strftime('%H:%M').tolist(), ['09:30','10:30'])
        self.assertEqual(result['Volume'].tolist(), [12,12])

    def test_night_session_spans_midnight(self):
        index = pd.date_range('2026-11-16 23:00','2026-11-17 02:25',freq='5min')
        result = synthesize_hour(bars(index),'AU2701',now='2026-11-17 03:00')
        self.assertEqual(result.index.strftime('%H:%M').tolist(), ['23:00','00:00','01:00','02:00'])
        self.assertEqual(result['Volume'].tolist(), [12,12,12,6])

    def test_loader_uses_original_provider_5_minute_data(self):
        index = pd.date_range('2026-11-16 09:00', periods=12, freq='5min')
        with patch('server.core.tq_provider.fetch_tq_data', return_value=bars(index)) as load:
            result=fetch_data('JM2701',period='60',data_provider='tqsdk',synthesize_60=True)
        self.assertEqual(load.call_args.args[1], '5')
        self.assertEqual(result.attrs['data_info']['hourly_mode'], 'trading_time')

    def test_loader_refuses_short_source_history_when_range_requested(self):
        index = pd.date_range('2026-11-16 09:00', periods=12, freq='5min')
        with patch('server.core.tq_provider.fetch_tq_data', return_value=bars(index)):
            with self.assertRaisesRegex(ValueError, '5分钟行情不足'):
                fetch_data('JM2701', period='60', data_provider='tqsdk', synthesize_60=True,
                           required_start_date='2026-08-01')
