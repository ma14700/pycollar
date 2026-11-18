
import backtrader as bt

cerebro = bt.Cerebro()
print("Broker attributes:")
print(dir(cerebro.broker))
try:
    cerebro.broker.set_cheat_on_open(True)
    print("set_cheat_on_open success")
except Exception as e:
    print(f"set_cheat_on_open failed: {e}")

try:
    cerebro.broker.set_coc(True)
    print("set_coc success")
except Exception as e:
    print(f"set_coc failed: {e}")
    
try:
    cerebro.broker.set_coo(True)
    print("set_coo success")
except Exception as e:
    print(f"set_coo failed: {e}")
