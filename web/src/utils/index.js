import { symbolMap, futuresMap } from '../constants';

export { parseLogItem } from './logParser.js';

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
