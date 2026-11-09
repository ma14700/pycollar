import asyncio
import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core.engine import BacktestEngine
from core.parameters import execution_options
from core.result_window import result_window
from core.migrations import upgrade_database, schema_version
from core.errors import unexpected_error


class ExecutionOptionsTests(unittest.TestCase):
    def test_boolean_execution_option_is_explicit(self):
        for value, expected in [(True, True), (False, False), ('true', True), ('false', False)]:
            self.assertIs(execution_options({'optimal_entry': value})['optimal_entry'], expected)
        for value in [1, 0, None, [], 'yes', '']:
            with self.assertRaises(ValueError): execution_options({'optimal_entry': value})

    def test_invalid_parameters_fail_before_market_data_fetch(self):
        for params in [{'optimal_entry': 'no'}, {'fast_period': -1}, {'slow_period': True}, {'print_log': 1}]:
            with patch('core.engine.fetch_data') as fetch:
                result = BacktestEngine().run('JM0', 'daily', params)
            self.assertIn('error', result)
            fetch.assert_not_called()
        for start, end in [('not-a-date', None), ('2026-01-01', '2025-01-01')]:
            with patch('core.engine.fetch_data') as fetch:
                result = BacktestEngine().run('JM0', 'daily', {}, start_date=start, end_date=end)
            self.assertIn('error', result)
            fetch.assert_not_called()

    def test_false_string_stays_false_and_execution_option_is_not_a_strategy_parameter(self):
        df = pd.DataFrame({'Open': 100., 'High': 101., 'Low': 99., 'Close': 100., 'Volume': 1},
                          index=pd.date_range('2025-01-01', periods=85))
        with patch('core.engine.fetch_data', return_value=df), contextlib.redirect_stdout(io.StringIO()):
            result = BacktestEngine().run('JM0', 'daily', {'optimal_entry': 'false', 'print_log': False})
        self.assertNotIn('error', result)
        self.assertIs(result['execution_info']['optimal_entry'], False)
        self.assertNotIn('optimal_entry', result['strategy_info']['params'])


class ResultWindowTests(unittest.TestCase):
    def test_invalid_execution_timestamps_fail_rather_than_surviving_filter(self):
        for trades, equity in [([{'date': 'invalid'}], []), ([], [{'value': 100}])]:
            with self.assertRaises(ValueError):
                result_window([], trades, equity, None, None, 100)

    def test_end_day_is_inclusive_and_plain_warning_is_preserved(self):
        logs, trades, equity = result_window(['warning'], [{'date': '2025-01-02 23:59:00'}],
                                             [{'date': '2025-01-03', 'value': 110}],
                                             '2025-01-01', '2025-01-02', 100)
        self.assertEqual(logs, ['warning'])
        self.assertEqual(len(trades), 1)
        self.assertEqual(equity, [])


class MigrationTests(unittest.TestCase):
    def test_additive_upgrade_preserves_rows_and_is_idempotent(self):
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE backtest_records (id INTEGER PRIMARY KEY, symbol TEXT)'))
            connection.execute(text("INSERT INTO backtest_records VALUES (1, 'JM0')"))
        self.assertEqual(upgrade_database(engine), 1)
        self.assertEqual(upgrade_database(engine), 1)
        with engine.connect() as connection:
            self.assertEqual(schema_version(connection), 1)
            row = connection.execute(text('SELECT symbol, strategy_name, detail_data FROM backtest_records')).one()
            self.assertEqual(tuple(row), ('JM0', 'TrendFollowingStrategy', None))
        engine.dispose()

    def test_future_schema_is_rejected(self):
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)'))
            connection.execute(text('INSERT INTO schema_migrations VALUES (99)'))
        with self.assertRaises(RuntimeError): upgrade_database(engine)
        engine.dispose()


class PublicErrorsTests(unittest.TestCase):
    def test_unexpected_error_logs_diagnostics_without_exposing_them(self):
        error = RuntimeError('private/local/path diagnostic')
        request = SimpleNamespace(method='GET', url=SimpleNamespace(path='/api/example'))
        with self.assertLogs('pycollar.api', level='ERROR') as captured:
            response = asyncio.run(unexpected_error(request, error))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('private/local/path', response.body.decode())
        self.assertIn('private/local/path', '\n'.join(captured.output))


if __name__ == '__main__':
    unittest.main()
