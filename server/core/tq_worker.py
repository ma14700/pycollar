"""Isolated SDK event loop with a parent-enforced connection timeout."""
import contextlib
import io
import json
import math
import sys
import time
import pandas as pd

from .tq_provider import credentials, PERIODS, SERIES_LENGTH


def collect(request):
    from tqsdk import TqApi, TqAuth
    user, password = credentials()
    api = None
    try:
        api = TqApi(auth=TqAuth(user, password), disable_print=True)
        deadline = time.time() + 30
        if request['action'] == 'contracts':
            return {'contracts': list(api.query_quotes(ins_class='FUTURE',
                exchange_id=request['exchange'], product_id=request['product'], expired=None))}
        if request['action'] == 'contract_quote':
            serial = api.get_kline_serial(request['symbol'], 86400, data_length=2)
            while not api.is_serial_ready(serial):
                if not api.wait_update(deadline=deadline):
                    raise TimeoutError
            valid = serial.loc[(serial.datetime > 0) & (serial.close > 0)]
            if valid.empty:
                raise ValueError('No contract prices')
            latest = valid.iloc[-1]
            date = pd.Timestamp(int(valid['datetime'].iloc[-1]), unit='ns', tz='UTC').tz_convert('Asia/Shanghai')
            return {'price': float(latest['close']), 'date': date.isoformat(sep=' ')}
        if request["action"] == "bars":
            serial = api.get_kline_serial(request["symbol"], PERIODS[request["period"]], data_length=SERIES_LENGTH)
            while not api.is_serial_ready(serial):
                if not api.wait_update(deadline=deadline):
                    raise TimeoutError
            columns = ["datetime", "open", "high", "low", "close", "volume", "close_oi"]
            valid = serial.loc[serial.datetime > 0, columns].copy()
            valid["datetime"] = valid["datetime"].astype("int64")
            # Avoid pandas' default float precision when encoding nanoseconds.
            history_complete = bool(serial.loc[serial.datetime > 0, 'id'].min() == 0) if 'id' in serial else False
            return {"bars": valid.to_dict("records"), "history_complete": history_complete}
        quote = api.get_quote(request["symbol"])
        while not quote.datetime or not math.isfinite(quote.last_price) or quote.last_price <= 0:
            if not api.wait_update(deadline=deadline):
                raise TimeoutError
        return {"price": float(quote.last_price), "date": quote.datetime}
    finally:
        if api is not None:
            api.close()


if __name__ == "__main__":
    request = json.loads(sys.stdin.read())
    try:
        # SDK diagnostics may contain authentication context; never forward them.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            response = collect(request)
        print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    except Exception as error:
        message = "天勤取数超时，请检查网络或稍后重试" if isinstance(error, TimeoutError) else "天勤连接或取数失败，请核对快期账号、密码、品种及免费行情权限"
        print(json.dumps({"error": message}, ensure_ascii=False))
        sys.exit(1)
