import { create } from 'zustand';
import { api } from '../services/api';

// 认证状态管理
const useAuthStore = create((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  // 初始化时从localStorage恢复状态
  initialize: () => {
    const token = localStorage.getItem('auth_token');
    const user = localStorage.getItem('user');
    if (token && user) {
      try {
        set({
          token,
          user: JSON.parse(user),
          isAuthenticated: true,
        });
      } catch (e) {
        console.error('Failed to parse user from localStorage:', e);
      }
    }
  },

  // 登录
  login: async (credentials) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.auth.login(credentials);
      const { token, user } = response;
      
      localStorage.setItem('auth_token', token);
      localStorage.setItem('user', JSON.stringify(user));
      
      set({
        token,
        user,
        isAuthenticated: true,
        isLoading: false,
      });
      
      return response;
    } catch (error) {
      set({
        error: error.message,
        isLoading: false,
      });
      throw error;
    }
  },

  // 登出
  logout: async () => {
    try {
      await api.auth.logout();
    } catch (error) {
      console.error('Logout error:', error);
    }
    
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      error: null,
    });
  },

  // 获取当前用户
  fetchCurrentUser: async () => {
    if (!get().isAuthenticated) return;
    
    set({ isLoading: true, error: null });
    try {
      const user = await api.auth.getCurrentUser();
      localStorage.setItem('user', JSON.stringify(user));
      
      set({
        user,
        isLoading: false,
      });
    } catch (error) {
      set({
        error: error.message,
        isLoading: false,
      });
    }
  },

  // 清除错误
  clearError: () => set({ error: null }),
}));

