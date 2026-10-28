const nonNegativeNumber = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : null;
};

export const getProfitDistributionOption = (metrics = {}) => {
    const stats = metrics || {};
    const won = nonNegativeNumber(stats.won_trades);
    const lost = nonNegativeNumber(stats.lost_trades);
    const flat = nonNegativeNumber(stats.flat_trades) ?? 0;
    const total = nonNegativeNumber(stats.total_trades);
    const rate = nonNegativeNumber(stats.win_rate);
    const hasCounts = won !== null && lost !== null;
    const hasTrades = hasCounts ? won + lost + flat > 0 : total > 0 && rate !== null;

    if (!hasTrades) {
        return {
            title: {
                text: '暂无已平仓交易，无法统计盈亏分布',
                left: 'center', top: 'middle',
                textStyle: { color: '#999', fontSize: 14 },
            },
            series: [],
        };
    }

    // 旧记录可能只有胜率；统一按 0～100 的百分数处理。
    const win = hasCounts ? won : Math.min(rate, 100);
    const loss = hasCounts ? lost : 100 - win;

    return {
        title: { text: '盈亏分布', left: 'center' },
        legend: { bottom: 16, data: ['盈利交易', '亏损交易', ...(hasCounts && flat > 0 ? ['持平交易'] : [])] },
        tooltip: {
            trigger: 'item',
            formatter: hasCounts ? '{b}：{c} 笔（{d}%）' : '{b}：{d}%',
        },
        series: [{
            name: '盈亏分布',
            type: 'pie',
            radius: ['35%', '60%'],
            stillShowZeroSum: false,
            label: { formatter: '{b}\n{d}%' },
            data: [
                { value: win, name: '盈利交易', itemStyle: { color: '#cf1322' } },
                { value: loss, name: '亏损交易', itemStyle: { color: '#3f8600' } },
                ...(hasCounts && flat > 0 ? [{ value: flat, name: '持平交易', itemStyle: { color: '#94a3b8' } }] : []),
            ],
        }],
    };
};
