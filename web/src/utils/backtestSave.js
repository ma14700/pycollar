const safeNumber = value => {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(typeof value === 'string' ? value.replace('%', '') : value);
  return Number.isFinite(number) ? number : null;
};

export function buildBacktestSaveRequests(results, fallback = {}) {
  const items = results?.isBatch ? results.items.filter(item => item.success) : [{ data: results }];
  return items.filter(item => item.data?.metrics).map(item => {
    const data = item.data;
    const request = { ...fallback, ...data.backtest_request };
    const symbol = item.symbol || data.data_info?.symbol || request.symbol;
    const payload = {
      symbol: Array.isArray(symbol) ? symbol[0] : symbol,
      period: data.data_info?.period || request.period,
      strategy_name: request.strategy_name,
      strategy_params: request.strategy_params || {},
      detail_data: data,
    };
    for (const key of ['initial_cash', 'final_value', 'net_profit', 'return_rate',
      'sharpe_ratio', 'max_drawdown', 'total_trades', 'win_rate']) {
      payload[key] = safeNumber(data.metrics[key]);
    }
    return payload;
  });
}
