import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';

const Dashboard = () => {
  const [dashboardConfig, setDashboardConfig] = useState({
    widgets: [
      {
        id: 1,
        type: 'line',
        title: 'BTC价格走势',
        data: [
          { name: '1月', price: 40000 },
          { name: '2月', price: 45000 },
          { name: '3月', price: 50000 },
          { name: '4月', price: 48000 },
          { name: '5月', price: 52000 },
          { name: '6月', price: 55000 },
        ],
        xKey: 'name',
        yKey: 'price',
        color: '#3b82f6',
        width: '100%',
        height: 300
      },
      {
        id: 2,
        type: 'bar',
        title: '策略性能',
        data: [
          { name: 'MA策略', pnl: 1250.50 },
          { name: 'RSI策略', pnl: 980.25 },
          { name: 'BB策略', pnl: 850.75 },
          { name: 'MACD策略', pnl: 1100.20 },
        ],
        xKey: 'name',
        yKey: 'pnl',
        color: '#10b981',
        width: '100%',
        height: 300
      },
      {
        id: 3,
        type: 'pie',
        title: '资产分布',
        data: [
          { name: 'BTC', value: 60 },
          { name: 'ETH', value: 25 },
          { name: '其他', value: 15 },
        ],
        color: '#8b5cf6',
        width: '100%',
        height: 300
      },
      {
        id: 4,
        type: 'radar',
        title: '风险指标',
        data: [
          { subject: 'VaR', A: 80, fullMark: 100 },
          { subject: '夏普比率', A: 90, fullMark: 100 },
          { subject: '最大回撤', A: 70, fullMark: 100 },
          { subject: '胜率', A: 85, fullMark: 100 },
          { subject: '盈亏比', A: 75, fullMark: 100 },
        ],
        width: '100%',
        height: 300
      }
    ]
  });

  const [showAddWidget, setShowAddWidget] = useState(false);
  const [newWidget, setNewWidget] = useState({
    type: 'line',
    title: '',
    data: [],
    xKey: 'name',
    yKey: 'value',
    color: '#3b82f6',
    width: '100%',
    height: 300
  });

  const addWidget = () => {
    const newId = Math.max(...dashboardConfig.widgets.map(w => w.id)) + 1;
    const widget = {
      id: newId,
      ...newWidget
    };
    setDashboardConfig({
      widgets: [...dashboardConfig.widgets, widget]
    });
    setShowAddWidget(false);
  };

  const removeWidget = (id) => {
    setDashboardConfig({
      widgets: dashboardConfig.widgets.filter(w => w.id !== id)
    });
  };

  const renderWidget = (widget) => {
    switch (widget.type) {
      case 'line':
        return (
          <ResponsiveContainer width={widget.width} height={widget.height}>
            <LineChart data={widget.data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={widget.xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey={widget.yKey} stroke={widget.color} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        );
      case 'bar':
        return (
          <ResponsiveContainer width={widget.width} height={widget.height}>
            <BarChart data={widget.data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={widget.xKey} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey={widget.yKey} fill={widget.color} />
            </BarChart>
          </ResponsiveContainer>
        );
      case 'pie':
        return (
          <ResponsiveContainer width={widget.width} height={widget.height}>
            <PieChart>
              <Pie
                data={widget.data}
                cx="50%"
                cy="50%"
                labelLine={false}
                outerRadius={80}
                fill={widget.color}
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        );
      case 'radar':
        return (
          <ResponsiveContainer width={widget.width} height={widget.height}>
            <RadarChart outerRadius={90} data={widget.data}>
              <PolarGrid />
              <PolarAngleAxis dataKey="subject" />
              <PolarRadiusAxis angle={30} domain={[0, 100]} />
              <Radar name="风险指标" dataKey="A" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
              <Legend />
            </RadarChart>
          </ResponsiveContainer>
        );
      default:
        return null;
    }
  };

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>自定义仪表盘</h2>
        <button 
          className="add-widget-btn"
          onClick={() => setShowAddWidget(!showAddWidget)}
        >
          添加图表
        </button>
      </div>

      {showAddWidget && (
        <div className="add-widget-form">
          <h3>添加新图表</h3>
          <div className="form-group">
            <label>图表类型</label>
            <select 
              value={newWidget.type} 
              onChange={(e) => setNewWidget({...newWidget, type: e.target.value})}
            >
              <option value="line">折线图</option>
              <option value="bar">柱状图</option>
              <option value="pie">饼图</option>
              <option value="radar">雷达图</option>
            </select>
          </div>
          <div className="form-group">
            <label>图表标题</label>
            <input 
              type="text" 
              value={newWidget.title} 
              onChange={(e) => setNewWidget({...newWidget, title: e.target.value})}
            />
          </div>
          <div className="form-group">
            <label>颜色</label>
            <input 
              type="color" 
              value={newWidget.color} 
              onChange={(e) => setNewWidget({...newWidget, color: e.target.value})}
            />
          </div>
          <div className="form-actions">
            <button onClick={addWidget}>添加</button>
            <button onClick={() => setShowAddWidget(false)}>取消</button>
          </div>
        </div>
      )}

      <div className="widget-grid">
        {dashboardConfig.widgets.map(widget => (
          <div key={widget.id} className="widget">
            <div className="widget-header">
              <h3>{widget.title}</h3>
              <button 
                className="remove-widget-btn"
                onClick={() => removeWidget(widget.id)}
              >
                ×
              </button>
            </div>
            <div className="widget-content">
              {renderWidget(widget)}
            </div>
          </div>
        ))}
      </div>

      <style jsx>{`
        .dashboard {
          padding: 20px;
        }
        .dashboard-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 20px;
        }
        .dashboard-header h2 {
          margin: 0;
          color: #1e293b;
        }
        .add-widget-btn {
          background-color: #3b82f6;
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
        }
        .add-widget-btn:hover {
          background-color: #2563eb;
        }
        .add-widget-form {
          background-color: #f8fafc;
          padding: 20px;
          border-radius: 8px;
          margin-bottom: 20px;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .add-widget-form h3 {
          margin-top: 0;
          color: #1e293b;
        }
        .form-group {
          margin-bottom: 15px;
        }
        .form-group label {
          display: block;
          margin-bottom: 5px;
          font-weight: 500;
          color: #475569;
        }
        .form-group input,
        .form-group select {
          width: 100%;
          padding: 8px;
          border: 1px solid #cbd5e1;
          border-radius: 4px;
        }
        .form-actions {
          display: flex;
          gap: 10px;
          margin-top: 20px;
        }
        .form-actions button {
          padding: 8px 16px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }
        .form-actions button:first-child {
          background-color: #10b981;
          color: white;
        }
        .form-actions button:last-child {
          background-color: #64748b;
          color: white;
        }
        .widget-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
          gap: 20px;
        }
        .widget {
          background-color: white;
          border-radius: 8px;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
          overflow: hidden;
        }
        .widget-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 15px;
          background-color: #f1f5f9;
        }
        .widget-header h3 {
          margin: 0;
          color: #1e293b;
          font-size: 16px;
        }
        .remove-widget-btn {
          background: none;
          border: none;
          font-size: 20px;
          cursor: pointer;
          color: #64748b;
        }
        .remove-widget-btn:hover {
          color: #ef4444;
        }
        .widget-content {
          padding: 15px;
        }
      `}</style>
    </div>
  );
};

export default Dashboard;