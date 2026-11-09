import { getMA144ExitStrategy } from './ma144ExitStrategies.js';
import { tomorrowStrategyOptions } from './tomorrowStrategy.js';
import { strategyNameMap } from '../constants/index.js';

export const strategyOptions = Object.entries({ ...Object.fromEntries(tomorrowStrategyOptions.map(item => [item.value,item.label])), ...strategyNameMap }).map(([value,label]) => ({value,label}));
export const strategyParameterKeys = ['fast_period','slow_period','exit_period','ma_period','macd_fast','macd_slow','macd_signal','dkx_period','dkx_ma_period','atr_period','atr_multiplier','size_mode','risk_per_trade','equity_percent','take_profit_points','stop_loss_points','sl_mode','sl_value','tp_mode','tp_value','ma_type','risk_reward_ratio','allow_reverse','use_expma','exit_on_opposite_cross'];
export const pickStrategyParameters = values => Object.fromEntries(strategyParameterKeys.filter(key => values[key] !== undefined).map(key => [key,values[key]]));
export const isFixedMA144Strategy = name => Boolean(getMA144ExitStrategy(name)) || ['MA20MA144LongOnlyStrategy','MA20MA144ShortOnlyStrategy','MA20MA144LongShortStrategy'].includes(name);
export function defaultStrategyParameters(name) {
    const option = tomorrowStrategyOptions.find(item => item.value === name);
    return { atr_period:14,atr_multiplier:3,risk_per_trade:.02,equity_percent:.1,size_mode:'fixed',
        ...(option?.defaults || {fast_period:20,slow_period:144,exit_period:55}) };
}
export function buildStrategyParameters(strategyType, values) {
    const isMA144SignalStrategy = isFixedMA144Strategy(strategyType);
    const ma144ExitPeriod = getMA144ExitStrategy(strategyType) ? 144 : 55;
    const isDirectionalMA55Strategy = ['MA20MA55LongOnlyStrategy','MA20MA55ShortOnlyStrategy'].includes(strategyType);
      let params = {};
      const riskPerTrade = values.risk_per_trade !== undefined ? parseFloat(values.risk_per_trade) : 0.02;
      const equityPercent = values.equity_percent !== undefined ? parseFloat(values.equity_percent) : 0.1;
      const contractMultiplier = values.contract_multiplier ? parseInt(values.contract_multiplier) : 1;
      const marginRate = values.margin_rate !== undefined ? parseFloat(values.margin_rate) : 0.1;

      // Strategy params construction logic
      if (strategyType === 'MA20MA60DailyMACDStrategy') {
        params = {fast_period:20, slow_period:60, size_mode:'fixed', fixed_size:Number(values.fixed_size || 20),
            contract_multiplier:contractMultiplier, margin_rate:marginRate};
      } else if (strategyType === 'TrendFollowingStrategy') {
        params = {
          fast_period: parseInt(values.fast_period),
          slow_period: parseInt(values.slow_period),
          atr_period: 14,
          atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 2.0,
          risk_per_trade: riskPerTrade,
          equity_percent: equityPercent,
          margin_rate: marginRate,
          contract_multiplier: contractMultiplier,
          use_expma: false,
          size_mode: values.size_mode || 'fixed',
          fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20
        };
      } else if (isMA144SignalStrategy) {
        params = {
          fast_period: 20,
          slow_period: 144,
          exit_period: ma144ExitPeriod,
          size_mode: 'fixed',
          fixed_size: Number(values.fixed_size || 20),
          margin_rate: marginRate,
          contract_multiplier: contractMultiplier,
        };
      } else if (strategyType === 'MA55BreakoutStrategy') {
        params = {
          ma_period: 55,
          macd_fast: 12,
          macd_slow: 26,
          macd_signal: values.macd_signal ? parseInt(values.macd_signal) : 9,
          atr_period: 14,
          atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
          risk_per_trade: riskPerTrade,
          equity_percent: equityPercent,
          margin_rate: marginRate,
          size_mode: values.size_mode || 'fixed',
          fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
          contract_multiplier: contractMultiplier,
          use_trailing_stop: false
        };
      } else if (strategyType === 'MA55TouchExitStrategy') {
        params = {
            ma_period: 55,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier,
            weak_threshold: 7.0
        };
      } else if (strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PointExitStrategy' || isDirectionalMA55Strategy || strategyType === 'StockMA20MA55LongOnlyStrategy' || strategyType === 'MA20MA60CrossoverStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : strategyType === 'MA20MA60CrossoverStrategy' ? 60 : 55,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA20MA55PartialTakeProfitStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier,
            take_profit_points: values.take_profit_points ? parseFloat(values.take_profit_points) : 0
        };
      } else if (strategyType === 'DKXStrategy') {
        params = {
            dkx_period: values.dkx_period ? parseInt(values.dkx_period) : 20,
            dkx_ma_period: values.dkx_ma_period ? parseInt(values.dkx_ma_period) : 10,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'DKXPartialTakeProfitStrategy') {
        params = {
            dkx_period: values.dkx_period ? parseInt(values.dkx_period) : 20,
            dkx_ma_period: values.dkx_ma_period ? parseInt(values.dkx_ma_period) : 10,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier,
            take_profit_points: values.take_profit_points ? parseFloat(values.take_profit_points) : 0
        };
      } else if (strategyType === 'DKXFixedTPSLStrategy') {
        params = {
            dkx_period: values.dkx_period ? parseInt(values.dkx_period) : 20,
            dkx_ma_period: values.dkx_ma_period ? parseInt(values.dkx_ma_period) : 10,
            take_profit_points: values.take_profit_points ? parseFloat(values.take_profit_points) : 100,
            stop_loss_points: values.stop_loss_points ? parseFloat(values.stop_loss_points) : 50,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'DualMAFixedTPSLStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            ma_type: values.ma_type || 'SMA',
            sl_mode: values.sl_mode || 'points',
            sl_value: values.sl_value ? parseFloat(values.sl_value) : 50.0,
            tp_mode: values.tp_mode || 'points',
            tp_value: values.tp_value ? parseFloat(values.tp_value) : 100.0,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA20MA55RiskRewardStrategy' || strategyType === 'MA20MA55RR3Strategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            risk_reward_ratio: Number(values.risk_reward_ratio ?? (strategyType === 'MA20MA55RR3Strategy' ? 3 : 2)),
            atr_period: values.atr_period ? parseInt(values.atr_period) : 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 2.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA5MA20CrossoverStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 5,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 20,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA5MA55CrossoverStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 5,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            allow_reverse: values.allow_reverse !== undefined ? values.allow_reverse : true,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      }

      if (isDirectionalMA55Strategy) params.size_mode = 'fixed';
      if (strategyType === 'MA20MA55RR3Strategy') {
          params.size_mode = 'fixed';
          params.exit_on_opposite_cross = values.exit_on_opposite_cross ?? false;
          for (const [key, fallback] of [['fast_period',20],['slow_period',55],['atr_period',14],['fixed_size',20],['atr_multiplier',2],['risk_reward_ratio',3]]) {
              params[key] = Number(values[key] ?? fallback);
              if (!Number.isFinite(params[key]) || params[key] <= 0 ||
                  (['fast_period','slow_period','atr_period','fixed_size'].includes(key) && !Number.isInteger(params[key]))) {
                  throw new Error('均线、ATR周期和手数必须为正整数，ATR倍数和止盈倍数必须大于0');
              }
          }
          if (params.fast_period >= params.slow_period) throw new Error('快均线周期必须小于慢均线周期');
      }
      if (strategyType === 'MA20MA55PointExitStrategy') {
          params.size_mode = 'fixed';
          for (const [key, fallback, label] of [['take_profit_points',100,'盈利'],['stop_loss_points',50,'亏损']]) {
              params[key] = Number(values[key] ?? fallback);
              if (!Number.isFinite(params[key]) || params[key] <= 0) throw new Error(`${label}平仓点数必须大于0`);
          }
      }
      params.entry_delay_bars = Number(values.entry_delay_bars ?? 0);
      params.exit_delay_bars = Number(values.exit_delay_bars ?? 0);

      params.margin_rate = marginRate;
      return params;
}
