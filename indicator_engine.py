# indicator_engine.py - 기술적 지표 계산 엔진
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import talib
from abc import ABC, abstractmethod

@dataclass
class IndicatorResult:
    """지표 계산 결과"""
    name: str
    value: float
    signal: str  # 'BUY', 'SELL', 'NEUTRAL'
    strength: float  # 0-1 사이의 강도
    timeframe: str
    timestamp: int
    
class BaseIndicator(ABC):
    """기본 지표 클래스"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @abstractmethod
    async def calculate(self, df: pd.DataFrame, **kwargs) -> IndicatorResult:
        """지표 계산 (각 지표별로 구현)"""
        pass
    
    def _get_signal_strength(self, value: float, thresholds: Dict[str, float]) -> Tuple[str, float]:
        """신호와 강도 계산"""
        if value >= thresholds.get('strong_buy', 80):
            return 'BUY', 1.0
        elif value >= thresholds.get('buy', 60):
            return 'BUY', 0.7
        elif value <= thresholds.get('strong_sell', 20):
            return 'SELL', 1.0
        elif value <= thresholds.get('sell', 40):
            return 'SELL', 0.7
        else:
            return 'NEUTRAL', 0.1

class RSIIndicator(BaseIndicator):
    """RSI 지표"""
    
    def __init__(self, period: int = 14):
        super().__init__(f"RSI_{period}")
        self.period = period
    
    async def calculate(self, df: pd.DataFrame, **kwargs) -> IndicatorResult:
        if len(df) < self.period:
            return IndicatorResult(
                name=self.name,
                value=50.0,
                signal='NEUTRAL',
                strength=0.0,
                timeframe=kwargs.get('timeframe', '1'),
                timestamp=int(df.iloc[-1]['timestamp']) if not df.empty else 0
            )
        
        rsi_values = talib.RSI(df['close'].values, timeperiod=self.period)
        current_rsi = rsi_values[-1]
        
        # RSI 기반 신호 생성
        thresholds = {
            'strong_buy': 25,    # 과매도 강한 매수
            'buy': 35,           # 과매도 매수
            'sell': 65,          # 과매수 매도
            'strong_sell': 75    # 과매수 강한 매도
        }
        
        if current_rsi <= 30:
            signal, strength = 'BUY', min(1.0, (30 - current_rsi) / 10)
        elif current_rsi >= 70:
            signal, strength = 'SELL', min(1.0, (current_rsi - 70) / 10)
        else:
            signal, strength = 'NEUTRAL', 0.1
        
        return IndicatorResult(
            name=self.name,
            value=current_rsi,
            signal=signal,
            strength=strength,
            timeframe=kwargs.get('timeframe', '1'),
            timestamp=int(df.iloc[-1]['timestamp'])
        )

class MACDIndicator(BaseIndicator):
    """MACD 지표"""
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(f"MACD_{fast}_{slow}_{signal}")
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
    
    async def calculate(self, df: pd.DataFrame, **kwargs) -> IndicatorResult:
        min_periods = max(self.slow, self.signal_period) + 10
        
        if len(df) < min_periods:
            return IndicatorResult(
                name=self.name,
                value=0.0,
                signal='NEUTRAL',
                strength=0.0,
                timeframe=kwargs.get('timeframe', '1'),
                timestamp=int(df.iloc[-1]['timestamp']) if not df.empty else 0
            )
        
        macd, signal, histogram = talib.MACD(
            df['close'].values,
            fastperiod=self.fast,
            slowperiod=self.slow,
            signalperiod=self.signal_period
        )
        
        current_macd = macd[-1]
        current_signal = signal[-1]
        current_histogram = histogram[-1]
        prev_histogram = histogram[-2] if len(histogram) > 1 else 0
        
        # MACD 크로스오버 및 히스토그램 기반 신호
        if current_macd > current_signal and prev_histogram <= 0 < current_histogram:
            signal_type, strength = 'BUY', 0.8
        elif current_macd < current_signal and prev_histogram >= 0 > current_histogram:
            signal_type, strength = 'SELL', 0.8
        elif current_histogram > 0 and current_histogram > prev_histogram:
            signal_type, strength = 'BUY', 0.5
        elif current_histogram < 0 and current_histogram < prev_histogram:
            signal_type, strength = 'SELL', 0.5
        else:
            signal_type, strength = 'NEUTRAL', 0.1
        
        return IndicatorResult(
            name=self.name,
            value=current_histogram,
            signal=signal_type,
            strength=strength,
            timeframe=kwargs.get('timeframe', '1'),
            timestamp=int(df.iloc[-1]['timestamp'])
        )

class BollingerBandsIndicator(BaseIndicator):
    """볼린저 밴드 지표"""
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__(f"BB_{period}_{std_dev}")
        self.period = period
        self.std_dev = std_dev
    
    async def calculate(self, df: pd.DataFrame, **kwargs) -> IndicatorResult:
        if len(df) < self.period:
            return IndicatorResult(
                name=self.name,
                value=50.0,
                signal='NEUTRAL',
                strength=0.0,
                timeframe=kwargs.get('timeframe', '1'),
                timestamp=int(df.iloc[-1]['timestamp']) if not df.empty else 0
            )
        
        upper, middle, lower = talib.BBANDS(
            df['close'].values,
            timeperiod=self.period,
            nbdevup=self.std_dev,
            nbdevdn=self.std_dev
        )
        
        current_price = df.iloc[-1]['close']
        current_upper = upper[-1]
        current_lower = lower[-1]
        current_middle = middle[-1]
        
        # BB 위치 기반 신호 (0-100 스케일)
        bb_position = (current_price - current_lower) / (current_upper - current_lower) * 100
        
        if bb_position <= 10:  # 하단 밴드 근처
            signal_type, strength = 'BUY', min(1.0, (10 - bb_position) / 10)
        elif bb_position >= 90:  # 상단 밴드 근처
            signal_type, strength = 'SELL', min(1.0, (bb_position - 90) / 10)
        else:
            signal_type, strength = 'NEUTRAL', 0.1
        
        return IndicatorResult(
            name=self.name,
            value=bb_position,
            signal=signal_type,
            strength=strength,
            timeframe=kwargs.get('timeframe', '1'),
            timestamp=int(df.iloc[-1]['timestamp'])
        )

class VolumeIndicator(BaseIndicator):
    """거래량 지표"""
    
    def __init__(self, period: int = 20):
        super().__init__(f"VOLUME_{period}")
        self.period = period
    
    async def calculate(self, df: pd.DataFrame, **kwargs) -> IndicatorResult:
        if len(df) < self.period:
            return IndicatorResult(
                name=self.name,
                value=1.0,
                signal='NEUTRAL',
                strength=0.0,
                timeframe=kwargs.get('timeframe', '1'),
                timestamp=int(df.iloc[-1]['timestamp']) if not df.empty else 0
            )
        
        # 평균 거래량 대비 현재 거래량 비율
        avg_volume = df['volume'].rolling(window=self.period).mean()
        current_volume = df.iloc[-1]['volume']
        volume_ratio = current_volume / avg_volume.iloc[-1]
        
        # 가격 변화와 거래량 관계
        price_change = (df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close']
        
        # 거래량 확인 신호
        if volume_ratio > 2.0 and price_change > 0.01:  # 거래량 급증 + 상승
            signal_type, strength = 'BUY', min(1.0, volume_ratio / 3.0)
        elif volume_ratio > 2.0 and price_change < -0.01:  # 거래량 급증 + 하락
            signal_type, strength = 'SELL', min(1.0, volume_ratio / 3.0)
        elif volume_ratio < 0.5:  # 거래량 급감
            signal_type, strength = 'NEUTRAL', 0.2
        else:
            signal_type, strength = 'NEUTRAL', 0.1
        
        return IndicatorResult(
            name=self.name,
            value=volume_ratio,
            signal=signal_type,
            strength=strength,
            timeframe=kwargs.get('timeframe', '1'),
            timestamp=int(df.iloc[-1]['timestamp'])
        )

class MovingAverageIndicator(BaseIndicator):
    """이동평균 지표"""
    
    def __init__(self, period: int = 20, ma_type: str = 'SMA'):
        super().__init__(f"{ma_type}_{period}")
        self.period = period
        self.ma_type = ma_type
    
    async def calculate(self, df: pd.DataFrame, **kwargs) -> IndicatorResult:
        if len(df) < self.period:
            return IndicatorResult(
                name=self.name,
                value=df.iloc[-1]['close'] if not df.empty else 0,
                signal='NEUTRAL',
                strength=0.0,
                timeframe=kwargs.get('timeframe', '1'),
                timestamp=int(df.iloc[-1]['timestamp']) if not df.empty else 0
            )
        
        # 이동평균 계산
        if self.ma_type == 'SMA':
            ma_values = talib.SMA(df['close'].values, timeperiod=self.period)
        elif self.ma_type == 'EMA':
            ma_values = talib.EMA(df['close'].values, timeperiod=self.period)
        elif self.ma_type == 'WMA':
            ma_values = talib.WMA(df['close'].values, timeperiod=self.period)
        else:
            ma_values = talib.SMA(df['close'].values, timeperiod=self.period)
        
        current_price = df.iloc[-1]['close']
        current_ma = ma_values[-1]
        prev_ma = ma_values[-2] if len(ma_values) > 1 else current_ma
        
        # 가격과 이동평균 관계 + 이동평균 기울기
        price_vs_ma = (current_price - current_ma) / current_ma * 100
        ma_slope = (current_ma - prev_ma) / prev_ma * 100
        
        # 신호 생성
        if current_price > current_ma and ma_slope > 0.1:
            signal_type = 'BUY'
            strength = min(1.0, abs(price_vs_ma) / 2.0 + abs(ma_slope))
        elif current_price < current_ma and ma_slope < -0.1:
            signal_type = 'SELL'
            strength = min(1.0, abs(price_vs_ma) / 2.0 + abs(ma_slope))
        else:
            signal_type = 'NEUTRAL'
            strength = 0.1
        
        return IndicatorResult(
            name=self.name,
            value=current_ma,
            signal=signal_type,
            strength=strength,
            timeframe=kwargs.get('timeframe', '1'),
            timestamp=int(df.iloc[-1]['timestamp'])
        )

class IndicatorEngine:
    """기술적 지표 계산 엔진"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 지표 인스턴스 초기화
        self.indicators: List[BaseIndicator] = []
        self._initialize_indicators()
        
        # 지표 결과 저장소
        self.indicator_results: Dict[str, Dict[str, List[IndicatorResult]]] = {}
        
    def _initialize_indicators(self):
        """지표 인스턴스들 초기화"""
        # RSI 지표들
        for period in self.config.RSI_PERIODS:
            self.indicators.append(RSIIndicator(period))
        
        # MACD 지표
        self.indicators.append(MACDIndicator(
            self.config.MACD_FAST,
            self.config.MACD_SLOW,
            self.config.MACD_SIGNAL
        ))
        
        # 볼린저 밴드
        self.indicators.append(BollingerBandsIndicator(
            self.config.BB_PERIOD,
            self.config.BB_STD
        ))
        
        # 이동평균선들
        for period in self.config.MA_PERIODS:
            self.indicators.append(MovingAverageIndicator(period, 'SMA'))
        
        for period in self.config.EMA_PERIODS:
            self.indicators.append(MovingAverageIndicator(period, 'EMA'))
        
        # 거래량 지표
        self.indicators.append(VolumeIndicator(20))
        
        self.logger.info(f"✅ {len(self.indicators)}개 지표 초기화 완료")
    
    async def calculate_all_indicators(self, symbol: str, market_data: Dict[str, pd.DataFrame]) -> Dict[str, List[IndicatorResult]]:
        """모든 지표 계산"""
        results = {}
        
        for timeframe, df in market_data.items():
            if df is None or df.empty:
                continue
            
            timeframe_results = []
            
            # 각 지표별 계산
            for indicator in self.indicators:
                try:
                    result = await indicator.calculate(df, timeframe=timeframe)
                    timeframe_results.append(result)
                    
                except Exception as e:
                    self.logger.error(f"❌ {symbol} {timeframe} {indicator.name} 계산 실패: {str(e)}")
            
            results[timeframe] = timeframe_results
        
        return results
    
    def update_indicators(self, symbol: str, results: Dict[str, List[IndicatorResult]]):
        """지표 결과 업데이트"""
        self.indicator_results[symbol] = results
    
    def get_indicators(self, symbol: str, timeframe: str = None) -> Optional[List[IndicatorResult]]:
        """지표 결과 조회"""
        if symbol not in self.indicator_results:
            return None
        
        if timeframe:
            return self.indicator_results[symbol].get(timeframe)
        else:
            # 모든 시간대의 지표 결합
            all_results = []
            for tf_results in self.indicator_results[symbol].values():
                all_results.extend(tf_results)
            return all_results
    
    def calculate_btc_dominance_factor(self) -> float:
        """BTC 도미넌스 팩터 계산"""
        try:
            btc_indicators = self.get_indicators('BTCUSDT', '15')  # 15분봉 기준
            if not btc_indicators:
                return 1.0
            
            # BTC 강도 계산 (여러 지표 종합)
            total_strength = 0
            count = 0
            
            for indicator in btc_indicators:
                if indicator.signal == 'BUY':
                    total_strength += indicator.strength
                elif indicator.signal == 'SELL':
                    total_strength -= indicator.strength
                count += 1
            
            if count == 0:
                return 1.0
            
            avg_strength = total_strength / count
            
            # 강도에 따른 팩터 결정
            if avg_strength > 0.6:
                return self.config.BTC_DOMINANCE_WEIGHTS['STRONG_BULL']
            elif avg_strength > 0.3:
                return self.config.BTC_DOMINANCE_WEIGHTS['BULL']
            elif avg_strength < -0.6:
                return self.config.BTC_DOMINANCE_WEIGHTS['STRONG_BEAR']
            elif avg_strength < -0.3:
                return self.config.BTC_DOMINANCE_WEIGHTS['BEAR']
            else:
                return self.config.BTC_DOMINANCE_WEIGHTS['SIDEWAYS']
                
        except Exception as e:
            self.logger.error(f"BTC 도미넌스 계산 실패: {str(e)}")
            return 1.0
    
    def get_indicator_summary(self, symbol: str, timeframe: str = '15') -> Dict[str, Any]:
        """지표 요약 정보"""
        indicators = self.get_indicators(symbol, timeframe)
        if not indicators:
            return {}
        
        buy_count = sum(1 for ind in indicators if ind.signal == 'BUY')
        sell_count = sum(1 for ind in indicators if ind.signal == 'SELL')
        neutral_count = len(indicators) - buy_count - sell_count
        
        avg_buy_strength = np.mean([ind.strength for ind in indicators if ind.signal == 'BUY']) if buy_count > 0 else 0
        avg_sell_strength = np.mean([ind.strength for ind in indicators if ind.signal == 'SELL']) if sell_count > 0 else 0
        
        return {
            'total_indicators': len(indicators),
            'buy_signals': buy_count,
            'sell_signals': sell_count,
            'neutral_signals': neutral_count,
            'buy_strength': avg_buy_strength,
            'sell_strength': avg_sell_strength,
            'overall_bias': 'BUY' if buy_count > sell_count else 'SELL' if sell_count > buy_count else 'NEUTRAL'
        }
