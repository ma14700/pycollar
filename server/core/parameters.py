"""Validate strategy inputs separately from broker execution options."""
import math


def boolean_option(value, label):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    raise ValueError(f'{label} 必须为 true 或 false')


def execution_options(params):
    return {'optimal_entry': boolean_option(params.get('optimal_entry', False), 'optimal_entry')}


def filter_strategy_params(strategy_class, params):
    valid = {}
    for key, value in params.items():
        if key == 'optimal_entry' or not hasattr(strategy_class.params, key):
            continue
        if value is None or value == '':
            continue
        default = getattr(strategy_class.params, key)
        if isinstance(default, bool):
            value = boolean_option(value, key)
        elif isinstance(default, (int, float)):
            if isinstance(value, bool):
                raise ValueError(f'策略参数 {key} 数值无效')
            number = float(value)
            if not math.isfinite(number) or (isinstance(default, int) and not number.is_integer()):
                raise ValueError(f'策略参数 {key} 数值无效')
            value = int(number) if isinstance(default, int) else number
            if (key.endswith('_period') or key in ('fixed_size', 'contract_multiplier', 'atr_multiplier')) and value <= 0:
                raise ValueError(f'策略参数 {key} 必须大于 0')
        valid[key] = value
    validator = getattr(strategy_class, 'validate_params', None)
    if callable(validator):
        validator(valid)
    return valid
