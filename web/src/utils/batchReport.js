import { finiteNumber } from './backtestAnalytics.js';
import { accountReturn } from './contractEstimate.js';

export function batchReportRows(items = []) {
    return items.map((item,index) => {
        const metrics = item.data?.metrics || {};
        const request = item.data?.backtest_request || {};
        return { key:String(index),symbol:item.symbol || request.symbol || '未知合约',
            strategy:item.strategy_name || request.strategy_name || item.data?.strategy_info?.name || '未知策略',
            success:Boolean(item.success),error:item.error || '回测失败', data:item.data,
            profit:finiteNumber(metrics.net_profit),returnPct:accountReturn(metrics),
            drawdown:finiteNumber(metrics.max_drawdown),winRate:finiteNumber(metrics.win_rate),trades:finiteNumber(metrics.total_trades),
            perHandProfit:finiteNumber(metrics.one_hand_net_profit),perHandReturn:finiteNumber(metrics.one_hand_profit_pct),
            basis:metrics.one_hand_return_basis,period:item.data?.data_info?.period || request.period,
        };
    });
}

export function equitySparkline(curve = [], width = 240, height = 58) {
    if (!Array.isArray(curve)) return [];
    const values = curve.map(point=>finiteNumber(point?.value));
    const valid = values.filter(value=>value!==null);
    if (valid.length < 2) return [];
    const min=Math.min(...valid), max=Math.max(...valid), range=max-min || 1;
    const segments=[];
    let segment=[];
    values.forEach((value,index)=>{
        if(value===null) { if(segment.length) segments.push(segment.join(' ')); segment=[]; return; }
        const x=curve.length>1?index/(curve.length-1)*(width-4)+2:2;
        const y=max===min?height/2:height-5-(value-min)/range*(height-10);
        segment.push(`${segment.length?'L':'M'}${x.toFixed(2)},${y.toFixed(2)}`);
    });
    if(segment.length) segments.push(segment.join(' '));
    return segments;
}
