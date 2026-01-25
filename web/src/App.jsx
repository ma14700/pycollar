import React from 'react';
import { RouterProvider } from 'react-router-dom';
import router from './router';
import { BacktestProvider } from './context/BacktestContext';
import './App.css';

const App = () => {
  return (
    <BacktestProvider>
      <RouterProvider router={router} />
    </BacktestProvider>
  );
};

export default App;
