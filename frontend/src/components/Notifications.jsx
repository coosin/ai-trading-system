import React, { useState, useEffect } from 'react';

function Notifications() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [showSettings, setShowSettings] = useState(false);
  const [notificationSettings, setNotificationSettings] = useState({
    trade_executed: true,
    strategy_status: true,
    system_alerts: true,
    risk_thresholds: true,
    market_movements: false,
    email_notifications: false,
    sms_notifications: false
  });

  useEffect(() => {
    fetchNotifications();
  }, []);

  const fetchNotifications = async () => {
    try {
      setLoading(true);
      // 模拟获取通知列表
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      const mockNotifications = [
        {
          id: '1',
          title: '交易执行成功',
          message: '策略 "移动平均趋势跟踪" 执行了一笔 BTC/USDT 买入交易',
          type: 'trade',
          read: false,
          timestamp: '2024-01-01T12:30:00Z',
          details: {
            strategy: '移动平均趋势跟踪',
            symbol: 'BTC/USDT',
            side: 'buy',
            price: '49500',
            amount: '0.01'
          }
        },
        {
          id: '2',
          title: '策略状态变更',
          message: '策略 "机器学习策略" 已停止运行',
          type: 'strategy',
          read: false,
          timestamp: '2024-01-01T11:45:00Z',
          details: {
            strategy: '机器学习策略',
            status: 'stopped',
            reason: '手动停止'
          }
        },
        {
          id: '3',
          title: '风险阈值警告',
          message: '账户 "Binance 主账户" 的风险敞口已超过设定阈值',
          type: 'risk',
          read: true,
          timestamp: '2024-01-01T10:20:00Z',
          details: {
            account: 'Binance 主账户',
            risk_exposure: '45%',
            threshold: '40%'
          }
        },
        {
          id: '4',
          title: '市场波动提醒',
          message: 'BTC/USDT 价格在过去 1 小时内下跌了 5%',
          type: 'market',
          read: true,
          timestamp: '2024-01-01T09:15:00Z',
          details: {
            symbol: 'BTC/USDT',
            change: '-5%',
            timeframe: '1h'
          }
        },
        {
          id: '5',
          title: '系统状态更新',
          message: '系统已完成每日维护，所有模块运行正常',
          type: 'system',
          read: true,
          timestamp: '2024-01-01T08:00:00Z',
          details: {
            status: 'running',
            modules: 7
          }
        }
      ];
      
      setNotifications(mockNotifications);
    } catch (error) {
      console.error('Error fetching notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  const markAsRead = (notificationId) => {
    setNotifications(prev => prev.map(notification => 
      notification.id === notificationId 
        ? { ...notification, read: true }
        : notification
    ));
  };

  const markAllAsRead = () => {
    setNotifications(prev => prev.map(notification => ({ ...notification, read: true })));
  };

  const deleteNotification = (notificationId) => {
    setNotifications(prev => prev.filter(notification => notification.id !== notificationId));
  };

  const deleteAllNotifications = () => {
    setNotifications([]);
  };

  const filteredNotifications = notifications.filter(notification => {
    if (filter === 'all') return true;
    if (filter === 'unread') return !notification.read;
    return notification.type === filter;
  });

  const updateSettings = (e) => {
    const { name, checked } = e.target;
    setNotificationSettings(prev => ({ ...prev, [name]: checked }));
  };

  if (loading) {
    return <div style={{ padding: '20px' }}>加载通知中...</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h2>通知系统</h2>
      
      <div style={{ marginBottom: '30px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3>通知列表</h3>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={markAllAsRead}
              style={{
                padding: '8px 16px',
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              全部标记为已读
            </button>
            <button
              onClick={deleteAllNotifications}
              style={{
                padding: '8px 16px',
                backgroundColor: '#e74c3c',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              清空通知
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              style={{
                padding: '8px 16px',
                backgroundColor: '#95a5a6',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              通知设置
            </button>
          </div>
        </div>
        
        <div style={{ marginBottom: '20px' }}>
          <label>筛选：</label>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ marginLeft: '10px', padding: '5px' }}
          >
            <option value="all">所有通知</option>
            <option value="unread">未读通知</option>
            <option value="trade">交易通知</option>
            <option value="strategy">策略通知</option>
            <option value="risk">风险通知</option>
            <option value="market">市场通知</option>
            <option value="system">系统通知</option>
          </select>
        </div>
        
        {showSettings && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
            <h4>通知设置</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px' }}>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="trade_executed"
                    checked={notificationSettings.trade_executed}
                    onChange={updateSettings}
                  />
                  交易执行通知
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="strategy_status"
                    checked={notificationSettings.strategy_status}
                    onChange={updateSettings}
                  />
                  策略状态通知
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="system_alerts"
                    checked={notificationSettings.system_alerts}
                    onChange={updateSettings}
                  />
                  系统警报通知
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="risk_thresholds"
                    checked={notificationSettings.risk_thresholds}
                    onChange={updateSettings}
                  />
                  风险阈值通知
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="market_movements"
                    checked={notificationSettings.market_movements}
                    onChange={updateSettings}
                  />
                  市场波动通知
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="email_notifications"
                    checked={notificationSettings.email_notifications}
                    onChange={updateSettings}
                  />
                  邮件通知
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="sms_notifications"
                    checked={notificationSettings.sms_notifications}
                    onChange={updateSettings}
                  />
                  短信通知
                </label>
              </div>
            </div>
          </div>
        )}
        
        <div style={{ maxHeight: '600px', overflowY: 'auto', border: '1px solid #e0e0e0', borderRadius: '8px' }}>
          {filteredNotifications.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
              没有通知
            </div>
          ) : (
            filteredNotifications.map(notification => (
              <div 
                key={notification.id}
                style={{
                  padding: '15px',
                  borderBottom: '1px solid #e0e0e0',
                  backgroundColor: notification.read ? 'white' : '#f8f9fa',
                  cursor: 'pointer'
                }}
                onClick={() => markAsRead(notification.id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                  <div>
                    <h4 style={{ margin: '0 0 5px 0', color: notification.read ? '#333' : '#3498db' }}>
                      {notification.title}
                    </h4>
                    <p style={{ margin: '0', color: '#666' }}>{notification.message}</p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '12px', color: '#999' }}>
                      {new Date(notification.timestamp).toLocaleString()}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteNotification(notification.id);
                      }}
                      style={{
                        marginTop: '5px',
                        padding: '3px 8px',
                        backgroundColor: '#e74c3c',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>
                {notification.details && (
                  <div style={{ marginTop: '10px', padding: '10px', backgroundColor: '#f1f3f4', borderRadius: '4px', fontSize: '14px' }}>
                    {Object.entries(notification.details).map(([key, value]) => (
                      <div key={key}>
                        <strong>{key.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}：</strong>
                        {value}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default Notifications;