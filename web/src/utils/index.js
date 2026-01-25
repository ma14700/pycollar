import { symbolMap, futuresMap } from '../constants';

export const parseLogItem = (log, index) => {
    const logStr = String(log || '');
    const firstComma = logStr.indexOf(',');
    const date = firstComma !== -1 ? logStr.substring(0, firstComma).trim() : '';
    const content = firstComma !== -1 ? logStr.substring(firstComma + 1).trim() : logStr;
    
    let type = 'info';
    if (content.includes('买入') || content.includes('开多') || content.includes('做多')) type = 'buy';
    else if (content.includes('卖出') || content.includes('开空') || content.includes('做空') || content.includes('平仓')) type = 'sell';
    else if (content.includes('交易利润')) type = 'profit';
    else if (content.includes('策略启动') || content.includes('回测结束')) type = 'system';
    else if (content.includes('金叉') || content.includes('死叉')) type = 'signal';

    let pnl = null;
    if (type === 'profit') {
        const match = content.match(/净利\s*([-\d.]+)/);
        if (match) pnl = parseFloat(match[1]);
    }

    return { key: index, date, content, type, pnl };
};

export function calculateMA(dayCount, data) {
  if (!Array.isArray(data)) return [];
  var result = [];
  var sum = 0;
  for (var i = 0, len = data.length; i < len; i++) {
    if (!data[i] || data[i].length < 2) {
        result.push('-');
        continue;
    }
    sum += data[i][1];
    if (i >= dayCount) {
      if (data[i - dayCount] && data[i - dayCount].length >= 2) {
          sum -= data[i - dayCount][1];
      }
      result.push((sum / dayCount).toFixed(2));
    } else {
      result.push((sum / (i + 1)).toFixed(2));
    }
  }
  return result;
}

export const getSymbolName = (symbol) => {
  if (!symbol) return '';
  if (symbolMap[symbol]) return symbolMap[symbol];
  
  // 匹配期货代码 (大写字母开头)
  const match = symbol.match(/^([A-Z]+)/);
  if (match) {
      const code = match[1];
      if (futuresMap[code]) return futuresMap[code];
  }
  
  return symbol;
};

export const getValueColor = (val) => {
    if (val === null || val === undefined || val === '') return 'inherit';
    
    // 移除百分号等非数字字符进行判断
    let numVal = val;
    if (typeof val === 'string') {
        numVal = parseFloat(val.replace(/%/g, ''));
    }
    
    if (isNaN(numVal)) return 'inherit';
    
    // 大于0红色，小于0绿色，等于0默认
    if (numVal > 0) return '#cf1322'; // Red
    if (numVal < 0) return '#3f8600'; // Green
    return 'inherit';
};
