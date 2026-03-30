from flask import Flask, render_template, request, jsonify
import json
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.modules.core.config_manager import ConfigManager

app = Flask(__name__)

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.openclaw-trading', 'config.json')

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')

@app.route('/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    try:
        config_manager = ConfigManager(CONFIG_PATH)
        config = config_manager.get_config()
        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/config', methods=['POST'])
def update_config():
    """更新配置"""
    try:
        new_config = request.json
        config_manager = ConfigManager(CONFIG_PATH)
        config_manager.update_config(new_config)
        return jsonify({'message': '配置更新成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/config/templates', methods=['GET'])
def get_config_templates():
    """获取配置模板"""
    templates = {
        'conservative': {
            'risk_thresholds': {
                'low': 0.1,
                'medium': 0.3,
                'high': 0.6,
                'extreme': 0.9
            },
            'confidence_threshold': 0.7,
            'learning_rate': 0.05,
            'reward_factor': 1.0,
            'penalty_factor': 1.5
        },
        'balanced': {
            'risk_thresholds': {
                'low': 0.2,
                'medium': 0.4,
                'high': 0.7,
                'extreme': 1.0
            },
            'confidence_threshold': 0.6,
            'learning_rate': 0.1,
            'reward_factor': 1.0,
            'penalty_factor': 1.0
        },
        'aggressive': {
            'risk_thresholds': {
                'low': 0.3,
                'medium': 0.5,
                'high': 0.8,
                'extreme': 1.2
            },
            'confidence_threshold': 0.5,
            'learning_rate': 0.15,
            'reward_factor': 1.5,
            'penalty_factor': 0.8
        }
    }
    return jsonify(templates)

@app.route('/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    try:
        # 这里可以添加系统状态检查逻辑
        status = {
            'status': 'running',
            'version': '1.0.0',
            'config_file': CONFIG_PATH,
            'config_exists': os.path.exists(CONFIG_PATH)
        }
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # 创建模板目录和静态文件目录
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
    
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    # 创建基本的HTML模板
    index_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智能量化交易系统配置</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .section {
            margin: 20px 0;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        h2 {
            color: #555;
            font-size: 18px;
            margin-top: 0;
        }
        .form-group {
            margin: 10px 0;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input[type="number"] {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        .template-buttons {
            margin: 10px 0;
        }
        .status {
            background-color: #e8f5e8;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .error {
            background-color: #ffebee;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
            color: #c62828;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>智能量化交易系统配置</h1>
        
        <div class="status" id="status">
            系统状态: 加载中...
        </div>
        
        <div class="section">
            <h2>配置模板</h2>
            <div class="template-buttons">
                <button onclick="loadTemplate('conservative')">保守型</button>
                <button onclick="loadTemplate('balanced')">平衡型</button>
                <button onclick="loadTemplate('aggressive')">激进型</button>
            </div>
        </div>
        
        <div class="section">
            <h2>风险阈值配置</h2>
            <div class="form-group">
                <label for="low_risk">低风险阈值:</label>
                <input type="number" id="low_risk" step="0.01" min="0" max="1">
            </div>
            <div class="form-group">
                <label for="medium_risk">中风险阈值:</label>
                <input type="number" id="medium_risk" step="0.01" min="0" max="1">
            </div>
            <div class="form-group">
                <label for="high_risk">高风险阈值:</label>
                <input type="number" id="high_risk" step="0.01" min="0" max="1">
            </div>
            <div class="form-group">
                <label for="extreme_risk">极端风险阈值:</label>
                <input type="number" id="extreme_risk" step="0.01" min="0" max="1">
            </div>
        </div>
        
        <div class="section">
            <h2>决策参数配置</h2>
            <div class="form-group">
                <label for="confidence_threshold">置信度阈值:</label>
                <input type="number" id="confidence_threshold" step="0.01" min="0" max="1">
            </div>
            <div class="form-group">
                <label for="learning_rate">学习率:</label>
                <input type="number" id="learning_rate" step="0.01" min="0" max="1">
            </div>
            <div class="form-group">
                <label for="reward_factor">奖励因子:</label>
                <input type="number" id="reward_factor" step="0.01" min="0" max="2">
            </div>
            <div class="form-group">
                <label for="penalty_factor">惩罚因子:</label>
                <input type="number" id="penalty_factor" step="0.01" min="0" max="2">
            </div>
        </div>
        
        <div class="section">
            <button onclick="saveConfig()">保存配置</button>
            <button onclick="loadConfig()">加载配置</button>
        </div>
        
        <div id="message"></div>
    </div>
    
    <script>
        // 加载配置
        async function loadConfig() {
            try {
                const response = await fetch('/config');
                const config = await response.json();
                
                if (config.error) {
                    document.getElementById('message').innerHTML = `<div class="error">${config.error}</div>`;
                    return;
                }
                
                // 填充表单
                if (config.risk_thresholds) {
                    document.getElementById('low_risk').value = config.risk_thresholds.low || 0.2;
                    document.getElementById('medium_risk').value = config.risk_thresholds.medium || 0.4;
                    document.getElementById('high_risk').value = config.risk_thresholds.high || 0.7;
                    document.getElementById('extreme_risk').value = config.risk_thresholds.extreme || 1.0;
                }
                
                document.getElementById('confidence_threshold').value = config.confidence_threshold || 0.6;
                document.getElementById('learning_rate').value = config.learning_rate || 0.1;
                document.getElementById('reward_factor').value = config.reward_factor || 1.0;
                document.getElementById('penalty_factor').value = config.penalty_factor || 1.0;
                
                document.getElementById('message').innerHTML = '<div class="status">配置加载成功</div>';
            } catch (error) {
                document.getElementById('message').innerHTML = `<div class="error">加载配置失败: ${error.message}</div>`;
            }
        }
        
        // 保存配置
        async function saveConfig() {
            try {
                const config = {
                    risk_thresholds: {
                        low: parseFloat(document.getElementById('low_risk').value),
                        medium: parseFloat(document.getElementById('medium_risk').value),
                        high: parseFloat(document.getElementById('high_risk').value),
                        extreme: parseFloat(document.getElementById('extreme_risk').value)
                    },
                    confidence_threshold: parseFloat(document.getElementById('confidence_threshold').value),
                    learning_rate: parseFloat(document.getElementById('learning_rate').value),
                    reward_factor: parseFloat(document.getElementById('reward_factor').value),
                    penalty_factor: parseFloat(document.getElementById('penalty_factor').value)
                };
                
                const response = await fetch('/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(config)
                });
                
                const result = await response.json();
                if (result.error) {
                    document.getElementById('message').innerHTML = `<div class="error">${result.error}</div>`;
                } else {
                    document.getElementById('message').innerHTML = '<div class="status">配置保存成功</div>';
                }
            } catch (error) {
                document.getElementById('message').innerHTML = `<div class="error">保存配置失败: ${error.message}</div>`;
            }
        }
        
        // 加载配置模板
        async function loadTemplate(templateName) {
            try {
                const response = await fetch('/config/templates');
                const templates = await response.json();
                const template = templates[templateName];
                
                if (template) {
                    // 填充表单
                    document.getElementById('low_risk').value = template.risk_thresholds.low;
                    document.getElementById('medium_risk').value = template.risk_thresholds.medium;
                    document.getElementById('high_risk').value = template.risk_thresholds.high;
                    document.getElementById('extreme_risk').value = template.risk_thresholds.extreme;
                    document.getElementById('confidence_threshold').value = template.confidence_threshold;
                    document.getElementById('learning_rate').value = template.learning_rate;
                    document.getElementById('reward_factor').value = template.reward_factor;
                    document.getElementById('penalty_factor').value = template.penalty_factor;
                    
                    document.getElementById('message').innerHTML = `<div class="status">已加载${templateName === 'conservative' ? '保守型' : templateName === 'balanced' ? '平衡型' : '激进型'}配置模板</div>`;
                }
            } catch (error) {
                document.getElementById('message').innerHTML = `<div class="error">加载模板失败: ${error.message}</div>`;
            }
        }
        
        // 加载系统状态
        async function loadStatus() {
            try {
                const response = await fetch('/status');
                const status = await response.json();
                
                if (status.error) {
                    document.getElementById('status').innerHTML = `系统状态: 错误 - ${status.error}`;
                } else {
                    document.getElementById('status').innerHTML = `系统状态: ${status.status} | 版本: ${status.version}`;
                }
            } catch (error) {
                document.getElementById('status').innerHTML = `系统状态: 错误 - ${error.message}`;
            }
        }
        
        // 页面加载时初始化
        window.onload = function() {
            loadStatus();
            loadConfig();
        };
    </script>
</body>
</html>
    '''
    
    index_path = os.path.join(template_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_html)
    
    # 启动应用
    app.run(host='0.0.0.0', port=5000, debug=True)
