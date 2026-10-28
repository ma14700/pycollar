import React from 'react';
import { Card, Empty, Skeleton } from 'antd';
import ReactECharts from 'echarts-for-react';
import '../styles/analytics.css';

export function AnalysisHero({ icon, eyebrow, title, description, extra }) {
    return <header className="analysis-hero">
        <div className="analysis-heading"><span className="analysis-hero-icon">{icon}</span><div>
            <div className="analysis-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p>
        </div></div><div className="analysis-hero-actions">{extra}</div>
    </header>;
}

export function AnalysisStat({ title, value, detail, icon, color = '#2563eb', loading }) {
    return <Card className="analysis-stat" variant="borderless">
        {loading ? <Skeleton active paragraph={{ rows: 1 }} /> : <>
            <div className="analysis-stat-heading"><span>{title}</span><span className="analysis-stat-icon" style={{ color }}>{icon}</span></div>
            <div className="analysis-stat-value" style={{ color }}>{value}</div><div className="analysis-stat-detail">{detail}</div>
        </>}
    </Card>;
}

export function AnalysisChart({ title, subtitle, option, hasData, height = 280, onEvents, loading, extra }) {
    return <Card variant="borderless" className="analysis-card" title={<div className="analysis-card-title">{title}<small>{subtitle}</small></div>} extra={extra}>
        {loading ? <Skeleton active style={{ height }} /> : hasData
            ? <div role="img" aria-label={title}><ReactECharts option={option} notMerge style={{ height }} onEvents={onEvents} opts={{ renderer: 'svg' }} /></div>
            : <div className="analysis-chart-empty" style={{ minHeight: height }}><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前范围暂无可绘制的数据" /></div>}
    </Card>;
}
