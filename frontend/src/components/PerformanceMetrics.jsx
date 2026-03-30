import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';

const PerformanceMetrics = () => {
  const [metrics, setMetrics] = useState({});
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchMetrics = async () => {
    try {
      const response = await axios.get('/api/v1/metrics');
      setMetrics(response.data);
      setHistory(prev => [...prev, { timestamp: new Date(), ...response.data }].slice(-24));
    } catch (error) {
      console.error('Error fetching metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div>加载中...</div>;
  }

  return (
    <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h2>性能指标</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', marginTop: '20px' }}>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>总事件数</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
            {metrics.total_events || 0}
          </div>
        </div>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>总错误数</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#e74c3c' }}>
            {metrics.total_errors || 0}
          </div>
        </div>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>模块启动次数</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
            {metrics.module_starts || 0}
          </div>
        </div>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>事件处理时间</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
            {(metrics.event_processing_time_ms || 0).toFixed(2)} ms
          </div>
        </div>
      </div>

      <h3 style={{ marginTop: '30px' }}>性能趋势</h3>
      <div style={{ height: '400px', marginTop: '15px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" tickFormatter={(tick) => new Date(tick).toLocaleTimeString()} />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="total_events" stroke="#3498db" activeDot={{ r: 8 }} />
            <Line type="monotone" dataKey="total_errors" stroke="#e74c3c" />
            <Line type="monotone" dataKey="event_processing_time_ms" stroke="#27ae60" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <h3 style={{ marginTop: '30px' }}>模块状态分布</h3>
      <div style={{ height: '300px', marginTop: '15px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={[
            { name: '运行中', value: metrics.running_modules || 0, fill: '#27ae60' },
            { name: '已停止', value: (metrics.module_count || 0) - (metrics.running_modules || 0), fill: '#e74c3c' }
          ]}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default PerformanceMetrics;