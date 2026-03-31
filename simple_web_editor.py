#!/usr/bin/env python3
"""
简单Web代码编辑器
可以通过浏览器编辑交易系统代码
"""

import os
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = Path(__file__).parent.absolute()
TRADING_SYSTEM_DIR = BASE_DIR

class CodeEditorHandler(BaseHTTPRequestHandler):
    """处理HTTP请求的处理器"""
    
    def do_GET(self):
        """处理GET请求"""
        try:
            if self.path == '/':
                self.send_index()
            elif self.path == '/api/files':
                self.send_file_list()
            elif self.path.startswith('/api/file/'):
                file_path = self.path[10:]  # 去掉 '/api/file/'
                self.send_file_content(file_path)
            elif self.path.startswith('/static/'):
                self.send_static_file()
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            self.send_error(500, f"Server Error: {str(e)}")
    
    def do_POST(self):
        """处理POST请求（保存文件）"""
        if self.path.startswith('/api/save/'):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            file_path = self.path[10:]  # 去掉 '/api/save/'
            file_full_path = TRADING_SYSTEM_DIR / file_path
            
            try:
                # 保存文件
                with open(file_full_path, 'w', encoding='utf-8') as f:
                    f.write(data['content'])
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': '文件保存成功'
                }).encode('utf-8'))
            except Exception as e:
                self.send_error(500, f"保存失败: {str(e)}")
        else:
            self.send_error(404, "Not Found")
    
    def send_index(self):
        """发送主页HTML"""
        html = '''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>交易系统代码编辑器</title>
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #1e1e1e;
                    color: #d4d4d4;
                }
                .container {
                    display: flex;
                    height: 90vh;
                    gap: 20px;
                }
                .sidebar {
                    width: 300px;
                    background: #252526;
                    border-radius: 8px;
                    padding: 20px;
                    overflow-y: auto;
                }
                .editor-container {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                }
                .file-list {
                    list-style: none;
                    padding: 0;
                }
                .file-item {
                    padding: 8px 12px;
                    cursor: pointer;
                    border-radius: 4px;
                    margin-bottom: 4px;
                }
                .file-item:hover {
                    background: #2a2d2e;
                }
                .file-item.active {
                    background: #094771;
                }
                .py-file { color: #4ec9b0; }
                .md-file { color: #ce9178; }
                .sh-file { color: #dcdcaa; }
                .txt-file { color: #9cdcfe; }
                .editor-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 10px;
                }
                #editor {
                    flex: 1;
                    border: 1px solid #3e3e42;
                    border-radius: 8px;
                    overflow: hidden;
                }
                button {
                    background: #007acc;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                }
                button:hover {
                    background: #0062a3;
                }
                .status {
                    margin-top: 10px;
                    padding: 8px;
                    border-radius: 4px;
                    display: none;
                }
                .success { background: #2d5a27; }
                .error { background: #5a1f1f; }
            </style>
        </head>
        <body>
            <h1>📝 交易系统代码编辑器</h1>
            <div class="container">
                <div class="sidebar">
                    <h3>📁 文件列表</h3>
                    <ul id="fileList" class="file-list"></ul>
                </div>
                <div class="editor-container">
                    <div class="editor-header">
                        <h3 id="fileName">选择文件开始编辑</h3>
                        <button onclick="saveFile()">💾 保存</button>
                    </div>
                    <div id="editor"></div>
                    <div id="status" class="status"></div>
                </div>
            </div>
            
            <script src="https://cdnjs.cloudflare.com/ajax/libs/ace/1.15.2/ace.js"></script>
            <script>
                let editor = null;
                let currentFile = '';
                
                // 初始化编辑器
                function initEditor() {
                    editor = ace.edit("editor");
                    editor.setTheme("ace/theme/monokai");
                    editor.session.setMode("ace/mode/python");
                    editor.setOptions({
                        fontSize: "14px",
                        showPrintMargin: false
                    });
                }
                
                // 加载文件列表
                async function loadFileList() {
                    try {
                        const response = await fetch('/api/files');
                        const files = await response.json();
                        
                        const fileList = document.getElementById('fileList');
                        fileList.innerHTML = '';
                        
                        files.forEach(file => {
                            const li = document.createElement('li');
                            li.className = `file-item ${getFileClass(file)}`;
                            li.textContent = file;
                            li.onclick = () => loadFile(file);
                            fileList.appendChild(li);
                        });
                    } catch (error) {
                        console.error('加载文件列表失败:', error);
                    }
                }
                
                // 加载文件内容
                async function loadFile(filename) {
                    try {
                        const response = await fetch(`/api/file/${encodeURIComponent(filename)}`);
                        if (!response.ok) throw new Error('加载失败');
                        
                        const data = await response.json();
                        currentFile = filename;
                        document.getElementById('fileName').textContent = `📄 ${filename}`;
                        
                        // 设置编辑器内容和模式
                        editor.setValue(data.content, -1);
                        editor.session.setMode(getEditorMode(filename));
                        
                        // 高亮当前文件
                        document.querySelectorAll('.file-item').forEach(item => {
                            item.classList.remove('active');
                        });
                        document.querySelector(`.file-item:contains('${filename}')`).classList.add('active');
                        
                        showStatus('文件加载成功', 'success');
                    } catch (error) {
                        showStatus(`加载失败: ${error.message}`, 'error');
                    }
                }
                
                // 保存文件
                async function saveFile() {
                    if (!currentFile) {
                        showStatus('请先选择文件', 'error');
                        return;
                    }
                    
                    try {
                        const response = await fetch(`/api/save/${encodeURIComponent(currentFile)}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ content: editor.getValue() })
                        });
                        
                        const result = await response.json();
                        if (result.success) {
                            showStatus('保存成功', 'success');
                        } else {
                            showStatus('保存失败', 'error');
                        }
                    } catch (error) {
                        showStatus(`保存失败: ${error.message}`, 'error');
                    }
                }
                
                // 工具函数
                function getFileClass(filename) {
                    if (filename.endsWith('.py')) return 'py-file';
                    if (filename.endsWith('.md')) return 'md-file';
                    if (filename.endsWith('.sh')) return 'sh-file';
                    return 'txt-file';
                }
                
                function getEditorMode(filename) {
                    if (filename.endsWith('.py')) return 'ace/mode/python';
                    if (filename.endsWith('.js') || filename.endsWith('.jsx')) return 'ace/mode/javascript';
                    if (filename.endsWith('.html')) return 'ace/mode/html';
                    if (filename.endsWith('.css')) return 'ace/mode/css';
                    if (filename.endsWith('.md')) return 'ace/mode/markdown';
                    if (filename.endsWith('.json')) return 'ace/mode/json';
                    return 'ace/mode/text';
                }
                
                function showStatus(message, type) {
                    const status = document.getElementById('status');
                    status.textContent = message;
                    status.className = `status ${type}`;
                    status.style.display = 'block';
                    setTimeout(() => {
                        status.style.display = 'none';
                    }, 3000);
                }
                
                // 初始化
                window.onload = function() {
                    initEditor();
                    loadFileList();
                };
            </script>
        </body>
        </html>
        '''
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def send_file_list(self):
        """发送文件列表"""
        try:
            # 获取所有.py, .md, .sh, .json, .txt文件
            files = []
            for root, dirs, filenames in os.walk(TRADING_SYSTEM_DIR):
                # 跳过一些目录
                if any(skip in root for skip in ['.git', 'node_modules', '__pycache__', '.venv', 'venv']):
                    continue
                    
                for filename in filenames:
                    if filename.endswith(('.py', '.md', '.sh', '.json', '.txt', '.js', '.jsx', '.html', '.css')):
                        rel_path = os.path.relpath(os.path.join(root, filename), TRADING_SYSTEM_DIR)
                        files.append(rel_path)
            
            files.sort()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(files[:100]).encode('utf-8'))  # 限制前100个文件
        except Exception as e:
            self.send_error(500, f"获取文件列表失败: {str(e)}")
    
    def send_file_content(self, file_path):
        """发送文件内容"""
        try:
            file_full_path = TRADING_SYSTEM_DIR / file_path
            
            if not file_full_path.exists():
                self.send_error(404, "文件不存在")
                return
            
            with open(file_full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'content': content,
                'filename': file_path
            }).encode('utf-8'))
        except Exception as e:
            self.send_error(500, f"读取文件失败: {str(e)}")
    
    def send_static_file(self):
        """发送静态文件（暂不支持）"""
        self.send_error(404, "静态文件服务未启用")
    
    def log_message(self, format, *args):
        """简化日志输出"""
        pass  # 静默日志

def main():
    """启动Web服务器"""
    port = 8080
    server_address = ('', port)
    
    print(f"🚀 启动交易系统Web代码编辑器...")
    print(f"📁 项目目录: {TRADING_SYSTEM_DIR}")
    print(f"🌐 访问地址: http://localhost:{port}")
    print(f"📝 支持编辑: .py, .md, .sh, .json, .js, .html, .css 等文件")
    print("🛑 按 Ctrl+C 停止服务器")
    
    httpd = HTTPServer(server_address, CodeEditorHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"❌ 服务器错误: {e}")

if __name__ == '__main__':
    main()