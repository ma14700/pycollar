import React from 'react';
import ReactECharts from 'echarts-for-react';

const ChartPanel = ({ chartType, results, onChartClick }) => {
    if (!results) return null;

    // 提取 key 的逻辑，避免 ReactECharts 内部状态混乱
    const data = results || {};
    const equityCurve = Array.isArray(data.equity_curve) ? data.equity_curve : [];
    const hasEquity = equityCurve.length > 0;
    // 使用 chartType 和 hasEquity 作为 key，确保结构变化时组件重绘
    const chartKey = `${chartType}-${hasEquity ? 'hasEquity' : 'noEquity'}`;

    const getOption = () => {
        // 饼图逻辑
        if (chartType === 'pie') {
            const metrics = results.metrics || {};
            const win = metrics.win_rate || 0;
            const loss = 1 - win;
            return {
                title: { text: '盈亏分布', left: 'center' },
                tooltip: { trigger: 'item' },
                series: [{
                    type: 'pie',
                    radius: '50%',
                    data: [
                        { value: win, name: '盈利交易' },
                        { value: loss, name: '亏损交易' }
                    ]
                }]
            };
        }

        const data = results;
        // 如果是 equity_curve (Line 模式)
        if (chartType === 'line') {
            const equityCurve = Array.isArray(data.equity_curve) ? data.equity_curve : [];
            return {
                title: { text: '账户权益曲线' },
                tooltip: { trigger: 'axis' },
                grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
                xAxis: { 
                    type: 'category', 
                    data: equityCurve.map(item => item ? item.date : '') 
                },
                yAxis: { 
                    type: 'value', 
                    scale: true 
                },
                series: [{
                    name: '权益',
                    data: equityCurve.map(item => item ? item.value : 0),
                    type: 'line',
                    smooth: true,
                    areaStyle: { opacity: 0.3 },
                    itemStyle: { color: '#1890ff' }
                }]
            };
        }

        // Kline 模式
        // 解析后端返回的数据结构
        const klineObj = data.kline_data || {};
        const dates = klineObj.dates || [];
        const klineData = klineObj.values || [];
        
        // 数据完整性检查：如果没有K线数据或日期数据，不渲染复杂图表
        if (!dates.length || !klineData.length) {
            return {
                title: { 
                    text: '暂无数据', 
                    left: 'center',
                    top: 'center',
                    textStyle: { color: '#999' }
                }
            };
        }

        const maData = klineObj.ma || {};
        const dkxData = klineObj.dkx || {};
        // 兼容 signals 或 trades 字段
        const signals = data.signals || data.trades || [];
        const equityCurve = data.equity_curve || [];

        // 构建数据系列
        const seriesList = [];
        const legendData = ['K线', 'DKX', 'MADKX', '资金曲线'];
        if (!maData.strategy_fast) legendData.push('MA20');
        if (!maData.strategy_slow) legendData.push('MA55');
        
        // 预处理有效日期集合，用于过滤不在当前时间范围内的信号
        const validDatesSet = new Set(dates);

        // K线
        seriesList.push({
            name: 'K线',
            type: 'candlestick',
            data: klineData,
            itemStyle: {
                color: '#ef232a',
                color0: '#14b143',
                borderColor: '#ef232a',
                borderColor0: '#14b143'
            },
            markPoint: {
                data: signals
                    .filter(sig => validDatesSet.has(sig.date)) // 过滤掉日期不匹配的信号，防止ECharts断言错误
                    .map(sig => {
                        // 优先使用后端提供的 action (如"反手做多")，若无则回退到基础类型
                        const name = sig.action || (sig.type === 'buy' ? '买入' : '卖出');
                        
                        let valueStr;
                        if (sig.custom_label) {
                            valueStr = sig.custom_label;
                        } else {
                            // 计算显示手数：
                            // 1. 如果是反手操作，成交量(size)通常包含平仓和开仓两部分（例如平20开20，size=40）
                            //    此时用户通常希望看到的是持仓后的净头寸（20手），即 sig.position 的绝对值。
                            // 2. 其他情况（开仓、平仓、加减仓），直接显示成交量 sig.size。
                            let displaySize = Math.abs(sig.size || 0);
                            if (name.includes('反手') && sig.position !== undefined) {
                                displaySize = Math.abs(sig.position);
                            }
                            valueStr = `${name}\n${displaySize}手`;
                        }

                        return {
                            name: name,
                            coord: [sig.date, sig.price],
                            // 显示操作名称和手数
                            value: valueStr,
                            itemStyle: { 
                                color: sig.itemStyle?.color || (sig.type === 'buy' ? '#ef232a' : '#14b143') 
                            },
                            label: {
                                show: true,
                                fontSize: 10,
                                lineHeight: 12
                            }
                        };
                    })
            }
        });

        // 均线
        // 优先展示策略自定义均线
        if (maData.strategy_fast) {
            const name = maData.strategy_fast_label || 'Fast MA';
            legendData.push(name);
            seriesList.push({
                name: name,
                type: 'line',
                data: maData.strategy_fast,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 1.5, color: '#ff7f50' }
            });
        } else if (maData.ma20) {
            // 只有在没有自定义策略均线时才显示默认的 MA20
            seriesList.push({
                name: 'MA20',
                type: 'line',
                data: maData.ma20,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 1, color: '#ff7f50' }
            });
        }

        if (maData.strategy_slow) {
            const name = maData.strategy_slow_label || 'Slow MA';
            legendData.push(name);
            seriesList.push({
                name: name,
                type: 'line',
                data: maData.strategy_slow,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 1.5, color: '#87cefa' }
            });
        } else if (maData.ma55) {
             // 只有在没有自定义策略均线时才显示默认的 MA55
            seriesList.push({
                name: 'MA55',
                type: 'line',
                data: maData.ma55,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 1, color: '#87cefa' }
            });
        }

        // DKX
        if (dkxData.dkx) {
            seriesList.push({
                name: 'DKX',
                type: 'line',
                data: dkxData.dkx,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 2, color: '#722ed1' }
            });
        }
        if (dkxData.madkx) {
            seriesList.push({
                name: 'MADKX',
                type: 'line',
                data: dkxData.madkx,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 2, color: '#fa8c16', type: 'dashed' }
            });
        }

        // 资金曲线 (独立坐标轴)
        const equitySeries = equityCurve.map(item => item ? item.value : 0);
        const showEquity = equitySeries.length > 0;

        if (showEquity) {
            seriesList.push({
                name: '资金曲线',
                type: 'line',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: equitySeries,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 1.5, color: '#1890ff' },
                areaStyle: { opacity: 0.15 }
            });
        }

        const grid = [
            {
                left: '5%',
                right: '5%',
                top: '5%',
                height: showEquity ? '60%' : '85%'
            }
        ];
        
        const xAxis = [
            {
                type: 'category',
                gridIndex: 0,
                data: dates,
                scale: true,
                boundaryGap: false,
                axisLine: { onZero: false },
                splitLine: { show: false },
                min: 'dataMin',
                max: 'dataMax'
            }
        ];

        const yAxis = [
            {
                scale: true,
                gridIndex: 0,
                splitArea: { show: true }
            }
        ];

        if (showEquity) {
            grid.push({
                left: '5%',
                right: '5%',
                top: '70%',
                height: '20%'
            });
            xAxis.push({
                type: 'category',
                gridIndex: 1,
                data: dates,
                axisLabel: { show: false }
            });
            yAxis.push({
                scale: true,
                gridIndex: 1,
                splitNumber: 2,
                axisLabel: { show: true },
                axisLine: { show: false },
                axisTick: { show: false },
                splitLine: { show: false }
            });
        }

        return {
            animation: false,
            title: { text: 'K线图 & 交易信号' },
            legend: {
                data: legendData,
                selected: {
                    'MA20': true,
                    'MA55': true,
                    'DKX': true,
                    'MADKX': true
                }
            },
            grid: grid,
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                },
                formatter: function (params) {
                    if (!params || !params.length) return '';
                    const date = params[0].axisValue;
                    let result = date + '<br/>';
                    
                    params.forEach(param => {
                        const seriesName = param.seriesName;
                        const marker = param.marker;
                        const value = param.value;
                        
                        if (param.seriesType === 'candlestick') {
                            // 防御性编程：处理不同长度的数据格式
                            if (Array.isArray(value)) {
                                let open, close, low, high;
                                // 常见的 ECharts candlestick 格式: [index, open, close, low, high] (长度5)
                                // 或者 [open, close, low, high] (长度4)
                                if (value.length >= 5) {
                                    open = value[1];
                                    close = value[2];
                                    low = value[3];
                                    high = value[4];
                                } else if (value.length === 4) {
                                    open = value[0];
                                    close = value[1];
                                    low = value[2];
                                    high = value[3];
                                }

                                if (open !== undefined) {
                                    result += `${marker} ${seriesName}<br/>
                                               开盘: ${open}<br/>
                                               收盘: ${close}<br/>
                                               最低: ${low}<br/>
                                               最高: ${high}<br/>`;
                                }
                            }
                        } else {
                             let val = value;
                             if (Array.isArray(value) && value.length > 1) val = value[1];
                             if (val === undefined || val === null) val = param.data;
                             
                             if (typeof val === 'number') {
                                 val = val.toFixed(2);
                             } else if (val === null || val === undefined) {
                                 val = '-';
                             }
                             
                             result += `${marker} ${seriesName}: ${val}<br/>`;
                        }
                    });
                    return result;
                }
            },
            xAxis: xAxis,
            yAxis: yAxis,
            dataZoom: [
                {
                    type: 'inside',
                    xAxisIndex: showEquity ? [0, 1] : [0],
                    start: 50,
                    end: 100
                },
                {
                    show: true,
                    xAxisIndex: showEquity ? [0, 1] : [0],
                    type: 'slider',
                    top: '94%',
                    start: 50,
                    end: 100
                }
            ],
            series: seriesList.map(s => ({
                ...s,
                xAxisIndex: s.xAxisIndex || 0,
                yAxisIndex: s.yAxisIndex || 0
            }))
        };
    };

    return (
        <ReactECharts
            key={chartKey}
            option={getOption()}
            style={{ height: '600px', width: '100%' }}
            notMerge={true}
            onEvents={onChartClick ? { click: onChartClick } : undefined}
        />
    );
};

export default ChartPanel;
