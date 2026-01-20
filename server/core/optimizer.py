import random
import copy
from .engine import BacktestEngine

class StrategyOptimizer:
    def __init__(self):
        self.engine = BacktestEngine()
        
    def optimize(self, symbol, period, initial_params, target_return=20.0, max_trials=10, start_date=None, end_date=None, strategy_name='TrendFollowingStrategy'):
        """
        简单的随机搜索优化器
        :param symbol: 交易品种
        :param period: K线周期
        :param initial_params: 初始参数字典
        :param target_return: 目标收益率 (%)
        :param max_trials: 最大尝试次数
        :param start_date: 开始时间
        :param end_date: 结束时间
        :param strategy_name: 策略名称
        :return: (best_params, best_result)
        """
        best_result = None
        best_return = -float('inf')
        best_params = initial_params.copy()
        
        # 定义参数搜索空间
        param_ranges = {}
        
        if strategy_name == 'TrendFollowingStrategy':
            param_ranges = {
                'fast_period': list(range(5, 30, 2)),
                'slow_period': list(range(20, 100, 5)),
                'atr_period': [10, 14, 20, 30],
                'atr_multiplier': [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
                'risk_per_trade': [0.01, 0.02, 0.03, 0.05]
            }
        elif strategy_name == 'MA55BreakoutStrategy':
             param_ranges = {
                'ma_period': [20, 34, 55, 89, 144],
                'macd_fast': [10, 12, 15],
                'macd_slow': [20, 26, 30],
                'macd_signal': [7, 9, 12],
                'atr_period': [14, 20],
                'atr_multiplier': [1.5, 2.0, 2.5, 3.0],
            }
             # 根据开仓模式调整优化参数
             if initial_params.get('size_mode') == 'fixed':
                 param_ranges['fixed_size'] = [1, 2, 3, 5]
             else:
                 param_ranges['risk_per_trade'] = [0.01, 0.02, 0.03, 0.05]
        
        print(f"开始自动优化... 策略: {strategy_name}, 目标收益率: >{target_return}%, 最大尝试: {max_trials}次")
        
        for i in range(max_trials):
            # 生成新参数
            trial_params = initial_params.copy()
            
            # 随机变异 1-3 个参数
            if param_ranges:
                num_mutations = random.randint(1, min(3, len(param_ranges)))
                keys_to_mutate = random.sample(list(param_ranges.keys()), num_mutations)
                
                for key in keys_to_mutate:
                    if key in param_ranges:
                        trial_params[key] = random.choice(param_ranges[key])
            
            # 特定策略的约束检查
            if strategy_name == 'TrendFollowingStrategy':
                # 确保 fast < slow
                if 'fast_period' in trial_params and 'slow_period' in trial_params:
                    if trial_params['fast_period'] >= trial_params['slow_period']:
                        trial_params['slow_period'] = trial_params['fast_period'] + 5
            elif strategy_name == 'MA55BreakoutStrategy':
                # 确保 macd_fast < macd_slow
                if 'macd_fast' in trial_params and 'macd_slow' in trial_params:
                     if trial_params['macd_fast'] >= trial_params['macd_slow']:
                         trial_params['macd_slow'] = trial_params['macd_fast'] + 5

            print(f"优化尝试 #{i+1}: {trial_params}")
            
            # 运行回测
            result = self.engine.run(symbol, period, trial_params, start_date=start_date, end_date=end_date, strategy_name=strategy_name)
            
            if "error" in result:
                continue
                
            # 计算收益率
            final_value = result['metrics']['final_value']
            initial_cash = result['metrics']['initial_cash']
            net_profit = final_value - initial_cash
            return_rate = (net_profit / initial_cash) * 100
            
            print(f"  -> 收益率: {return_rate:.2f}%")
            
            # 更新最佳结果
            if return_rate > best_return:
                best_return = return_rate
                best_result = result
                best_params = trial_params
            
            # 检查是否达到目标
            if best_return > target_return:
                print(f"  -> 达到目标收益率! 停止优化。")
                break
                
        return best_params, best_result
