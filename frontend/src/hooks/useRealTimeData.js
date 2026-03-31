import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

/**
 * 实时数据获取Hook
 * 用于获取真实的市场数据、技术指标和AI分析结果
 */

export function useMarketData(symbol, interval = '1m', limit = 60) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.market.getKlines(symbol, interval, limit);
      setData(response.data || []);
      setError(null);
    } catch (err) {
      console.error('获取市场数据失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, limit]);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 5000); // 每5秒刷新
    return () => clearInterval(timer);
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

export function useTechnicalIndicators(symbol) {
  const [indicators, setIndicators] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchIndicators = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.externalData.getIndicators(symbol, ['rsi', 'macd', 'sma', 'ema', 'bollinger']);
      setIndicators(response.data || {});
      setError(null);
    } catch (err) {
      console.error('获取技术指标失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchIndicators();
    const timer = setInterval(fetchIndicators, 10000); // 每10秒刷新
    return () => clearInterval(timer);
  }, [fetchIndicators]);

  return { indicators, loading, error, refetch: fetchIndicators };
}

export function useAIMarketAnalysis(symbol) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const analyze = useCallback(async (modelId = 'astron-code-latest') => {
    try {
      setLoading(true);
      
      // 先获取市场数据
      const marketResponse = await api.market.getKlines(symbol, '1h', 24);
      const marketData = {
        symbol,
        price: marketResponse.data?.[marketResponse.data.length - 1]?.close || 0,
        data: marketResponse.data || []
      };
      
      // 调用AI分析
      const response = await api.ai.analyzeMarket(marketData, modelId);
      setAnalysis(response.data);
      setError(null);
    } catch (err) {
      console.error('AI分析失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  return { analysis, loading, error, analyze };
}

export function useAITradingSignal(symbol) {
  const [signal, setSignal] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const generateSignal = useCallback(async (modelId = 'astron-code-latest') => {
    try {
      setLoading(true);
      
      // 获取市场数据
      const marketResponse = await api.market.getKlines(symbol, '1h', 24);
      const marketData = {
        symbol,
        price: marketResponse.data?.[marketResponse.data.length - 1]?.close || 0,
        data: marketResponse.data || []
      };
      
      // 调用AI生成信号
      const response = await api.ai.generateSignal(marketData, modelId);
      setSignal(response.data);
      setError(null);
    } catch (err) {
      console.error('生成交易信号失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  return { signal, loading, error, generateSignal };
}

export function useOrderBook(symbol) {
  const [orderBook, setOrderBook] = useState({ bids: [], asks: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchOrderBook = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.market.getOrderBook(symbol);
      setOrderBook(response.data || { bids: [], asks: [] });
      setError(null);
    } catch (err) {
      console.error('获取订单簿失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchOrderBook();
    const timer = setInterval(fetchOrderBook, 2000); // 每2秒刷新
    return () => clearInterval(timer);
  }, [fetchOrderBook]);

  return { orderBook, loading, error, refetch: fetchOrderBook };
}

export function useTrades(symbol, limit = 20) {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchTrades = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.trading.getHistory({ symbol, limit });
      setTrades(response.data || []);
      setError(null);
    } catch (err) {
      console.error('获取交易历史失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [symbol, limit]);

  useEffect(() => {
    fetchTrades();
    const timer = setInterval(fetchTrades, 3000); // 每3秒刷新
    return () => clearInterval(timer);
  }, [fetchTrades]);

  return { trades, loading, error, refetch: fetchTrades };
}

export function useStrategies() {
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchStrategies = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.strategies.getAll();
      setStrategies(response.data || []);
      setError(null);
    } catch (err) {
      console.error('获取策略列表失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStrategies();
  }, [fetchStrategies]);

  return { strategies, loading, error, refetch: fetchStrategies };
}

export function usePerformance() {
  const [performance, setPerformance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchPerformance = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.performance.getMetrics();
      setPerformance(response.data);
      setError(null);
    } catch (err) {
      console.error('获取性能指标失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPerformance();
    const timer = setInterval(fetchPerformance, 30000); // 每30秒刷新
    return () => clearInterval(timer);
  }, [fetchPerformance]);

  return { performance, loading, error, refetch: fetchPerformance };
}

export function useRiskMetrics() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchMetrics = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.risk.getMetrics();
      setMetrics(response.data);
      setError(null);
    } catch (err) {
      console.error('获取风险指标失败:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const timer = setInterval(fetchMetrics, 30000); // 每30秒刷新
    return () => clearInterval(timer);
  }, [fetchMetrics]);

  return { metrics, loading, error, refetch: fetchMetrics };
}
