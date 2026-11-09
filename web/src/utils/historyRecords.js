// Read bounded pages before calculating statistics over all saved records.
export async function loadHistoryRecords(request, signal) {
    const items = [];
    let cursor;
    do {
        signal?.throwIfAborted();
        const { data } = await request('/api/backtest/history', { params: { cursor, limit: 200 }, signal });
        if (!Array.isArray(data.items)) throw new Error('历史记录响应格式无效');
        items.push(...data.items);
        if (!data.has_more) return items;
        const next = data.next_cursor;
        if (!Number.isInteger(next) || next <= 0 || (cursor !== undefined && next >= cursor)) {
            throw new Error('历史记录分页游标无效');
        }
        cursor = next;
    } while (true);
}
