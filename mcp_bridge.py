#!/usr/bin/env python3
"""
简单的MCP桥接服务器
用于连接OpenClaw和Trae IDE
"""

import asyncio
import json
import sys
import os
from pathlib import Path

class MCPServer:
    """简单的MCP服务器实现"""
    
    def __init__(self, project_dir):
        self.project_dir = Path(project_dir)
        self.tools = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "execute_command": self.execute_command,
            "run_test": self.run_test,
            "analyze_code": self.analyze_code,
            "check_dependencies": self.check_dependencies
        }
    
    async def read_file(self, params):
        """读取文件内容"""
        file_path = self.project_dir / params.get("path", "")
        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        
        try:
            content = file_path.read_text(encoding='utf-8')
            return {
                "success": True,
                "content": content,
                "path": str(file_path)
            }
        except Exception as e:
            return {"error": f"读取文件失败: {str(e)}"}
    
    async def write_file(self, params):
        """写入文件内容"""
        file_path = self.project_dir / params.get("path", "")
        content = params.get("content", "")
        
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            file_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "message": f"文件已保存: {file_path}",
                "path": str(file_path)
            }
        except Exception as e:
            return {"error": f"写入文件失败: {str(e)}"}
    
    async def execute_command(self, params):
        """执行命令"""
        command = params.get("command", "")
        if not command:
            return {"error": "命令不能为空"}
        
        try:
            import subprocess
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {"error": "命令执行超时"}
        except Exception as e:
            return {"error": f"命令执行失败: {str(e)}"}
    
    async def run_test(self, params):
        """运行测试"""
        test_path = params.get("path", "tests/")
        
        command = f"cd {self.project_dir} && python3 -m pytest {test_path} -v"
        return await self.execute_command({"command": command})
    
    async def analyze_code(self, params):
        """分析代码"""
        file_path = params.get("path", "")
        if file_path:
            full_path = self.project_dir / file_path
            if full_path.exists():
                # 简单的代码分析
                content = full_path.read_text(encoding='utf-8')
                lines = content.split('\n')
                
                return {
                    "success": True,
                    "analysis": {
                        "file_path": str(full_path),
                        "line_count": len(lines),
                        "has_imports": any(line.strip().startswith('import') or line.strip().startswith('from') for line in lines),
                        "has_functions": any('def ' in line for line in lines),
                        "has_classes": any('class ' in line for line in lines)
                    }
                }
        
        # 如果没有指定文件，分析整个项目
        py_files = list(self.project_dir.rglob("*.py"))
        
        return {
            "success": True,
            "analysis": {
                "total_py_files": len(py_files),
                "project_size_mb": sum(f.stat().st_size for f in py_files) / 1024 / 1024,
                "sample_files": [str(f.relative_to(self.project_dir)) for f in py_files[:10]]
            }
        }
    
    async def check_dependencies(self, params):
        """检查依赖"""
        requirements_file = self.project_dir / "requirements.txt"
        if not requirements_file.exists():
            return {"error": "requirements.txt 文件不存在"}
        
        try:
            import subprocess
            # 检查已安装的包
            result = subprocess.run(
                ["pip", "list", "--format=json"],
                capture_output=True,
                text=True
            )
            
            installed_packages = json.loads(result.stdout) if result.stdout else []
            installed_dict = {pkg["name"].lower(): pkg for pkg in installed_packages}
            
            # 读取requirements.txt
            requirements = []
            with open(requirements_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # 简单解析包名
                        pkg_name = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                        requirements.append({
                            "requirement": line,
                            "name": pkg_name.lower(),
                            "installed": pkg_name.lower() in installed_dict,
                            "version": installed_dict.get(pkg_name.lower(), {}).get("version", "未安装")
                        })
            
            return {
                "success": True,
                "requirements": requirements,
                "total": len(requirements),
                "installed": sum(1 for r in requirements if r["installed"]),
                "missing": sum(1 for r in requirements if not r["installed"])
            }
        except Exception as e:
            return {"error": f"检查依赖失败: {str(e)}"}
    
    async def handle_request(self, request_data):
        """处理MCP请求"""
        try:
            request = json.loads(request_data)
            method = request.get("method")
            params = request.get("params", {})
            
            # 处理MCP标准方法
            if method == "initialize":
                # MCP初始化请求
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "OpenClaw Trading MCP Server",
                            "version": "1.0.0"
                        },
                        "capabilities": {
                            "tools": {
                                "listChanged": True
                            }
                        }
                    }
                })
            
            elif method == "tools/list":
                # 返回可用工具列表
                tools = []
                for tool_name, tool_func in self.tools.items():
                    tools.append({
                        "name": tool_name,
                        "description": self.get_tool_description(tool_name),
                        "inputSchema": self.get_tool_schema(tool_name)
                    })
                
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "tools": tools
                    }
                })
            
            elif method == "tools/call":
                # 调用工具
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                if tool_name in self.tools:
                    result = await self.tools[tool_name](arguments)
                    return json.dumps({
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result, ensure_ascii=False, indent=2)
                                }
                            ]
                        }
                    })
                else:
                    return json.dumps({
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {
                            "code": -32601,
                            "message": f"工具不存在: {tool_name}"
                        }
                    })
            
            elif method == "notifications/initialized":
                # 通知服务器已初始化
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {}
                })
            
            elif method == "shutdown":
                # 关闭服务器
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {}
                })
            
            elif method in self.tools:
                # 向后兼容：直接调用工具
                result = await self.tools[method](params)
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": result
                })
            else:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"方法不存在: {method}"
                    }
                })
        except json.JSONDecodeError:
            return json.dumps({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": "JSON解析错误"
                }
            })
        except Exception as e:
            return json.dumps({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"服务器错误: {str(e)}"
                }
            })
    
    def get_tool_description(self, tool_name):
        """获取工具描述"""
        descriptions = {
            "read_file": "读取文件内容",
            "write_file": "写入文件内容",
            "execute_command": "执行Shell命令",
            "run_test": "运行测试套件",
            "analyze_code": "分析代码结构",
            "check_dependencies": "检查Python依赖"
        }
        return descriptions.get(tool_name, f"执行 {tool_name} 操作")
    
    def get_tool_schema(self, tool_name):
        """获取工具输入模式"""
        schemas = {
            "read_file": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件相对路径"
                    }
                },
                "required": ["path"]
            },
            "write_file": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件相对路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容"
                    }
                },
                "required": ["path", "content"]
            },
            "execute_command": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的Shell命令"
                    }
                },
                "required": ["command"]
            },
            "run_test": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "测试路径（默认为tests/）"
                    }
                },
                "required": []
            },
            "analyze_code": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录路径"
                    }
                },
                "required": []
            },
            "check_dependencies": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        return schemas.get(tool_name, {
            "type": "object",
            "properties": {},
            "required": []
        })
    
    async def run_stdio(self):
        """通过标准输入输出运行MCP服务器"""
        print("🚀 MCP桥接服务器启动", file=sys.stderr)
        print(f"📁 项目目录: {self.project_dir}", file=sys.stderr)
        print("🛠️ 可用工具: " + ", ".join(self.tools.keys()), file=sys.stderr)
        print("⏳ 等待请求...", file=sys.stderr)
        
        while True:
            try:
                # 读取标准输入
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                
                # 处理请求
                response = await self.handle_request(line.strip())
                
                # 写入标准输出
                print(response, flush=True)
                
            except Exception as e:
                print(f"❌ 处理请求失败: {e}", file=sys.stderr)

async def main():
    """主函数"""
    # 使用交易系统项目目录
    project_dir = Path("/home/cool/.openclaw-trading")
    
    if not project_dir.exists():
        print(f"❌ 项目目录不存在: {project_dir}", file=sys.stderr)
        sys.exit(1)
    
    server = MCPServer(project_dir)
    await server.run_stdio()

if __name__ == "__main__":
    asyncio.run(main())