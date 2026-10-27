const price = value => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null;
    return value;
};
const rounded = value => {
    if (!Number.isFinite(value)) return null;
    const result = Number(value.toFixed(10));
    return result === 0 ? 0 : result;
};
const change = (close, reference) => close === null || reference === null ? null : rounded(close - reference);
const percentChange = (close, reference) => close === null || reference === null ? null : rounded((close / reference - 1) * 100);

// ECharts candles use [open, close, low, high]. The first following bar's
// previous close must come from the matching window, not its own open.
export function buildFollowingDetails(match) {
    const candles = match?.following?.ohlc || [];
    const dates = match?.following?.dates || [];
    const anchor = price(match?.ohlc?.at(-1)?.[1]);
    let previous = anchor;
    return Array.from({ length: Math.max(candles.length, dates.length) }, (_, index) => {
        const open = price(candles[index]?.[0]);
        const close = price(candles[index]?.[1]);
        const row = {
            key: index + 1,
            sequence: index + 1,
            date: dates[index] || null,
            open, close, previous_close: previous,
            body_change: change(close, open),
            change: change(close, previous),
            change_pct: percentChange(close, previous),
            cumulative_change: change(close, anchor),
            cumulative_pct: percentChange(close, anchor),
        };
        // Missing prices break the adjacent-bar comparison; never skip over
        // a missing bar and label a multi-bar move as a single-bar change.
        previous = close;
        return row;
    });
}
