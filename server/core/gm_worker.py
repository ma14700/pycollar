"""Run the official GM SDK in its isolated Python environment."""
import contextlib
import io
import json
import sys
import datetime


def collect(request):
    from gm.api import history, history_n, set_token
    set_token(request['token'])
    fields = 'symbol,open,high,low,close,volume,position,bob,eob'
    if request['action'] == 'quote':
        frame = history_n(symbol=request['symbol'], frequency='1d', count=5, fields=fields, df=True)
        return {'rows': json.loads(frame.to_json(orient='records', date_format='iso'))}
    start = datetime.datetime.fromisoformat(request['start'])
    end = datetime.datetime.fromisoformat(request['end'])
    frequency = request['frequency']
    days = 15 if frequency == '60s' else 60 if frequency == '300s' else 180 if frequency.endswith('s') else 730
    rows = []
    while start < end:
        next_end = min(start + datetime.timedelta(days=days), end)
        frame = history(symbol=request['symbol'], frequency=frequency,
                        start_time=start.strftime('%Y-%m-%d %H:%M:%S'),
                        end_time=next_end.strftime('%Y-%m-%d %H:%M:%S'), fields=fields, df=True)
        if len(frame) >= 33000:
            raise ValueError('单次行情达到平台数据上限，请缩短时间范围')
        rows.extend(json.loads(frame.to_json(orient='records', date_format='iso')))
        start = next_end
    return {'rows': rows}


if __name__ == '__main__':
    request = json.loads(sys.stdin.read())
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            response = collect(request)
    except Exception as error:
        message = str(error).replace(request.get('token', ''), '[redacted]')
        try:
            parsed = json.loads(message)
            code, detail = parsed.get('status'), parsed.get('message', '')
        except (ValueError, TypeError):
            code, detail = None, ''
        if code == 1001:
            message = '无法连接掘金终端服务，请启动并登录掘金量化终端后重试'
        elif code == 2002:
            message = '掘金数据权限不足：' + detail[:350]
        elif code == 1026:
            message = '掘金终端更新令牌失败，请检查终端登录状态后重试'
        elif isinstance(error, ValueError) and '数据上限' in message:
            pass
        else:
            message = f'掘金行情请求失败（错误代码 {code}），请检查终端、合约和数据权限' if code else '掘金行情请求失败，请检查终端和数据权限'
        response = {'error': message}
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
