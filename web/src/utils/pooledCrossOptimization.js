// Pool the point totals and counts first; never average ratios from different contracts.
function pooledPointStats(parts) {
    const keys=['gross_profit_points','gross_loss_points','profit_count','loss_count'];
    if (!parts.length || !parts.every(part=>keys.every(key=>Number.isFinite(part[key])))) return {};
    const totals=Object.fromEntries(keys.map(key=>[key,parts.reduce((sum,part)=>sum+part[key],0)]));
    const avg_profit_points=totals.profit_count ? totals.gross_profit_points/totals.profit_count : null;
    const avg_loss_points=totals.loss_count ? totals.gross_loss_points/totals.loss_count : null;
    return {...totals,avg_profit_points,avg_loss_points,
        profit_loss_ratio:avg_profit_points != null && avg_loss_points > 0 ? avg_profit_points/avg_loss_points : null};
}

// Pool the actual outcomes, retaining each independent contract's identity.
export function pooledCrossGroups(runs) {
    const groups = new Map();
    for (const run of runs.filter(entry=>Array.isArray(entry.data?.groups))) {
        for (const group of run.data.groups) {
            if (!groups.has(group.pair)) groups.set(group.pair, {pair:group.pair,pending:0,expired:0,events:[],excluded:[],
                summary:{golden:{total:0,up:0,down:0,flat:0},death:{total:0,up:0,down:0,flat:0}},pnlParts:{golden:[],death:[]}});
            const result=groups.get(group.pair);
            result.pending += group.pending || 0; result.expired += group.expired || 0;
            result.events.push(...group.events.map(event=>({...event,symbol:run.symbol})));
            result.excluded.push(...(group.excluded || []).map(event=>({...event,symbol:run.symbol})));
            for (const direction of ['golden','death']) {
                result.pnlParts[direction].push(group.summary[direction]);
                for (const key of ['total','up','down','flat']) result.summary[direction][key] += group.summary[direction][key];
            }
        }
    }
    return Array.from(groups.values(), group=>{
        for (const direction of ['golden','death']) {
            const summary=group.summary[direction];
            const rate=count=>summary.total ? Math.round(count/summary.total*10000)/100 : null;
            summary.up_pct=rate(summary.up);
            summary.match_pct=rate(direction==='golden'?summary.up:summary.down);
            Object.assign(summary,pooledPointStats(group.pnlParts[direction]));
        }
        delete group.pnlParts;
        return group;
    });
}

// Pool raw counts per horizon; never average per-contract percentages.
export function pooledCrossOptimization(runs) {
    const successful = runs.filter(run => Array.isArray(run.data?.optimization));
    if (!successful.length) return [];
    const groups = new Map();
    for (const run of successful) {
        for (const item of run.data.optimization) {
            const key = `${item.pair}-${item.direction}`;
            if (!groups.has(key)) groups.set(key, {pair:item.pair,direction:item.direction,byBars:new Map()});
            const group = groups.get(key);
            for (const point of item.series) {
                if (!group.byBars.has(point.bars)) group.byBars.set(point.bars,{bars:point.bars,wins:0,total:0,pnlParts:[]});
                const sum = group.byBars.get(point.bars);
                sum.wins += point.wins; sum.total += point.total;
                sum.pnlParts.push(point);
            }
        }
    }
    return Array.from(groups.values(), group => {
        const series = Array.from(group.byBars.values()).sort((a,b)=>a.bars-b.bars)
            .map(({pnlParts,...row})=>({...row,match_pct:row.total ? Math.round(row.wins/row.total*10000)/100 : null,...pooledPointStats(pnlParts)}));
        let best = null;
        for (const row of series) if (row.total && (!best || row.wins * best.total > best.wins * row.total)) best = row;
        return {pair:group.pair,direction:group.direction,best,series};
    });
}

// Rebuild samples from the same returned candle snapshot and signal audit.
export function pooledBestEvents(runs, item) {
    if (!item?.best) return {events:[],complete:true};
    const events = [];
    for (const run of runs.filter(entry=>Array.isArray(entry.data?.optimization))) {
        const chart = run.data.chart;
        const group = run.data.groups.find(entry=>entry.pair===item.pair);
        if (!chart || !group) return {events:[],complete:false};
        const positions = new Map(chart.dates.map((date,index)=>[date,index]));
        for (const signal of [...group.events,...(group.excluded || [])]) {
            if (signal.direction !== item.direction) continue;
            const index = positions.get(signal.signal);
            if (index === undefined) return {events:[],complete:false};
            const begin = index + (run.data.observation_delay || 0);
            let opposite = Infinity;
            if (run.data.reverse_exit && signal.next_opposite) {
                opposite = positions.get(signal.next_opposite);
                if (opposite === undefined) return {events:[],complete:false};
            }
            if (opposite <= begin) continue;
            const end = Math.min(begin + item.best.bars, opposite);
            if (end >= chart.dates.length) continue;
            const signalClose = chart.ohlc[index]?.[1], startClose = chart.ohlc[begin]?.[1], endClose = chart.ohlc[end]?.[1];
            if (![signalClose,startClose,endClose].every(Number.isFinite) || startClose <= 0) return {events:[],complete:false};
            const change = endClose - startClose;
            events.push({symbol:run.symbol,direction:item.direction,signal:chart.dates[index],signal_close:signalClose,
                start:chart.dates[begin],start_close:startClose,end:chart.dates[end],end_close:endClose,bars:end-begin,exit_reason:opposite <= begin + item.best.bars ? 'reverse' : 'horizon',
                return_pct:(endClose/startClose-1)*100,outcome:change>0?'up':change<0?'down':'flat'});
        }
    }
    const wins = events.filter(event=>event.outcome===(item.direction==='golden'?'up':'down')).length;
    return {events,complete:events.length===item.best.total && wins===item.best.wins};
}
