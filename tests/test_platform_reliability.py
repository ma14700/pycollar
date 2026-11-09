"""Regression checks for optimization and the history API, using no user data."""
import contextlib
import inspect
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import main
from core.optimizer import StrategyOptimizer
from core.database import Base, BacktestRecord
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from fastapi import HTTPException
from core.history import history_page


def result(profit):
    return {'metrics': {'initial_cash': 10000, 'final_value': 10000 + profit}}


class OptimizerTests(unittest.TestCase):
    def test_unsupported_strategy_never_runs_trials(self):
        optimizer = StrategyOptimizer()
        with patch.object(optimizer.engine, 'run') as run:
            self.assertIsNone(optimizer.optimize('JM0', '60', {}, strategy_name='MA20MA55RR3Strategy')[1])
            run.assert_not_called()

    def test_only_strict_improvements_are_returned_and_duplicates_skipped(self):
        for profit, improved in [(50, False), (100, False), (110, True)]:
            optimizer = StrategyOptimizer()
            with patch.object(optimizer.engine, 'run', return_value=result(profit)) as run, \
                 patch('core.optimizer.random.sample', return_value=['fast_period']), \
                 patch('core.optimizer.random.choice', return_value=7), contextlib.redirect_stdout(io.StringIO()):
                _, best = optimizer.optimize('JM0', '60', {'fast_period': 10},
                                             baseline_result=result(100), max_trials=5)
            self.assertEqual(best is not None, improved)
            self.assertEqual(run.call_count, 1)

    def test_dkx_search_changes_real_parameters(self):
        optimizer = StrategyOptimizer()
        with patch.object(optimizer.engine, 'run', return_value=result(200)) as run, \
             patch('core.optimizer.random.sample', return_value=['take_profit_points', 'stop_loss_points']), \
             patch('core.optimizer.random.choice', side_effect=[150, 80]), contextlib.redirect_stdout(io.StringIO()):
            optimizer.optimize('JM0', 'daily', {}, strategy_name='DKXFixedTPSLStrategy',
                               baseline_result=result(0), max_trials=1)
        self.assertEqual(run.call_args.args[2], {'take_profit_points': 150, 'stop_loss_points': 80})


class HistoryTests(unittest.TestCase):
    def test_cursor_pages_survive_inserts_and_deletes_without_duplicates(self):
        for index in range(7):
            self.db.add(BacktestRecord(symbol=str(index), detail_data={'metrics': {}}))
        self.db.commit()
        first = history_page(self.db, limit=3)
        self.assertEqual([item['id'] for item in first['items']], [7, 6, 5])
        self.db.add(BacktestRecord(symbol='new', detail_data={}))
        self.db.query(BacktestRecord).filter(BacktestRecord.id == 4).delete()
        self.db.commit()
        second = history_page(self.db, cursor=first['next_cursor'], limit=3)
        self.assertEqual([item['id'] for item in second['items']], [3, 2, 1])
        self.assertFalse(second['has_more'])
        self.assertIsNone(second['next_cursor'])

    def test_backtest_does_not_write_hidden_summary_records(self):
        metrics = dict(initial_cash=10000, final_value=10100, net_profit=100)
        with patch.object(main, 'BacktestEngine') as engine, \
             patch.object(main, 'BacktestRecord') as record, contextlib.redirect_stdout(io.StringIO()):
            engine.return_value.run.return_value = {'metrics': metrics}
            response = main.run_backtest(main.BacktestRequest(symbol='JM0', period='daily', strategy_params={}))
        record.assert_not_called()
        self.assertEqual(response['metrics'], metrics)

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_missing_detail_and_delete_preserve_404(self):
        for endpoint in (main.get_backtest_detail, main.delete_backtest):
            with self.assertRaises(HTTPException) as raised:
                endpoint(999, self.db)
            self.assertEqual(raised.exception.status_code, 404)

    def test_list_does_not_select_heavy_json_and_detail_remains_complete(self):
        self.db.add(BacktestRecord(symbol='JM0', detail_data={'large': [1] * 1000}))
        self.db.commit()
        statements = []
        event.listen(self.engine, 'before_cursor_execute', lambda conn, cursor, statement, *args: statements.append(statement))
        records = main.list_backtests(self.db)
        self.assertEqual(len(records), 1)
        selected = statements[0].split('FROM')[0]
        self.assertNotIn('detail_data', selected)
        self.assertNotIn('strategy_params', selected)
        self.assertEqual(len(main.get_backtest_detail(records[0]['id'], self.db)['detail_data']['large']), 1000)

    def test_blocking_handlers_are_threadpool_routes(self):
        for handler in (main.scan_strategy, main.save_backtest_result, main.list_backtests,
                        main.get_backtest_detail, main.delete_backtest):
            self.assertFalse(inspect.iscoroutinefunction(handler))

    def test_database_failure_rolls_back(self):
        request = main.SaveBacktestRequest(symbol='JM0', period='daily', strategy_name='test',
                                            strategy_params={}, detail_data={})
        with patch.object(self.db, 'commit', side_effect=RuntimeError('test write failure')), \
             patch.object(self.db, 'rollback', wraps=self.db.rollback) as rollback, \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaises(HTTPException):
            main.save_backtest_result(request, self.db)
        rollback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
