const numericPattern = '[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?';

export const parseLogItem = (log, index = 0) => {
    const structured = log && typeof log === 'object' ? log : null;
    const text = structured ? String(structured.content ?? structured.message ?? '') : String(log ?? '');
    const separator = text.indexOf(',');
    const hasDate = separator >= 0 && /^\d{4}-\d{2}-\d{2}/.test(text.slice(0, separator));
    const date = String(structured?.date ?? structured?.time ?? (hasDate ? text.slice(0, separator).trim() : ''));
    const content = hasDate ? text.slice(separator + 1).trim() : text;
    const action = String(structured?.action ?? content.match(/【(.*?)】/)?.[1] ?? '');
    const readNumber = (field, labels) => {
        const provided = structured?.[field];
        if (provided !== null && provided !== undefined && provided !== '' && Number.isFinite(Number(provided))) return Number(provided);
        for (const label of labels) {
            const match = content.match(new RegExp(`${label}\\s*(?:[:：]\\s*|\\s+)(${numericPattern})`));
            if (match && Number.isFinite(Number(match[1]))) return Number(match[1]);
        }
        return null;
    };
    const isSettlement = /交易利润|交易结算|平仓结算/.test(content) || structured?.kind === 'settlement';
    const isExecution = !isSettlement && (/交易执行|买入成交|卖出成交/.test(content) || structured?.kind === 'execution');
    let type = 'info';
    let kind = 'info';
    if (isSettlement) { type = 'profit'; kind = 'settlement'; }
    else if (isExecution) {
        kind = 'execution';
        if (/买多|开多|做多|平空|买入/.test(action || content.split(',')[0])) type = 'buy';
        else if (/卖空|开空|做空|平多|卖出/.test(action || content.split(',')[0])) type = 'sell';
        else type = 'profit';
    } else if (/警告|失败|错误|Error|拒绝|保证金不足|取消/.test(content)) { type = 'warning'; kind = 'warning'; }
    else if (/信号|金叉|死叉|开多仓|开空仓|反手做|平多信号|平空信号/.test(content)) { type = 'signal'; kind = 'signal'; }
    else if (/策略启动|回测开始|回测结束|窗口开始|数据结束检查/.test(content)) { type = 'system'; kind = 'system'; }
    return {
        key: index, date, content, type, kind, action, isSettlement, isExecution,
        price: readNumber('price', ['价格']), size: readNumber('size', ['数量']),
        comm: readNumber('comm', ['费用', '手续费']), pos: readNumber('pos', ['当前持仓']),
        cost: readNumber('cost', ['持仓成本', '成本']), mdd: readNumber('mdd', ['期间最大回撤']),
        pnl: readNumber('pnl', ['净利润', '净利']), pct: readNumber('pct', ['收益率']),
        dir: String(structured?.dir ?? content.match(/方向\s*[:：]\s*([^,，]+)/)?.[1]?.trim() ?? ''),
    };
};
