"""
技术指标计算模块

提供常用的技术分析指标计算功能
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """技术指标数据结构"""
    # 趋势指标
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    ema12: Optional[float] = None
    ema26: Optional[float] = None
    
    # 动量指标
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    stochastic_k: Optional[float] = None
    stochastic_d: Optional[float] = None
    
    # 波动指标
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    atr: Optional[float] = None
    
    # 成交量指标
    obv: Optional[float] = None
    volume_ma: Optional[float] = None
    
    # 趋势判断
    trend: str = "sideways"  # bullish, bearish, sideways
    trend_strength: float = 0.0  # 0-1


class TechnicalIndicatorCalculator:
    """技术指标计算器"""
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> Optional[float]:
        """计算简单移动平均线"""
        if len(prices) < period:
            return None
        return float(np.mean(prices[-period:]))
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """计算指数移动平均线"""
        if len(prices) < period:
            return None
        
        prices_array = np.array(prices)
        multiplier = 2.0 / (period + 1)
        ema = np.mean(prices_array[:period])
        
        for price in prices_array[period:]:
            ema = (price - ema) * multiplier + ema
        
        return float(ema)
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """计算相对强弱指数"""
        if len(prices) < period + 1:
            return None
        
        prices_array = np.array(prices)
        deltas = np.diff(prices_array)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return float(rsi)
    
    @staticmethod
    def calculate_macd(prices: List[float], 
                       fast_period: int = 12, 
                       slow_period: int = 26, 
                       signal_period: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """计算MACD指标"""
        if len(prices) < slow_period + signal_period:
            return None, None, None
        
        ema_fast = TechnicalIndicatorCalculator.calculate_ema(prices, fast_period)
        ema_slow = TechnicalIndicatorCalculator.calculate_ema(prices, slow_period)
        
        if ema_fast is None or ema_slow is None:
            return None, None, None
        
        macd = ema_fast - ema_slow
        
        # 计算MACD的EMA作为信号线
        macd_values = []
        for i in range(slow_period, len(prices) + 1):
            ema_f = TechnicalIndicatorCalculator.calculate_ema(prices[:i], fast_period)
            ema_s = TechnicalIndicatorCalculator.calculate_ema(prices[:i], slow_period)
            if ema_f and ema_s:
                macd_values.append(ema_f - ema_s)
        
        if len(macd_values) < signal_period:
            return macd, None, None
        
        signal = TechnicalIndicatorCalculator.calculate_ema(macd_values, signal_period)
        histogram = macd - signal if signal else None
        
        return macd, signal, histogram
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], 
                                   period: int = 20, 
                                   std_dev: float = 2.0) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """计算布林带"""
        if len(prices) < period:
            return None, None, None
        
        prices_array = np.array(prices[-period:])
        middle = float(np.mean(prices_array))
        std = float(np.std(prices_array))
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper, middle, lower
    
    @staticmethod
    def calculate_atr(highs: List[float], 
                      lows: List[float], 
                      closes: List[float], 
                      period: int = 14) -> Optional[float]:
        """计算平均真实波幅"""
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        if len(true_ranges) < period:
            return None
        
        return float(np.mean(true_ranges[-period:]))
    
    @staticmethod
    def calculate_stochastic(highs: List[float], 
                             lows: List[float], 
                             closes: List[float], 
                             k_period: int = 14, 
                             d_period: int = 3) -> Tuple[Optional[float], Optional[float]]:
        """计算随机指标"""
        if len(highs) < k_period or len(lows) < k_period or len(closes) < k_period:
            return None, None
        
        k_values = []
        for i in range(k_period - 1, len(closes)):
            high_max = max(highs[i - k_period + 1:i + 1])
            low_min = min(lows[i - k_period + 1:i + 1])
            close = closes[i]
            
            if high_max == low_min:
                k_values.append(50.0)
            else:
                k = ((close - low_min) / (high_max - low_min)) * 100
                k_values.append(k)
        
        if len(k_values) < d_period:
            return k_values[-1] if k_values else None, None
        
        k = k_values[-1]
        d = float(np.mean(k_values[-d_period:]))
        
        return k, d
    
    @staticmethod
    def calculate_obv(closes: List[float], volumes: List[float]) -> Optional[float]:
        """计算能量潮指标"""
        if len(closes) < 2 or len(volumes) < 2:
            return None
        
        obv = 0.0
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1]:
                obv += volumes[i]
            elif closes[i] < closes[i - 1]:
                obv -= volumes[i]
        
        return obv
    
    @staticmethod
    def calculate_volume_ma(volumes: List[float], period: int = 20) -> Optional[float]:
        """计算成交量移动平均"""
        if len(volumes) < period:
            return None
        return float(np.mean(volumes[-period:]))
    
    @staticmethod
    def determine_trend(ma5: Optional[float], 
                        ma20: Optional[float], 
                        ma50: Optional[float],
                        rsi: Optional[float],
                        macd: Optional[float],
                        macd_signal: Optional[float]) -> Tuple[str, float]:
        """判断趋势方向和强度"""
        bullish_signals = 0
        bearish_signals = 0
        total_signals = 0
        
        # MA趋势判断
        if ma5 and ma20:
            total_signals += 1
            if ma5 > ma20:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if ma20 and ma50:
            total_signals += 1
            if ma20 > ma50:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # RSI判断
        if rsi:
            total_signals += 1
            if rsi > 60:
                bullish_signals += 1
            elif rsi < 40:
                bearish_signals += 1
        
        # MACD判断
        if macd and macd_signal:
            total_signals += 1
            if macd > macd_signal:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if total_signals == 0:
            return "sideways", 0.0
        
        bullish_ratio = bullish_signals / total_signals
        bearish_ratio = bearish_signals / total_signals
        
        if bullish_ratio > 0.6:
            return "bullish", bullish_ratio
        elif bearish_ratio > 0.6:
            return "bearish", bearish_ratio
        else:
            return "sideways", max(bullish_ratio, bearish_ratio)
    
    @classmethod
    def calculate_all_indicators(cls, 
                                  klines: List[Dict[str, float]]) -> TechnicalIndicators:
        """计算所有技术指标"""
        if not klines or len(klines) < 50:
            logger.warning("K线数据不足，无法计算技术指标")
            return TechnicalIndicators()
        
        try:
            # 提取价格数据
            closes = [k.get('close', 0) for k in klines]
            highs = [k.get('high', 0) for k in klines]
            lows = [k.get('low', 0) for k in klines]
            volumes = [k.get('volume', 0) for k in klines]
            
            # 计算趋势指标
            ma5 = cls.calculate_sma(closes, 5)
            ma10 = cls.calculate_sma(closes, 10)
            ma20 = cls.calculate_sma(closes, 20)
            ma50 = cls.calculate_sma(closes, 50)
            ema12 = cls.calculate_ema(closes, 12)
            ema26 = cls.calculate_ema(closes, 26)
            
            # 计算动量指标
            rsi = cls.calculate_rsi(closes, 14)
            macd, macd_signal, macd_histogram = cls.calculate_macd(closes)
            stoch_k, stoch_d = cls.calculate_stochastic(highs, lows, closes)
            
            # 计算波动指标
            bb_upper, bb_middle, bb_lower = cls.calculate_bollinger_bands(closes)
            atr = cls.calculate_atr(highs, lows, closes)
            
            # 计算成交量指标
            obv = cls.calculate_obv(closes, volumes)
            volume_ma = cls.calculate_volume_ma(volumes)
            
            # 判断趋势
            trend, strength = cls.determine_trend(
                ma5, ma20, ma50, rsi, macd, macd_signal
            )
            
            return TechnicalIndicators(
                ma5=ma5,
                ma10=ma10,
                ma20=ma20,
                ma50=ma50,
                ema12=ema12,
                ema26=ema26,
                rsi=rsi,
                macd=macd,
                macd_signal=macd_signal,
                macd_histogram=macd_histogram,
                stochastic_k=stoch_k,
                stochastic_d=stoch_d,
                bollinger_upper=bb_upper,
                bollinger_middle=bb_middle,
                bollinger_lower=bb_lower,
                atr=atr,
                obv=obv,
                volume_ma=volume_ma,
                trend=trend,
                trend_strength=strength
            )
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return TechnicalIndicators()
    
    @classmethod
    def indicators_to_dict(cls, indicators: TechnicalIndicators) -> Dict[str, any]:
        """将技术指标转换为字典"""
        return {
            "trend": {
                "direction": indicators.trend,
                "strength": indicators.trend_strength,
                "ma5": indicators.ma5,
                "ma10": indicators.ma10,
                "ma20": indicators.ma20,
                "ma50": indicators.ma50,
                "ema12": indicators.ema12,
                "ema26": indicators.ema26
            },
            "momentum": {
                "rsi": indicators.rsi,
                "macd": indicators.macd,
                "macd_signal": indicators.macd_signal,
                "macd_histogram": indicators.macd_histogram,
                "stochastic_k": indicators.stochastic_k,
                "stochastic_d": indicators.stochastic_d
            },
            "volatility": {
                "bollinger_upper": indicators.bollinger_upper,
                "bollinger_middle": indicators.bollinger_middle,
                "bollinger_lower": indicators.bollinger_lower,
                "atr": indicators.atr
            },
            "volume": {
                "obv": indicators.obv,
                "volume_ma": indicators.volume_ma
            }
        }
