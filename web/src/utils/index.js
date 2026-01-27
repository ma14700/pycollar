import { symbolMap, futuresMap } from '../constants';

export const parseLogItem = (log, index) => {
    const logStr = String(log || '');
    const firstComma = logStr.indexOf(',');
    const date = firstComma !== -1 ? logStr.substring(0, firstComma).trim() : '';
    const content = firstComma !== -1 ? logStr.substring(firstComma + 1).trim() : logStr;
    
    let type = 'info';
    if (content.includes('买入') || content.includes('开多') || content.includes('做多')) type = 'buy';
    else if (content.includes('卖出') || content.includes('开空') || content.includes('做空')) type = 'sell';
    else if (content.includes('平仓') || content.includes('平多') || content.includes('平空')) type = 'profit'; // Use 'profit' color for closing
    else if (content.includes('策略启动') || content.includes('回测结束')) type = 'system';
    else if (content.includes('金叉') || content.includes('死叉')) type = 'signal';

    // Extract structured data from standardized log format
    // Format: 交易执行: 【{action}】 价格: {price}, 数量: {size}, 费用: {comm}, 当前持仓: {pos}, 持仓成本: {cost}, 方向: {dir}, 期间最大回撤: {mdd}, 净利润: {pnl}
    
    let action = '';
    const actionMatch = content.match(/【(.*?)】/);
    if (actionMatch) action = actionMatch[1];
    
    const extractNum = (key) => {
        const regex = new RegExp(`${key}:\\s*([-\\d.]+)`);
        const match = content.match(regex);
        return match ? parseFloat(match[1]) : null;
    };
    
    const price = extractNum('价格');
    const size = extractNum('数量');
    const comm = extractNum('费用');
    const pos = extractNum('当前持仓');
    const cost = extractNum('持仓成本');
    const mdd = extractNum('期间最大回撤');
    const pnl = extractNum('净利润');
    const pct = extractNum('收益率'); // Extract percentage
    
    let dir = '';
    const dirMatch = content.match(/方向:\s*([^,]+)/); // 方向 usually followed by comma or end
    if (dirMatch) {
        // Handle cases where "方向" is the last item or followed by MDD/PnL
        // The regex `[^,]+` matches until comma. If "方向: 做多 期间最大回撤...", we need to stop before next keyword
        // Actually my backend uses ", " separator.
        dir = dirMatch[1].trim();
        // Clean up if it grabbed too much (e.g. if next field didn't have comma before it, though my backend puts commas)
    }

    return { 
        key: index, 
        date, 
        content, 
        type, 
        action, 
        price, 
        size, 
        comm, 
        pos, 
        cost, 
        dir, 
        mdd, 
        pnl,
        pct
    };
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
