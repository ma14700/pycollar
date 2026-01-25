import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import MainLayout from '../layouts/MainLayout';
import BacktestPage from '../pages/Backtest';
import EditorPage from '../pages/Editor';
import LogsPage from '../pages/Logs';
import HistoryPage from '../pages/History';

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      {
        path: '/',
        element: <Navigate to="/backtest" replace />,
      },
      {
        path: 'backtest',
        element: <BacktestPage />,
      },
      {
        path: 'editor',
        element: <EditorPage />,
      },
      {
        path: 'logs',
        element: <LogsPage />,
      },
      {
        path: 'history',
        element: <HistoryPage />,
      },
    ],
  },
]);

export default router;
