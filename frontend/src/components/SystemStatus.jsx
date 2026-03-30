import React from 'react';

const SystemStatus = ({ status, loading }) => {
  if (loading) {
    return <div>加载中...</div>;
  }

  if (!status) {
    return <div>无法获取系统状态</div>;
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return '#27ae60';
      case 'starting':
        return '#f39c12';
      case 'stopped':
        return '#e74c3c';
      case 'error':
        return '#c0392b';
      default:
        return '#95a5a6';
    }
  };

  return (
    <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h2>系统状态</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', marginTop: '20px' }}>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>系统状态</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: getStatusColor(status.system_status) }}>
            {status.system_status}
          </div>
        </div>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>运行时间</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
            {Math.round(status.uptime / 3600)} 小时
          </div>
        </div>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>模块数量</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
            {status.module_count}
          </div>
        </div>
        <div style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
          <h3>运行中模块</h3>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
            {status.running_modules}
          </div>
        </div>
      </div>

      <h3 style={{ marginTop: '30px' }}>模块状态</h3>
      <div style={{ overflowX: 'auto', marginTop: '15px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: '#f5f5f5' }}>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>模块名称</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>状态</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>健康状态</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>运行时间</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>错误数</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(status.module_statuses).map(([name, moduleStatus]) => (
              <tr key={name}>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{name}</td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0', color: getStatusColor(moduleStatus.status) }}>
                  {moduleStatus.status}
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  {moduleStatus.health}
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  {Math.round(moduleStatus.uptime / 3600)} 小时
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  {moduleStatus.error_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SystemStatus;