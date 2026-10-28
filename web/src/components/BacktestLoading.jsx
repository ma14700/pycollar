import React, { useEffect, useId, useState } from 'react';
import { ClockCircleOutlined, LineChartOutlined, LoadingOutlined } from '@ant-design/icons';
import { strategyNameMap } from '../constants';
import './BacktestLoading.css';

const strategyLabels = {
    ...strategyNameMap,
    MA20MA60CrossoverStrategy: '20/60 双均线交叉',
    MA5MA20CrossoverStrategy: '5/20 双均线交叉',
    MA5MA55CrossoverStrategy: '5/55 均线多空交叉',
    DualMAFixedTPSLStrategy: '双均线 · 固定止盈止损',
    MA20MA55RiskRewardStrategy: '双均线 · 盈亏比策略',
};

const candles = [66, 58, 63, 42, 49, 39, 50, 55, 44, 57, 39, 28, 37, 32, 20, 29,
    38, 31, 22, 35, 28, 15, 25, 18, 29, 22, 13, 19, 10, 17, 22, 12];

function formatElapsed(seconds) {
    const minutes = Math.floor(seconds / 60);
    return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

const BacktestLoading = ({ run }) => {
    const [elapsed, setElapsed] = useState(0);
    const gradientId = useId().replace(/:/g, '');
    useEffect(() => {
        const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - run.startedAt) / 1000)));
        update();
        const timer = window.setInterval(update, 1000);
        return () => window.clearInterval(timer);
    }, [run.startedAt]);

    const batch = run.total > 1;
    const unit = run.unit || '品种';
    const percent = run.total ? Math.round(run.completed / run.total * 100) : 0;
    const period = run.period === 'daily' ? '日线' : run.period === 'weekly' ? '周线' : `${run.period} 分钟`;
    const provider = run.provider === 'tqsdk' ? '天勤行情' : '原有行情';
    const strategy = strategyLabels[run.strategy] || run.strategy;

    return <section className="backtest-wait" aria-busy="true" aria-label="策略回测执行中">
        <header className="backtest-wait-header">
            <span className="backtest-wait-status" role="status" aria-live="polite">
                <span className="backtest-wait-dot" />{batch ? '批量回测进行中' : '策略回测进行中'}
            </span>
            <span className="backtest-wait-clock" aria-live="off"><ClockCircleOutlined /> 已用时 <b>{formatElapsed(elapsed)}</b></span>
        </header>

        <div className="backtest-wait-intro">
            <div className="backtest-wait-icon"><LineChartOutlined /></div>
            <div>
                <h2>正在回测你的策略<span className="backtest-wait-dots" aria-hidden="true"><i /><i /><i /></span></h2>
                <p>{elapsed >= 30 ? '行情读取或策略计算需要一些时间，请保持页面打开。' : '正在获取历史行情并执行策略，完成后将自动展示结果。'}</p>
            </div>
        </div>

        <div className="backtest-wait-context">
            <div><span>当前品种</span><strong>{run.symbol || '准备中'}{run.symbolName && <small>{run.symbolName}</small>}</strong></div>
            <div><span>本次策略</span><strong title={strategy}>{strategy}</strong></div>
            <div><span>行情设置</span><strong>{period}<small>{provider}</small></strong></div>
        </div>

        <div className="backtest-wait-chart" aria-hidden="true">
            <div className="backtest-wait-chart-title"><span><span className="backtest-wait-chart-dot" /> 回测结果生成中</span><span className="backtest-wait-live"><LoadingOutlined spin /> 处理中</span></div>
            <svg viewBox="0 0 720 190" preserveAspectRatio="none">
                <defs>
                    <linearGradient id={`${gradientId}-area`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3c7ef7" stopOpacity=".15" /><stop offset="100%" stopColor="#3c7ef7" stopOpacity="0" /></linearGradient>
                    <linearGradient id={`${gradientId}-scan`} x1="0" y1="0" x2="1" y2="0"><stop stopColor="#90b5ff" stopOpacity="0" /><stop offset="100%" stopColor="#90b5ff" stopOpacity=".18" /></linearGradient>
                </defs>
                {[36, 77, 118, 159].map(y => <line key={y} x1="0" y1={y} x2="720" y2={y} stroke="#e9eff8" strokeDasharray="4 5" />)}
                <path d="M0,146 C35,146 42,120 72,126 S117,153 150,121 S192,129 221,102 S261,121 294,88 S331,107 366,76 S407,96 438,62 S480,83 512,47 S553,68 585,37 S628,60 659,25 S695,37 720,17 L720,190 L0,190 Z" fill={`url(#${gradientId}-area)`} />
                <path d="M0,146 C35,146 42,120 72,126 S117,153 150,121 S192,129 221,102 S261,121 294,88 S331,107 366,76 S407,96 438,62 S480,83 512,47 S553,68 585,37 S628,60 659,25 S695,37 720,17" fill="none" stroke="#b4cdf8" strokeWidth="2" />
                {candles.map((value, index) => {
                    const x = 12 + index * 22;
                    const y = value * 1.65 + 16;
                    const height = 10 + index % 4 * 5;
                    const color = index % 3 === 0 ? '#7cb5b0' : '#8aaff1';
                    return <g key={index} opacity=".65"><line x1={x + 4} y1={y - 9} x2={x + 4} y2={y + height + 10} stroke={color} /><rect x={x} y={y} width="8" height={height} rx="2" fill={color} /></g>;
                })}
                <g className="backtest-wait-scan"><rect x="-100" width="100" height="190" fill={`url(#${gradientId}-scan)`} /><line x1="0" y1="0" x2="0" y2="190" stroke="#80aaf7" strokeOpacity=".7" /></g>
            </svg>
            <div className="backtest-wait-chart-axis"><span>历史行情</span><span>策略信号</span><span>回测结果</span></div>
        </div>

        <div className="backtest-wait-metrics" aria-hidden="true">
            {['收益表现', '风险指标', '交易统计'].map((label, index) => <div key={label}><span>{label}</span><div className={`backtest-wait-skeleton backtest-wait-skeleton-${index}`} /><div className="backtest-wait-skeleton backtest-wait-skeleton-sub" /></div>)}
        </div>

        <footer className="backtest-wait-footer">
            <div className="backtest-wait-progress-caption">
                <span>{batch ? `已处理 ${run.completed} / ${run.total} 个${unit}` : '行情读取与策略计算中'}</span>
                <span>{batch ? `${percent}%` : '请稍候'}</span>
            </div>
            <div className={`backtest-wait-progress ${batch ? '' : 'backtest-wait-progress-indeterminate'}`}
                role="progressbar" aria-label="回测进度" aria-valuemin={batch ? 0 : undefined}
                aria-valuemax={batch ? run.total : undefined} aria-valuenow={batch ? run.completed : undefined}>
                <span style={batch ? { width: `${percent}%` } : undefined} />
            </div>
            <div className="backtest-wait-note">{batch ? `正在处理第 ${Math.min(run.completed + 1, run.total)} 个${unit}${run.failed ? ` · ${run.failed} 个失败` : ''}` : '计算完成后，收益曲线、风险指标和交易明细将在这里呈现。'}</div>
        </footer>
    </section>;
};

export default BacktestLoading;
