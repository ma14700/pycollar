import React, { createContext, useState, useContext } from 'react';

const BacktestContext = createContext();

export const BacktestProvider = ({ children }) => {
  const [results, setResults] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [savedFormValues, setSavedFormValues] = useState(null);
  const [savedStrategyType, setSavedStrategyType] = useState('MA55BreakoutStrategy');
  
  return (
    <BacktestContext.Provider value={{ 
      results, setResults, 
      symbols, setSymbols,
      savedFormValues, setSavedFormValues,
      savedStrategyType, setSavedStrategyType
    }}>
      {children}
    </BacktestContext.Provider>
  );
};

export const useBacktest = () => useContext(BacktestContext);
