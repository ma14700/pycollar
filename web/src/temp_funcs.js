
  const fetchSavedBacktests = async () => {
    setHistoryLoading(true);
    try {
      const response = await axios.get('http://localhost:8000/api/backtest/list');
      setSavedBacktests(response.data);
    } catch (error) {
      message.error('获取回测记录失败: ' + error.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleSaveBacktest = async () => {
    if (!results) return;
    try {
      const payload = {
        symbol: form.getFieldValue('symbol'),
        period: form.getFieldValue('period'),
        strategy_name: form.getFieldValue('strategy') || 'TrendFollowingStrategy',
        strategy_params: form.getFieldValue('params') || {}, // Assuming params are stored in form or state. Wait.
        initial_cash: results.metrics.initial_cash,
        final_value: results.metrics.final_value,
        net_profit: results.metrics.net_profit,
        return_rate: results.metrics.return_rate,
        sharpe_ratio: results.metrics.sharpe_ratio,
        max_drawdown: results.metrics.max_drawdown,
        total_trades: results.metrics.total_trades,
        win_rate: results.metrics.win_rate,
        detail_data: results
      };
      
      // We need to make sure strategy_params are correct. 
      // In onFinish, values are passed. But here we access form.
      // However, results object usually contains the params used?
      // Let's check results structure in previous tool output.
      // The backend returns `original` (with metrics) and `optimized`.
      // My `run_backtest` returns:
      // { "original": ..., "optimized": ..., "optimized_params": ..., "message": ... }
      // `original` has `metrics`.
      
      // Wait, `results` in state is the *response* from `/api/backtest`.
      // So `results.metrics` is WRONG if `results` is the root response object.
      // `results` has `original` and `optimized`.
      // I need to determine which one is currently being shown.
      // Usually, if optimized exists, we might show that?
      // Or `results` state IS the `original` part?
      
      // Let's check `onFinish` in App.jsx to see how `results` is set.
    
      await axios.post('http://localhost:8000/api/backtest/save', payload);
      message.success('回测结果已保存');
      fetchSavedBacktests(); // Refresh list
    } catch (error) {
      message.error('保存失败: ' + error.message);
    }
  };

  const handleViewHistory = async (id) => {
    setHistoryLoading(true);
    try {
      const response = await axios.get(`http://localhost:8000/api/backtest/${id}`);
      setViewingHistory(response.data);
    } catch (error) {
      message.error('获取详情失败: ' + error.message);
    } finally {
      setHistoryLoading(false);
    }
  };
