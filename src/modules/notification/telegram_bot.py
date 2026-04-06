"""
Telegram机器人模块 - 纯自然语言交互

功能：
1. 接收用户消息
2. 发送交易通知和警报
3. 完全自然语言交互，无固定命令
4. AI自由理解用户意图
"""

import asyncio
import logging
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, Awaitable
from urllib.parse import urlparse, urlunparse

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    """Telegram消息"""
    chat_id: int
    message_id: int
    from_user: Optional[str]
    text: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TelegramResponse:
    """Telegram响应"""
    chat_id: int
    text: str
    parse_mode: Optional[str] = None  # 默认不使用Markdown，避免解析错误
    reply_to_message_id: Optional[int] = None
    disable_web_page_preview: bool = True


class TelegramBot:
    """Telegram机器人 - 纯自然语言交互，无固定命令"""

    def __init__(self, config: Dict[str, Any], nli=None, llm_integration=None, main_controller=None):
        self.config = config
        self.enabled = config.get("enabled", False)
        
        # 支持从环境变量读取
        if config.get("bot_token_env"):
            self.bot_token = os.environ.get(config["bot_token_env"], "")
        else:
            self.bot_token = config.get("bot_token", "")
        
        if config.get("chat_ids_env"):
            chat_id_str = os.environ.get(config["chat_ids_env"], "")
            logger.info(f"📱 从环境变量 {config['chat_ids_env']} 读取 chat_ids: {chat_id_str}")
            self.chat_ids = [int(x.strip()) for x in chat_id_str.split(",") if x.strip()]
        else:
            self.chat_ids = config.get("chat_ids", [])
        
        self.nli = nli
        self.llm_integration = llm_integration
        self.main_controller = main_controller
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = None
        self._running = False
        self._polling_task = None
        self._last_update_id = 0
        
        self.message_handlers: List[Callable] = []
        
        logger.info(f"Telegram机器人初始化完成 - enabled={self.enabled}, chat_ids={self.chat_ids}")

    async def initialize(self):
        """初始化"""
        if not self.enabled:
            logger.info("Telegram机器人未启用")
            return
        
        self.proxy = self.config.get("proxy") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "http://host.docker.internal:7890"
        self.proxy = self._normalize_proxy_for_runtime(self.proxy)
        logger.info(f"📱 Telegram使用代理: {self.proxy}")
        
        self.session = aiohttp.ClientSession()
        
        me = await self._get_me()
        if me:
            logger.info(f"✅ Telegram机器人已连接: @{me.get('username', 'unknown')}")
        else:
            logger.warning("⚠️ Telegram机器人连接失败")

    def _normalize_proxy_for_runtime(self, proxy_url: Optional[str]) -> Optional[str]:
        """In Docker, rewrite loopback proxy URL to host gateway."""
        if not proxy_url:
            return proxy_url
        if not os.path.exists("/.dockerenv"):
            return proxy_url
        try:
            parsed = urlparse(proxy_url)
            host = (parsed.hostname or "").strip().lower()
            if host not in {"127.0.0.1", "localhost"}:
                return proxy_url
            netloc = parsed.netloc.replace(parsed.hostname or "", "host.docker.internal")
            return urlunparse(parsed._replace(netloc=netloc))
        except Exception:
            return proxy_url

    async def start(self):
        """启动轮询"""
        if not self.enabled:
            return
        
        self._running = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("✅ Telegram机器人轮询已启动")

    async def stop(self):
        """停止"""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram机器人已停止")
    
    async def shutdown(self):
        """关闭Telegram机器人"""
        await self.stop()
        await self.cleanup()
        logger.info("Telegram机器人已关闭")

    async def _get_me(self) -> Optional[Dict]:
        """获取机器人信息"""
        try:
            url = f"{self.base_url}/getMe"
            async with self.session.get(url, proxy=self.proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        return data.get("result")
        except Exception as e:
            logger.error(f"获取机器人信息失败: {e}")
        return None

    async def _polling_loop(self):
        """轮询循环"""
        while self._running:
            try:
                await self._poll_updates()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"轮询错误: {e}")
                await asyncio.sleep(5)

    async def _poll_updates(self):
        """轮询更新"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self._last_update_id + 1,
                "timeout": 30
            }
            
            async with self.session.get(url, params=params, proxy=self.proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            self._last_update_id = update.get("update_id", 0)
                            if "message" in update:
                                await self._process_message(update["message"])
        except Exception as e:
            logger.error(f"轮询更新失败: {e}")

    async def _process_message(self, message: Dict):
        """处理消息 - 纯自然语言，无固定命令"""
        try:
            chat_id = message["chat"]["id"]
            from_user = message.get("from", {}).get("username", str(chat_id))
            text = message.get("text", "")
            message_id = message.get("message_id", 0)
            
            if not text:
                return
            
            telegram_message = TelegramMessage(
                chat_id=chat_id,
                message_id=message_id,
                from_user=from_user,
                text=text,
                timestamp=datetime.now()
            )
            
            logger.info(f"📩 收到消息 [{from_user}]: {text[:50]}...")
            
            await self._process_natural_language(telegram_message)
            
            for handler in self.message_handlers:
                try:
                    await handler(telegram_message)
                except Exception as e:
                    logger.error(f"消息处理器错误: {e}")
                    
        except Exception as e:
            logger.error(f"处理消息失败: {e}")

    async def _process_natural_language(self, message: TelegramMessage):
        """处理自然语言消息 - 直接调用AI核心决策引擎"""
        try:
            logger.info(f"📩 收到消息 [{message.from_user}]: {message.text[:100] if len(message.text) > 100 else message.text}")

            if self.main_controller and hasattr(self.main_controller, "process_user_command"):
                logger.info(f"🤖 通过主控制器核心大脑路由处理: {message.text[:50]}")
                result = await self.main_controller.process_user_command(
                    message.text,
                    source="telegram",
                )
                response_text = (result or {}).get("response", "处理完成")
                success = (result or {}).get("success", False)
                logger.info(f"📤 AI响应: success={success}, response长度={len(response_text)}")
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text=response_text,
                    reply_to_message_id=message.message_id
                ))
            elif self.llm_integration:
                logger.info(f"Telegram使用llm_integration处理消息")
                system_context = await self._get_system_context()
                
                prompt = f"""你是一个全自主的量化交易AI助手。用户通过Telegram与你交流。

