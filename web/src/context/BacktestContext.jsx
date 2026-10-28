import React, { createContext, useState, useContext, useEffect, useSyncExternalStore } from 'react';
import axios from 'axios';
import { message } from 'antd';
import { createBacktestTask } from '../utils/backtestTask';

const BacktestContext = createContext();

export const BacktestProvider = ({ children }) => {
  const [task] = useState(() => createBacktestTask(payload =>
    axios.post('http://localhost:8000/api/backtest', payload).then(response => response.data)));
  const taskState = useSyncExternalStore(task.subscribe, task.getSnapshot);
  const [symbols, setSymbols] = useState([]);
  const [savedFormValues, setSavedFormValues] = useState(null);
  const [savedStrategyType, setSavedStrategyType] = useState('MA55BreakoutStrategy');
  const [autoOptimize, setAutoOptimize] = useState(false);
  const [currentParams, setCurrentParams] = useState(null);

  useEffect(() => {
    const run = taskState.activeRun;
    if (!run || run.status === 'running') return;
    if (run.status === 'failed') message.error(taskState.runError || '本次回测全部失败，请返回策略回测查看详情');
    else if (run.failed) message.warning(`回测完成：成功 ${run.total - run.failed}/${run.total}，请查看失败项`);
    else message.success(run.total > 1 ? `批量回测完成：成功 ${run.total}/${run.total}` : '回测完成');
  }, [taskState.activeRun, taskState.runError]);
  
  return (
    <BacktestContext.Provider value={{ 
      ...taskState, startBacktest: task.start,
      symbols, setSymbols,
      savedFormValues, setSavedFormValues,
      savedStrategyType, setSavedStrategyType,
      autoOptimize, setAutoOptimize, currentParams, setCurrentParams
    }}>
      {children}
    </BacktestContext.Provider>
  );
};

export const useBacktest = () => useContext(BacktestContext);
