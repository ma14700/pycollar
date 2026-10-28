// Owned by BacktestProvider, which stays mounted above the router.
// Route subscribers can come and go without owning or canceling this queue.
export function createBacktestTask(request, now = Date.now) {
    let state = { loading: false, activeRun: null, results: null, runError: null };
    let pending = null;
    const listeners = new Set();
    const update = patch => {
        state = { ...state, ...patch };
        listeners.forEach(listener => listener());
    };

    const start = ({ tasks, ...details }) => {
        if (state.loading) return pending;
        if (!Array.isArray(tasks) || !tasks.length) throw new Error('请至少选择一个回测目标');
        // Freeze submitted parameters independently of later form edits or navigation.
        const queue = structuredClone(tasks);
        const run = { ...details, total: queue.length, completed: 0, failed: 0,
            startedAt: now(), finishedAt: null, status: 'running', symbol: queue[0].payload.symbol };
        pending = Promise.resolve().then(async () => {
            const items = [];
            try {
                for (const { payload, symbolName } of queue) {
                    update({ activeRun: { ...state.activeRun, symbol: payload.symbol, symbolName,
                        provider: payload.data_provider } });
                    try {
                        const data = await request(payload);
                        items.push({ symbol: payload.symbol, success: true,
                            data: { ...data, backtest_request: payload } });
                    } catch (error) {
                        items.push({ symbol: payload.symbol, success: false,
                            error: error.response?.data?.detail || error.message || '回测请求失败' });
                    }
                    update({ activeRun: { ...state.activeRun, completed: items.length,
                        failed: items.filter(item => !item.success).length } });
                }
                const summary = { total: items.length, success: items.filter(item => item.success).length,
                    failed: items.filter(item => !item.success).length };
                update({ results: queue.length === 1 ? items[0].data || null : { isBatch: true, items, summary },
                    runError: queue.length === 1 && !items[0].success ? items[0].error : null });
            } catch (error) {
                update({ runError: error.message || '回测执行失败' });
            } finally {
                pending = null;
                update({ loading: false, activeRun: { ...state.activeRun, finishedAt: now(),
                    status: state.runError || state.activeRun.failed === queue.length ? 'failed' : 'completed' } });
            }
            return state;
        });
        update({ loading: true, results: null, runError: null, activeRun: run });
        return pending;
    };

    return { start, getSnapshot: () => state, subscribe: listener => {
        listeners.add(listener);
        return () => listeners.delete(listener);
    } };
}