// 系统状态管理
const useSystemStore = create((set, get) => ({
  status: null,
  health: null,
  metrics: null,
  isLoading: false,
  error: null,
  theme: localStorage.getItem('theme') || 'light', // 从localStorage恢复主题

  // 获取系统状态
  fetchStatus: async () => {
    set({ isLoading: true, error: null });
    try {
      const status = await api.system.getStatus();
      set({ status, isLoading: false });
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  // 获取健康检查
  fetchHealth: async () => {
    try {
      const health = await api.system.getHealth();
      set({ health });
    } catch (error) {
      console.error('Failed to fetch health:', error);
    }
  },

  // 获取指标
  fetchMetrics: async () => {
    try {
      const metrics = await api.system.getMetrics();
      set({ metrics });
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
    }
  },

  // 切换主题
  toggleTheme: () => set((state) => {
    const newTheme = state.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', newTheme);
    return { theme: newTheme };
  }),

  // 设置主题
  setTheme: (theme) => {
    localStorage.setItem('theme', theme);
    set({ theme });
  },

  // 清除错误
  clearError: () => set({ error: null }),
}));

// 主题样式管理
const useThemeStyles = () => {
  const theme = useSystemStore((state) => state.theme);
  
  return {
    container: {
      backgroundColor: theme === 'dark' ? '#1a1a1a' : '#f0f2f5',
      color: theme === 'dark' ? '#e0e0e0' : '#333',
      minHeight: '100vh'
    },
    sidebar: {
      backgroundColor: theme === 'dark' ? '#2d2d2d' : '#3498db',
      color: 'white'
    },
    content: {
      backgroundColor: theme === 'dark' ? '#1a1a1a' : 'white',
      color: theme === 'dark' ? '#e0e0e0' : '#333'
    },
    card: {
      backgroundColor: theme === 'dark' ? '#2d2d2d' : '#f8f9fa',
      color: theme === 'dark' ? '#e0e0e0' : '#333',
      border: theme === 'dark' ? '1px solid #444' : '1px solid #e9ecef'
    },
    button: {
      backgroundColor: theme === 'dark' ? '#34495e' : '#3498db',
      color: 'white',
      border: theme === 'dark' ? '1px solid #5a6d80' : '1px solid #2980b9'
    },
    input: {
      backgroundColor: theme === 'dark' ? '#343434' : 'white',
      color: theme === 'dark' ? '#e0e0e0' : '#333',
      border: theme === 'dark' ? '1px solid #444' : '1px solid #ced4da'
    },
    table: {
      backgroundColor: theme === 'dark' ? '#2d2d2d' : 'white',
      color: theme === 'dark' ? '#e0e0e0' : '#333'
    },
    tableHeader: {
      backgroundColor: theme === 'dark' ? '#3a3a3a' : '#e9ecef'
    },
    tableRow: {
      borderBottom: theme === 'dark' ? '1px solid #444' : '1px solid #dee2e6'
    }
  };
};

// 策略状态管理
const useStrategyStore = create((set, get) => ({
  strategies: [],
  activeStrategy: null,
  isLoading: false,
  error: null,

  // 获取所有策略
  fetchStrategies: async () => {
    set({ isLoading: true, error: null });
    try {
      const strategies = await api.strategies.getAll();
      set({ strategies, isLoading: false });
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  // 创建策略
  createStrategy: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const newStrategy = await api.strategies.create(data);
      set((state) => ({
        strategies: [...state.strategies, newStrategy],
        isLoading: false,
      }));
      return newStrategy;
    } catch (error) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  // 更新策略
  updateStrategy: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updatedStrategy = await api.strategies.update(id, data);
      set((state) => ({
        strategies: state.strategies.map((s) => 
          s.id === id ? updatedStrategy : s
        ),
        isLoading: false,
      }));
      return updatedStrategy;
    } catch (error) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  // 删除策略
  deleteStrategy: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await api.strategies.delete(id);
      set((state) => ({
        strategies: state.strategies.filter((s) => s.id !== id),
        isLoading: false,
      }));
    } catch (error) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  // 激活策略
  activateStrategy: async (id) => {
    try {
      await api.strategies.activate(id);
      set((state) => ({
        strategies: state.strategies.map((s) => 
          s.id === id ? { ...s, is_active: true } : { ...s, is_active: false }
        ),
      }));
    } catch (error) {
      console.error('Failed to activate strategy:', error);
      throw error;
    }
  },

  // 设置活动策略
  setActiveStrategy: (strategy) => set({ activeStrategy: strategy }),

  // 清除错误
  clearError: () => set({ error: null }),
}));

// 交易状态管理
const useTradingStore = create((set, get) => ({
  positions: [],
  orders: [],
  tradeHistory: [],
  isLoading: false,
  error: null,

  // 获取持仓
  fetchPositions: async () => {
    set({ isLoading: true, error: null });
    try {
      const positions = await api.trading.getPositions();
      set({ positions, isLoading: false });
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  // 获取订单
  fetchOrders: async () => {
    try {
      const orders = await api.trading.getOrders();
      set({ orders });
    } catch (error) {
      console.error('Failed to fetch orders:', error);
    }
  },

  // 创建订单
  createOrder: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const order = await api.trading.createOrder(data);
      set((state) => ({
        orders: [order, ...state.orders],
        isLoading: false,
      }));
      return order;
    } catch (error) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  // 取消订单
  cancelOrder: async (id) => {
    try {
      await api.trading.cancelOrder(id);
      set((state) => ({
        orders: state.orders.filter((o) => o.id !== id),
      }));
    } catch (error) {
      console.error('Failed to cancel order:', error);
      throw error;
    }
  },

  // 获取交易历史
  fetchHistory: async (params) => {
    try {
      const history = await api.trading.getHistory(params);
      set({ tradeHistory: history });
    } catch (error) {
      console.error('Failed to fetch trade history:', error);
    }
  },

  // 清除错误
  clearError: () => set({ error: null }),
}));

// 市场数据状态管理
const useMarketStore = create((set, get) => ({
  symbols: [],
  tickers: {},
  klines: {},
  orderBooks: {},
  selectedSymbol: 'BTC/USDT',
  isLoading: false,
  error: null,

  // 获取交易对
  fetchSymbols: async () => {
    try {
      const symbols = await api.market.getSymbols();
      set({ symbols });
    } catch (error) {
      console.error('Failed to fetch symbols:', error);
    }
  },

  // 获取Ticker
  fetchTicker: async (symbol) => {
    try {
      const ticker = await api.market.getTicker(symbol);
      set((state) => ({
        tickers: { ...state.tickers, [symbol]: ticker },
      }));
    } catch (error) {
      console.error('Failed to fetch ticker:', error);
    }
  },

  // 获取K线
  fetchKlines: async (symbol, interval, limit = 100) => {
    set({ isLoading: true, error: null });
    try {
      const klines = await api.market.getKlines(symbol, interval, limit);
      const key = `${symbol}_${interval}`;
      set((state) => ({
        klines: { ...state.klines, [key]: klines },
        isLoading: false,
      }));
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  // 获取订单簿
  fetchOrderBook: async (symbol) => {
    try {
      const orderBook = await api.market.getOrderBook(symbol);
      set((state) => ({
        orderBooks: { ...state.orderBooks, [symbol]: orderBook },
      }));
    } catch (error) {
      console.error('Failed to fetch order book:', error);
    }
  },

  // 设置选中的交易对
  setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),

  // 清除错误
  clearError: () => set({ error: null }),
}));

export {
  useAuthStore,
  useSystemStore,
  useStrategyStore,
  useTradingStore,
  useMarketStore,
  useThemeStyles
};
