import React from 'react';
import { Alert, Col, Form, Input, Radio, Row, Select, Switch, Tooltip } from 'antd';
import { SafetyCertificateOutlined } from '@ant-design/icons';
import RiskRewardInputs from '../../components/RiskRewardInputs';
import PointExitInputs from '../../components/PointExitInputs';
import { strategyOptions, isFixedMA144Strategy, isMA55144Strategy } from '../../utils/backtestStrategies';
import { getMA144ExitStrategy } from '../../utils/ma144ExitStrategies';

const { Option } = Select;

const DUAL_MA_STRATEGIES = new Set([
  'TrendFollowingStrategy',
  'MA20MA55CrossoverStrategy',
  'MA20MA55PartialTakeProfitStrategy',
  'StockMA20MA55LongOnlyStrategy',
  'DualMAFixedTPSLStrategy',
  'MA20MA55RiskRewardStrategy',
  'MA20MA55RR3Strategy',
  'MA20MA55PointExitStrategy',
  'MA20MA55LongOnlyStrategy',
  'MA20MA55ShortOnlyStrategy',
  'MA55MA144CrossoverStrategy',
  'MA55MA144LongOnlyStrategy',
  'MA55MA144ShortOnlyStrategy',
  'MA5MA20CrossoverStrategy',
  'MA5MA55CrossoverStrategy',
  'MA20MA60CrossoverStrategy',
]);

const DKX_STRATEGIES = new Set([
  'DKXStrategy',
  'DKXPartialTakeProfitStrategy',
  'DKXFixedTPSLStrategy',
]);

const FLEXIBLE_SIZE_STRATEGIES = new Set([
  'MA55BreakoutStrategy',
  'MA55TouchExitStrategy',
  'MA20MA55CrossoverStrategy',
  'MA20MA55PartialTakeProfitStrategy',
  'DKXStrategy',
  'DKXPartialTakeProfitStrategy',
  'DKXFixedTPSLStrategy',
  'StockMA20MA55LongOnlyStrategy',
  'DualMAFixedTPSLStrategy',
  'MA20MA55RiskRewardStrategy',
  'MA5MA20CrossoverStrategy',
  'MA5MA55CrossoverStrategy',
  'MA20MA60CrossoverStrategy',
]);

const OPTIMIZABLE_STRATEGIES = new Set([
  'TrendFollowingStrategy',
  'MA55BreakoutStrategy',
  'DKXStrategy',
  'DKXPartialTakeProfitStrategy',
  'DKXFixedTPSLStrategy',
]);

