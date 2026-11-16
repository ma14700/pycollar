export const compareCrossText = key => (a,b) => String(a[key] ?? '').localeCompare(String(b[key] ?? ''), 'zh-CN', {numeric:true});
export const compareCrossNumber = key => (a,b) => Number(a[key]) - Number(b[key]);

export function crossProfitPoints(event) {
    const {start_close:start, end_close:end, direction} = event;
    if (!Number.isFinite(start) || !Number.isFinite(end) || !['golden','death'].includes(direction)) return null;
    const points = direction === 'golden' ? end-start : start-end;
    return Math.round(points * 1e8) / 1e8;
}
