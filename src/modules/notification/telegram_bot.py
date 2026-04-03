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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, Awaitable

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
    parse_mode: str = "Markdown"
    reply_to_message_id: Optional[int] = None
    disable_web_page_preview: bool = True


class TelegramBot:
    """Telegram机器人 - 纯自然语言交互，无固定命令"""

    def __init__(self, config: Dict[str, Any], nli=None, llm_integration=None, main_controller=None):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.bot_token = config.get("bot_token", "")
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
        
        logger.info("Telegram机器人初始化完成 - 纯自然语言模式")

    async def initialize(self):
        """初始化"""
        if not self.enabled:
            logger.info("Telegram机器人未启用")
            return
        
        proxy = self.config.get("proxy") or "http://127.0.0.1:7890"
        
        self.session = aiohttp.ClientSession()
        
        me = await self._get_me()
        if me:
            logger.info(f"✅ Telegram机器人已连接: @{me.get('username', 'unknown')}")
        else:
            logger.warning("⚠️ Telegram机器人连接失败")

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

    async def _get_me(self) -> Optional[Dict]:
        """获取机器人信息"""
        try:
            url = f"{self.base_url}/getMe"
            proxy = "http://127.0.0.1:7890"
            async with self.session.get(url, proxy=proxy) as resp:
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
            
            proxy = "http://127.0.0.1:7890"
            async with self.session.get(url, params=params, proxy=proxy) as resp:
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
        """处理自然语言消息 - AI自由理解，无固定模式"""
        try:
            ai_executor = getattr(self.main_controller, 'ai_command_executor', None) if self.main_controller else None
            
            if ai_executor:
                result = await ai_executor.process_input(message.text)
                
                response_text = result.get("response", "处理完成")
                
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text=response_text,
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id
                ))
            elif self.llm_integration:
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
                        parse_mode="Markdown",
                        reply_to_message_id=message.message_id
                    ))
                else:
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text="抱歉，我现在无法处理您的请求，请稍后再试。",
                        parse_mode="Markdown",
                        reply_to_message_id=message.message_id
                    ))
            else:
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text="您好！我是OpenClaw交易系统的AI助手。\n\n请直接用自然语言告诉我您想做什么，我会尽力帮助您。\n\n例如：\n• 帮我看看账户余额\n• 分析一下BTC市场\n• 开多BTC 0.01\n• 现在有什么交易机会？",
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id
                ))
                
        except Exception as e:
            logger.error(f"处理自然语言失败: {e}")
            await self._send_message(TelegramResponse(
                chat_id=message.chat_id,
                text=f"处理消息时出错: {str(e)}",
                parse_mode="Markdown"
            ))

    async def _get_system_context(self) -> str:
        """获取系统上下文"""
        context_parts = [
            "系统状态:",
            "- 模式: 实盘交易",
            "- 交易类型: 永续合约",
            "- 杠杆: 10-50倍",
            "- 黑名单: ETH/USDT"
        ]
        
        if self.main_controller:
            mc = self.main_controller
            
            if hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine:
                engine = mc.ai_trading_engine
                positions = getattr(engine, 'positions', {})
                context_parts.append(f"- 当前持仓: {len(positions)}个")
            
            if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                context_parts.append("- 交易所: OKX (已连接)")
        
        return "\n".join(context_parts)

    async def _send_message(self, response: TelegramResponse):
        """发送消息"""
        try:
            url = f"{self.base_url}/sendMessage"
            
            payload = {
                "chat_id": response.chat_id,
                "text": response.text,
                "parse_mode": response.parse_mode,
                "disable_web_page_preview": response.disable_web_page_preview
            }
            
            if response.reply_to_message_id:
                payload["reply_to_message_id"] = response.reply_to_message_id
            
            proxy = "http://127.0.0.1:7890"
            async with self.session.post(url, json=payload, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        logger.debug(f"消息已发送")
                    else:
                        logger.error(f"发送消息失败: {data}")
                else:
                    logger.error(f"发送消息失败: {resp.status}")
        except Exception as e:
            logger.error(f"发送消息失败: {e}")

    async def send_alert(self, chat_id: int, title: str, message: str, level: str = "warning"):
        """发送警报消息"""
        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
            "error": "❌"
        }
        
        text = f"{emoji.get(level, 'ℹ️')} *{title}*\n\n{message}"
        
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        ))

    async def send_notification(self, chat_id: int, message: str):
        """发送通知消息"""
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        ))

    async def send_trade_notification(self, chat_id: int, trade_info: Dict[str, Any]):
        """发送交易通知"""
        action = trade_info.get("action", "unknown")
        symbol = trade_info.get("symbol", "unknown")
        quantity = trade_info.get("quantity", 0)
        price = trade_info.get("price", 0)
        
        text = f"📢 *交易执行*\n\n"
        text += f"操作: {action.upper()}\n"
        text += f"交易对: {symbol}\n"
        text += f"数量: {quantity}\n"
        text += f"价格: {price}\n"
        
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        ))

    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()
        logger.info("Telegram机器人已清理")

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown"):
        """发送消息的便捷方法"""
        await self._send_message(TelegramResponse(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode
        ))
    
    def add_message_handler(self, handler: Callable[[TelegramMessage], Awaitable[None]]):
        """添加消息处理器"""
        self.message_handlers.append(handler)
