const periods = [20,55,144];
const colors = {20:'#e8a83c',55:'#668bdc',144:'#a070d4'};

function legacyAverage(chart, period) {
    const values = chart.ohlc || [];
    let sum = 0, valid = 0;
    return values.map((bar,index)=>{
        const next = bar?.[1];
        if (typeof next === 'number' && Number.isFinite(next)) { sum += next; valid++; }
        if (index >= period) {
            const old = values[index-period]?.[1];
            if (typeof old === 'number' && Number.isFinite(old)) { sum -= old; valid--; }
        }
        return valid === period ? sum/period : null;
    });
}

export function candleAssistAverages(chart, pair) {
    const selectedPeriods = new Set(pair.split('/').map(Number));
    const selected = Object.fromEntries(periods.map(n=>[`MA${n}`,selectedPeriods.has(n)]));
    const series = periods.map(n=>({name:`MA${n}`,type:'line',data:chart.ma?.[String(n)] || legacyAverage(chart,n),showSymbol:false,smooth:false,
        itemStyle:{color:colors[n]},lineStyle:{width:1.5,color:colors[n]}}));
    return {selected,series};
}
