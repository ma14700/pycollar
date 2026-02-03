# 周线功能更新说明文档

## 1. 更新概述
本项目已成功集成“周线”K线周期支持。用户现在可以在策略回测、明日策略扫描及品种扫描等模块中选择“周线”作为分析周期。

## 2. 前端变更
涉及以下页面文件的更新，均在“K线周期”选择器中新增了 `<Option value="weekly">周线</Option>` 选项：

*   **策略回测页**: `web/src/pages/Backtest/index.jsx`
*   **品种扫描页**: `web/src/pages/SymbolScan/index.jsx`
*   **明日策略页**: `web/src/pages/TomorrowStrategy/index.jsx`

前端逻辑已确保将 `period="weekly"` 正确传递给后端 API。

## 3. 后端变更

### 3.1 数据加载 (`server/core/data_loader.py`)
*   **股票数据 (`fetch_stock_data`)**: 
    *   更新了逻辑判断 `if period in ['daily', 'weekly', 'monthly']`。
    *   直接调用 `ak.stock_zh_a_hist(..., period=period)` 获取周线数据。
*   **期货数据 (`fetch_futures_data`)**:
    *   新增了对 `period='weekly'` 的处理逻辑。
    *   **实现策略**: 由于上游数据源（新浪/东方财富）通常不提供稳定的期货周线接口，系统采用“获取日线数据 -> Pandas Resample”的策略。
    *   **重采样规则**: 使用 `W-FRI` (周五为一周结束)，聚合规则为：Open(first), High(max), Low(min), Close(last), Volume(sum), OpenInterest(last)。

### 3.2 回测引擎 (`server/core/engine.py`)
*   **`BacktestEngine.run`**:
    *   新增了 `period='weekly'` 到 `backtrader.TimeFrame.Weeks` 的映射。
    *   设置 `compression=1`。

### 3.3 数据库兼容性
*   经检查，`BacktestRecord` 表中的 `period` 字段类型为 `String`，完全兼容 "weekly" 字符串，无需进行数据库迁移。

## 4. 测试报告

已编写并运行单元测试 `tests/test_weekly_feature.py`，覆盖以下场景：

1.  **股票周线获取**: 模拟 AkShare 返回周线数据，验证加载逻辑正确。 -> **通过**
2.  **期货周线重采样**: 模拟期货日线数据，验证重采样逻辑（14天日线 -> 3根周线）及数据聚合正确性。 -> **通过**
3.  **回测引擎集成**: 模拟周线数据输入，运行回测引擎，验证无报错且能生成绩效指标。 -> **通过**

## 5. 维护指南
*   若需修改期货周线的聚合规则（如改为周日结束），请修改 `server/core/data_loader.py` 中的 `resample('W-FRI')` 参数。
*   股票周线数据直接依赖 AkShare 接口，如遇数据源问题，需检查 `ak.stock_zh_a_hist` 的可用性。
