const safeNumber = value => {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(typeof value === 'string' ? value.replace('%', '') : value);
  return Number.isFinite(number) ? number : null;
};

// Kept by the provider across route changes. Retry only items whose save failed.
export function createBacktestSaver(request) {
  const saved = new WeakMap();
  return async (results, fallback = {}) => {
    const payloads = buildBacktestSaveRequests(results, fallback);
    if (!results || !payloads.length) return 0;
    let entries = saved.get(results);
    if (!entries) { entries = new Map(); saved.set(results, entries); }
    for (const [index, payload] of payloads.entries()) {
      if (!entries.has(index)) {
        const pending = Promise.resolve().then(() => request(payload)).catch(error => {
          entries.delete(index);
          throw error;
        });
        entries.set(index, pending);
      }
      await entries.get(index);
    }
    return payloads.length;
  };
}

export function buildBacktestSaveRequests(results, fallback = {}) {
  const items = results?.isBatch ? results.items.filter(item => item.success) : [{ data: results }];
  return items.filter(item => item.data?.metrics).map(item => {
    const data = item.data;
    const request = { ...fallback, ...data.backtest_request };
    const symbol = item.symbol || data.data_info?.symbol || request.symbol;
    const payload = {
      symbol: Array.isArray(symbol) ? symbol[0] : symbol,
      period: data.data_info?.period || request.period,
      strategy_name: data.strategy_info?.name || request.strategy_name,
      strategy_params: { ...request.strategy_params, ...data.strategy_info?.params },
      detail_data: data,
    };
    for (const key of ['initial_cash', 'final_value', 'net_profit', 'return_rate',
      'sharpe_ratio', 'max_drawdown', 'total_trades', 'win_rate']) {
      payload[key] = safeNumber(data.metrics[key]);
    }
    return payload;
  });
}
