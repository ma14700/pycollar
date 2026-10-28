"""Explicit contracts: five months before delivery through the preceding month's 23rd."""
import datetime
import re
from zoneinfo import ZoneInfo


def contract_window(month):
    if not isinstance(month, str) or not re.fullmatch(r'\d{2}(0[1-9]|1[0-2])', month):
        raise ValueError('合约月份须为四位 YYMM，例如 2605、2701')
    year, delivery_month = 2000 + int(month[:2]), int(month[2:])
    first_month = year * 12 + delivery_month - 1 - 5
    start_year, start_month = divmod(first_month, 12)
    end_year, end_month = divmod(year * 12 + delivery_month - 1 - 1, 12)
    return {
        'contract_month': month,
        'start_date': datetime.date(start_year, start_month + 1, 1).isoformat(),
        'end_date': datetime.date(end_year, end_month + 1, 23).isoformat(),
    }


def contract_scope(symbol, month, market_type='futures', data_provider='tqsdk', data_source='main'):
    if market_type != 'futures':
        raise ValueError('具体合约回测仅适用于期货')
    if data_provider != 'tqsdk' or data_source != 'main':
        raise ValueError('具体合约回测须使用天勤行情和具体合约口径')
    window = contract_window(month)
    match = re.fullmatch(r'([A-Za-z]+)(0|\d{4})', symbol)
    if not match or match[2] not in ('0', month):
        raise ValueError('交易品种与所选合约月份不一致，请重新选择合约')
    return {'symbol': f'{match[1].upper()}{month}', **window}


def contract_choices(base_symbol, instruments, now=None):
    match = re.fullmatch(r'([A-Za-z]+)0', base_symbol)
    if not match:
        raise ValueError('请选择一个期货交易品种后查询合约')
    product = match[1].upper()
    year = (now or datetime.datetime.now(ZoneInfo('Asia/Shanghai'))).year
    choices = {}
    for instrument in instruments:
        match = re.fullmatch(r'([A-Z]+)\.([A-Za-z]+)(\d{3,4})', instrument)
        if not match or match[2].upper() != product:
            continue
        suffix = match[3]
        if len(suffix) == 3:  # CZCE uses a one-digit delivery year.
            delivery_year = year // 10 * 10 + int(suffix[0])
            if delivery_year > year + 5:
                delivery_year -= 10
            elif delivery_year < year - 4:
                delivery_year += 10
            suffix = f'{delivery_year % 100:02d}{suffix[1:]}'
        try:
            window = contract_window(suffix)
        except ValueError:
            continue
        delivery_year = 2000 + int(suffix[:2])
        if not year - 2 <= delivery_year <= year + 3:
            continue
        choices[suffix] = {
            'value': suffix, 'symbol': f'{product}{suffix}', 'resolved_symbol': instrument,
            'label': f'{product}{suffix}（{delivery_year}年{int(suffix[2:])}月）', **window,
        }
    return [choices[month] for month in sorted(choices, reverse=True)]