{system_context}

用户消息: {message.text}

请自由理解用户意图并执行相应操作。你可以：
1. 回答用户问题
2. 执行交易操作（开仓、平仓、查询等）
3. 分析市场
4. 开发或优化策略
5. 调整系统配置
6. 任何用户需要的操作

你有完全的自主权，根据用户意图和市场情况做出最佳决策。
请用中文回复，保持简洁专业。"""

                response = await self.llm_integration.generate(prompt)
                
                if response and response.success:
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text=response.content,
                        reply_to_message_id=message.message_id
                    ))
                else:
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text="抱歉，我现在无法处理您的请求，请稍后再试。",
                        reply_to_message_id=message.message_id
                    ))
            else:
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text="您好！我是OpenClaw交易系统的AI助手。\n\n请直接用自然语言告诉我您想做什么，我会尽力帮助您。\n\n例如：\n• 帮我看看账户余额\n• 分析一下BTC市场\n• 开多BTC 0.01\n• 现在有什么交易机会？",
                    reply_to_message_id=message.message_id
                ))
                
        except Exception as e:
            logger.error(f"处理自然语言失败: {e}")
            await self._send_message(TelegramResponse(
                chat_id=message.chat_id,
                text=f"处理消息时出错: {str(e)}"
            ))

    async def _get_system_context(self) -> str:
        """获取系统上下文 - 包含实时持仓信息"""
        context_parts = [
            "系统状态:",
            "- 模式: 实盘交易",
            "- 交易类型: 永续合约",
            "- 杠杆: 10-50倍",
            "- 黑名单: 无"
        ]
        
        if self.main_controller:
            mc = self.main_controller
            
            # 获取实时持仓
            if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                context_parts.append("- 交易所: OKX (已连接)")
                try:
                    positions = await mc.okx_exchange.get_positions()
                    active_pos = [p for p in positions if float(p.get('size', 0) or 0) != 0]
                    if active_pos:
                        pos_info = []
                        for p in active_pos[:5]:
                            symbol = p.get('symbol', '')
                            side = p.get('side', '')
                            size = p.get('size', 0)
                            pnl = float(p.get('unrealized_pnl', 0) or 0)
                            pos_info.append(f"  {symbol}: {side} {size} | 盈亏: ${pnl:+.2f}")
                        context_parts.append(f"- 当前持仓 ({len(active_pos)}个):\n" + "\n".join(pos_info))
                    else:
                        context_parts.append("- 当前持仓: 无")
                except Exception as e:
                    context_parts.append(f"- 当前持仓: 获取失败 ({e})")
            
            # 获取账户余额
            if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                try:
                    balance = await mc.okx_exchange.get_balance()
                    usdt = balance.get('USDT', {})
                    if isinstance(usdt, dict):
                        available = usdt.get('free', 0)
                    else:
                        available = usdt
                    context_parts.append(f"- 可用余额: {available:.2f} USDT")
                except:
                    pass
        
        return "\n".join(context_parts)

    async def _send_message(self, response: TelegramResponse):
        """发送消息 - 智能消息分割和去重"""
        try:
            text = response.text
            
            # Telegram消息长度限制为4096字符
            max_length = 4000
            
            # 如果消息很短，直接发送
            if len(text) <= max_length:
                await self._send_single_message(response)
                return
            
            # 智能分割长消息
            messages = self._smart_split_message(text, max_length)
            
            # 发送分割后的消息
            for i, msg in enumerate(messages):
                await self._send_single_message(TelegramResponse(
                    chat_id=response.chat_id,
                    text=msg,
                    parse_mode=response.parse_mode,
                    disable_web_page_preview=response.disable_web_page_preview,
                    reply_to_message_id=response.reply_to_message_id if i == 0 else None
                ))
                
                # 消息之间稍微延迟，避免频率限制
                if i < len(messages) - 1:
                    await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
    
    def _smart_split_message(self, text: str, max_length: int) -> List[str]:
        """
        智能分割消息 - 保持内容完整性
        
        优先级：
        1. 按段落分割（双换行）
        2. 按单行分割
        3. 强制分割（最后手段）
        """
        messages = []
        
        # 如果消息不太长，直接返回
        if len(text) <= max_length:
            return [text]
        
        # 1. 尝试按段落分割
        paragraphs = text.split('\n\n')
        if len(paragraphs) > 1:
            current_msg = ""
            for para in paragraphs:
                # 如果单个段落就超长，需要进一步分割
                if len(para) > max_length:
                    # 先保存当前消息
                    if current_msg:
                        messages.append(current_msg.strip())
                        current_msg = ""
                    
                    # 分割超长段落
                    para_messages = self._split_long_paragraph(para, max_length)
                    messages.extend(para_messages)
                # 如果加上这个段落不超长
                elif len(current_msg) + len(para) + 2 <= max_length:
                    current_msg += para + "\n\n"
                # 否则保存当前消息，开始新消息
                else:
                    if current_msg:
                        messages.append(current_msg.strip())
                    current_msg = para + "\n\n"
            
            if current_msg:
                messages.append(current_msg.strip())
        
        # 2. 如果段落分割失败，按行分割
        else:
            messages = self._split_by_lines(text, max_length)
        
        # 过滤空消息
        messages = [msg for msg in messages if msg.strip()]
        
        # 如果还是失败，强制分割
        if not messages:
            messages = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        
        return messages
    
    def _split_long_paragraph(self, para: str, max_length: int) -> List[str]:
        """分割超长段落"""
        messages = []
        lines = para.split('\n')
        current_msg = ""
        
        for line in lines:
            if len(current_msg) + len(line) + 1 <= max_length:
                current_msg += line + "\n"
            else:
                if current_msg:
                    messages.append(current_msg.strip())
                current_msg = line + "\n"
        
        if current_msg:
            messages.append(current_msg.strip())
        
        return messages
    
    def _split_by_lines(self, text: str, max_length: int) -> List[str]:
        """按行分割消息"""
        messages = []
        lines = text.split('\n')
        current_msg = ""
        
        for line in lines:
            if len(current_msg) + len(line) + 1 <= max_length:
                current_msg += line + "\n"
            else:
                if current_msg:
                    messages.append(current_msg.strip())
                current_msg = line + "\n"
        
        if current_msg:
            messages.append(current_msg.strip())
        
        return messages
    
    async def _send_single_message(self, response: TelegramResponse):
        """发送单条消息"""
        try:
            url = f"{self.base_url}/sendMessage"
            
            payload = {
                "chat_id": response.chat_id,
                "text": response.text,
                "disable_web_page_preview": True
            }
            
            # 不使用parse_mode，避免Markdown解析错误
            
            if response.reply_to_message_id:
                payload["reply_to_message_id"] = response.reply_to_message_id
            
            async with self.session.post(url, json=payload, proxy=self.proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        logger.info(f"✅ 消息已发送")
                    else:
                        logger.error(f"发送消息失败: {data}")
                else:
                    error_text = await resp.text()
                    logger.error(f"发送消息失败: {resp.status} - {error_text}")
        except Exception as e:
            logger.error(f"发送单条消息失败: {e}")

    async def send_alert(self, chat_id: int, title: str, message: str, level: str = "warning"):
        """发送警报消息"""
        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
            "error": "❌"
        }
        
        text = f"{emoji.get(level, 'ℹ️')} {title}\n\n{message}"
        
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=text
        ))

    async def send_notification(self, chat_id: int, message: str):
        """发送通知消息"""
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=message
        ))

    async def send_trade_notification(self, chat_id: int, trade_info: Dict[str, Any]):
        """发送交易通知"""
        action = trade_info.get("action", "unknown")
        symbol = trade_info.get("symbol", "unknown")
        quantity = trade_info.get("quantity", 0)
        price = trade_info.get("price", 0)
        
        text = f"📢 交易执行\n\n"
        text += f"操作: {action.upper()}\n"
        text += f"交易对: {symbol}\n"
        text += f"数量: {quantity}\n"
        text += f"价格: {price}\n"
        
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=text
        ))

    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()
        logger.info("Telegram机器人已清理")

    async def send_message(self, chat_id: Any, text: Optional[str] = None, parse_mode: str = None):
        """发送消息的便捷方法。

        兼容两种调用方式：
        1) send_message(chat_id, text, parse_mode)
        2) send_message(text)  # 自动发送到第一个配置的 chat_id
        """
        resolved_chat_id: Optional[int] = None
        resolved_text: Optional[str] = text

        if text is None:
            # Compatibility mode: first arg is text
            resolved_text = str(chat_id) if chat_id is not None else ""
            if self.chat_ids:
                resolved_chat_id = int(self.chat_ids[0])
        else:
            try:
                resolved_chat_id = int(chat_id)
            except (TypeError, ValueError):
                resolved_chat_id = int(self.chat_ids[0]) if self.chat_ids else None

        if resolved_chat_id is None:
            raise ValueError("No chat_id available for Telegram message delivery")
        if not resolved_text:
            return

        await self._send_message(TelegramResponse(
            chat_id=resolved_chat_id,
            text=resolved_text,
            parse_mode=parse_mode
        ))
    
    def add_message_handler(self, handler: Callable[[TelegramMessage], Awaitable[None]]):
        """添加消息处理器"""
        self.message_handlers.append(handler)
