# AI量化策略可视化平台

本项目是一个基于 Python (FastAPI) 和 React (Vite + Ant Design) 的量化交易策略回测平台。

## 项目结构

- `server/`: 后端代码
    - `core/`: 核心回测逻辑 (Backtrader 封装)
    - `main.py`: FastAPI 接口服务
- `web/`: 前端代码 (React)
    - `src/App.jsx`: 主界面逻辑

## 启动方式

### 1. 启动后端服务

打开终端，进入项目根目录：

```bash
# 安装依赖
pip install -r server/requirements.txt

# 启动服务
python server/main.py
```

服务将在 `http://localhost:8000` 启动。

### 2. 启动前端界面

打开新的终端，进入 `web` 目录：

```bash
cd web

# 安装依赖 (如果尚未安装)
npm install

# 启动开发服务器
npm run dev
```

浏览器访问显示的地址 (通常是 `http://localhost:5173`)。

## 功能特性

- **策略配置**：支持动态调整均线周期、ATR止损倍数、风险系数等。
- **多品种支持**：支持生猪、烧碱、螺纹钢等期货品种。
- **可视化回测**：展示账户权益曲线和关键绩效指标 (Sharpe, Drawdown, Win Rate)。
- **交易日志**：详细记录每笔交易的执行情况。