export default function StrategyConfigFields({
  strategyType,
  selectedStrategies,
  setSelectedStrategies,
  activateStrategy,
  loading,
  autoOptimize,
  setAutoOptimize,
  children,
}) {
  const ma144ExitStrategy = getMA144ExitStrategy(strategyType);
  const isMA144ReversalStrategy = Boolean(ma144ExitStrategy?.reverses);
  const ma144ExitPeriod = ma144ExitStrategy ? 144 : 55;
  const isMA144SignalStrategy = isFixedMA144Strategy(strategyType);
  const isShortMA144Strategy = ['MA20MA144ShortOnlyStrategy', 'MA20MA144CrossExitShortOnlyStrategy'].includes(strategyType);
  const isLongShortMA144Strategy = ['MA20MA144LongShortStrategy', 'MA20MA144CrossExitLongShortStrategy'].includes(strategyType);
  const isDirectionalMA55Strategy = [
    'MA20MA55LongOnlyStrategy',
    'MA20MA55ShortOnlyStrategy',
    'MA55MA144LongOnlyStrategy',
    'MA55MA144ShortOnlyStrategy',
  ].includes(strategyType);
  const isPointExitStrategy = strategyType === 'MA20MA55PointExitStrategy';
  const isRR3Strategy = strategyType === 'MA20MA55RR3Strategy';
  const isDailyMACDStrategy = strategyType === 'MA20MA60DailyMACDStrategy';
  const isDKXStrategy = DKX_STRATEGIES.has(strategyType);
  const isFixedSizeOnly =
    isRR3Strategy ||
    isMA144SignalStrategy ||
    isDirectionalMA55Strategy ||
    isPointExitStrategy ||
    isDailyMACDStrategy ||
    isMA55144Strategy(strategyType);

  return (
    <>
      <Form.Item label="选择策略（可多选）" required>
        <Select
          id="strategy_selection"
          mode="multiple"
          showSearch
          optionFilterProp="label"
          value={selectedStrategies}
          options={strategyOptions}
          disabled={loading}
          placeholder="至少选择一个策略"
          onChange={names => {
            const added = names.find(name => !selectedStrategies.includes(name));
            setSelectedStrategies(names);
            if (added) activateStrategy(added);
            else if (names.length && !names.includes(strategyType)) activateStrategy(names[0]);
          }}
        />
      </Form.Item>
      {selectedStrategies.length > 1 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`已选 ${selectedStrategies.length} 个策略，将与所选品种或合约逐一组合回测`}
          description="品种、日期、资金、固定手数及开平仓 K 线共用；切换下方策略可分别配置参数。"
        />
      )}
      <Form.Item label="当前策略参数">
        <Select
          id="strategy_editor"
          value={strategyType}
          disabled={loading || !selectedStrategies.length}
          options={strategyOptions.filter(item => selectedStrategies.includes(item.value))}
          onChange={activateStrategy}
        />
      </Form.Item>

      {isPointExitStrategy && (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="金叉做多、死叉做空并反手；触及盈利或亏损点数时全仓平仓"
            description="点数从实际开仓成交价计算，多空对称；止盈止损平仓后等待新的均线交叉。同根K线同时触及两者时按止损优先模拟。"
          />
          <PointExitInputs />
        </>
      )}
      {isDailyMACDStrategy && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="当前周期20/60交叉＋日线MACD过滤"
          description="均线按所选周期计算：例如60分钟周期使用20根与60根小时K线均线。上穿且已完成日线MACD的DIF>DEA时做多，下穿且DIF<DEA时做空；MACD独立取同合约日线，采用12/26/9，只使用信号确认时已完成的日线；判断金叉或死叉状态，不要求MACD在同一天交叉，也不要求在零轴上方或下方。反向均线交叉先离场，仅MACD同向才反手；未通过过滤的信号不会补开，等待新的均线交叉。收盘确认，按开平仓K线配置执行。"
        />
      )}
      {isDirectionalMA55Strategy && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={['MA20MA55LongOnlyStrategy', 'MA55MA144LongOnlyStrategy'].includes(strategyType) ? '金叉开多，死叉平多；不做空' : '死叉开空，金叉平空；不做多'}
          description={`使用固定手数，不加仓、不反手；离场后等待同方向的新交叉信号。默认 ${isMA55144Strategy(strategyType) ? 'MA55 / MA144' : 'MA20 / MA55'}，按开仓和平仓 K 线设置执行。`}
        />
      )}
      {strategyType === 'MA55MA144CrossoverStrategy' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="MA55 上穿 MA144 做多，下穿做空，持仓时反向交叉反手"
          description="默认使用 MA55 / MA144；信号在收盘确认，成交按开平仓 K 线设置执行。"
        />
      )}
      {isMA144SignalStrategy && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={
            isMA144ReversalStrategy
              ? 'MA20 / MA144 金叉平空开多，死叉平多开空（反手）'
              : isLongShortMA144Strategy
                ? `MA20 / MA144 金叉做多、死叉做空；MA20 / MA${ma144ExitPeriod} 反向交叉离场`
                : isShortMA144Strategy
                  ? `MA20 / MA144 死叉开空，MA20 / MA${ma144ExitPeriod} 金叉离场`
                  : `MA20 / MA144 金叉开多，MA20 / MA${ma144ExitPeriod} 死叉离场`
          }
          description={`${
            isMA144ReversalStrategy
              ? '空仓时金叉开多、死叉开空；持有多单遇死叉时平多并开空，持有空单遇金叉时平空并开多。反手后保持设定的固定手数，不加仓；反手订单按开仓、平仓 K 线设置的较大值等待成交。'
              : isLongShortMA144Strategy
                ? `空仓时金叉开多、死叉开空；多单在 MA20 下穿 MA${ma144ExitPeriod} 时离场，空单在 MA20 上穿 MA${ma144ExitPeriod} 时离场。不加仓，持仓期间只按离场规则处理，不直接反手；平仓成交后等待新的 MA20/144 交叉。`
                : isShortMA144Strategy
                  ? '仅做空，不加仓；离场后等待下一次 MA20 下穿 MA144。'
                  : '仅做多，不加仓；离场后等待下一次 MA20 上穿 MA144。'
          }均线按所选 K 线周期计算，日线下为 ${ma144ExitStrategy ? '20 / 144' : '20 / 55 / 144'} 日均线。信号收盘确认，按开仓 / 平仓 K 线设置等待成交，回测末尾沿用平台平仓规则。`}
        />
      )}

      {children}

      {isMA144SignalStrategy || isDailyMACDStrategy ? null : DUAL_MA_STRATEGIES.has(strategyType) ? (
        <>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="fast_period" label="快线周期">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="slow_period" label="慢线周期">
                <Input type="number" />
              </Form.Item>
            </Col>
          </Row>
          {strategyType === 'MA5MA55CrossoverStrategy' && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="allow_reverse" label="允许反手" valuePropName="checked" tooltip="开启后：金叉平空开多，死叉平多开空；关闭后：仅平仓不反手">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
          )}
          {strategyType === 'MA20MA55PartialTakeProfitStrategy' && (
            <Form.Item name="take_profit_points" label="盈利平半仓点数" tooltip="当浮动盈利达到此点数时，平掉一半仓位">
              <Input type="number" />
            </Form.Item>
          )}
          {(isRR3Strategy || strategyType === 'MA20MA55RiskRewardStrategy') && <RiskRewardInputs isRR3Strategy={isRR3Strategy} />}
          {strategyType === 'DualMAFixedTPSLStrategy' && (
            <>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="ma_type" label="均线类型">
                    <Select>
                      <Option value="SMA">简单均线 (SMA)</Option>
                      <Option value="EMA">指数均线 (EMA)</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="tp_mode" label="止盈模式">
                    <Select>
                      <Option value="points">固定点数</Option>
                      <Option value="percent">百分比 (%)</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="tp_value" label="止盈数值">
                    <Input type="number" step="0.1" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="sl_mode" label="止损模式">
                    <Select>
                      <Option value="points">固定点数</Option>
                      <Option value="percent">百分比 (%)</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="sl_value" label="止损数值">
                    <Input type="number" step="0.1" />
                  </Form.Item>
                </Col>
              </Row>
            </>
          )}
        </>
      ) : isDKXStrategy ? (
        <>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="dkx_period" label="DKX周期" tooltip="通常为20">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="dkx_ma_period" label="MADKX周期" tooltip="通常为10">
                <Input type="number" />
              </Form.Item>
            </Col>
          </Row>
          {strategyType === 'DKXPartialTakeProfitStrategy' && (
            <Form.Item name="take_profit_points" label="盈利平半仓点数" tooltip="当浮动盈利达到此点数时，平掉一半仓位">
              <Input type="number" />
            </Form.Item>
          )}
          {strategyType === 'DKXFixedTPSLStrategy' && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="take_profit_points" label="止盈点数">
                  <Input type="number" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="stop_loss_points" label="止损点数">
                  <Input type="number" />
                </Form.Item>
              </Col>
            </Row>
          )}
        </>
      ) : (
        <>
          <Form.Item name="ma_period" label="突破均线周期">
            <Input type="number" />
          </Form.Item>
          {strategyType === 'MA55BreakoutStrategy' && (
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="macd_fast" label="MACD快">
                  <Input type="number" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="macd_slow" label="MACD慢">
                  <Input type="number" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="macd_signal" label="MACD信">
                  <Input type="number" />
                </Form.Item>
              </Col>
            </Row>
          )}
        </>
      )}

      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) => prevValues.size_mode !== currentValues.size_mode}
      >
        {({ getFieldValue }) => {
          const sizeMode = getFieldValue('size_mode');
          if (
            (strategyType === 'TrendFollowingStrategy' || !sizeMode || sizeMode === 'atr_risk') &&
            !isRR3Strategy &&
            strategyType !== 'MA20MA55RiskRewardStrategy' &&
            !isMA144SignalStrategy &&
            !isDirectionalMA55Strategy &&
            !isDailyMACDStrategy &&
            !isMA55144Strategy(strategyType)
          ) {
            return (
              <Form.Item name="atr_multiplier" label="ATR止损倍数">
                <Input type="number" step="0.1" />
              </Form.Item>
            );
          }
          return null;
        }}
      </Form.Item>

      {isFixedSizeOnly ? (
        <Form.Item
          name="fixed_size"
          label="固定手数 (手)"
          initialValue={20}
          rules={[
            { required: true, message: '请输入固定手数' },
            {
              validator: (_, value) =>
                Number.isInteger(Number(value)) && Number(value) > 0
                  ? Promise.resolve()
                  : Promise.reject(new Error('固定手数须为正整数')),
            },
          ]}
        >
          <Input type="number" min={1} step={1} />
        </Form.Item>
      ) : FLEXIBLE_SIZE_STRATEGIES.has(strategyType) ? (
        <>
          <Form.Item name="size_mode" label="开仓模式" initialValue="fixed">
            <Radio.Group>
              <Radio value="fixed">固定手数</Radio>
              <Radio value="equity_percent">固定资金比例</Radio>
              <Radio value="atr_risk">ATR风险</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.size_mode !== currentValues.size_mode}
          >
            {({ getFieldValue }) => {
              const mode = getFieldValue('size_mode');
              if (mode === 'fixed') {
                return (
                  <Form.Item name="fixed_size" label="固定手数 (手)" initialValue={20}>
                    <Input type="number" />
                  </Form.Item>
                );
              }
              if (mode === 'equity_percent') {
                return (
                  <Form.Item name="equity_percent" label="资金比例 (0.1=10%)" initialValue={0.1}>
                    <Input type="number" step="0.1" max="1.0" min="0.01" />
                  </Form.Item>
                );
              }
              return (
                <Form.Item name="risk_per_trade" label="单笔风险系数 (0.02=2%)" initialValue={0.02}>
                  <Input type="number" step="0.01" />
                </Form.Item>
              );
            }}
          </Form.Item>
        </>
      ) : (
        <Form.Item name="risk_per_trade" label="单笔风险系数 (0.02=2%)">
          <Input type="number" step="0.01" />
        </Form.Item>
      )}

      <Form.Item name="margin_rate" label="保证金率 (0.1=10%)" initialValue={0.12}>
        <Input type="number" step="0.01" max={1} min={0.01} />
      </Form.Item>

      <Form.Item name="optimal_entry" label="开仓最优模式" valuePropName="checked" initialValue={false}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Switch />
          <Tooltip title="开启后，所有开仓、平仓、反手操作均以当前策略所选K线的中间点位 [(High+Low)/2] 作为执行价格（开启CheatOnOpen模式以确保成交）。">
            <span style={{ marginLeft: 8, fontSize: '12px', color: '#888', cursor: 'pointer' }}>
              <SafetyCertificateOutlined style={{ marginRight: 4 }} />
              说明
            </span>
          </Tooltip>
        </div>
      </Form.Item>

      <Form.Item name="contract_multiplier" label="合约乘数" hidden>
        <Input type="number" />
      </Form.Item>
      {!isRR3Strategy && strategyType !== 'MA20MA55RiskRewardStrategy' && <Form.Item name="atr_period" hidden><Input /></Form.Item>}

      <Form.Item label="自动优化 (若收益<20%)" tooltip="当区间总收益率低于20%时，对支持的策略尝试参数搜索，仅展示优于原参数的结果。同一区间筛选不代表未来收益。">
        <Switch checked={autoOptimize} onChange={setAutoOptimize} disabled={!OPTIMIZABLE_STRATEGIES.has(strategyType)} />
      </Form.Item>
    </>
  );
}
