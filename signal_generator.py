# signal_generator.py - 신호 생성 모듈
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np

from indicator_engine import IndicatorResult

@dataclass
class TradingSignal:
    """트레이딩 신호 데이터 구조"""
    symbol: str
    direction: str  # 'LONG', 'SHORT'
    score: int  # 0-100점
    confidence: float  # 0-1 신뢰도
    timeframe: str  # 주 시간대
    timestamp: datetime
    
    # 진입 정보
    entry_price: float
    entry_zones: List[Dict[str, float]]  # [{'price': 250, 'ratio': 0.3}, ...]
    
    # 리스크 관리
    stop_loss: float
    take_profits: List[float]
    trailing_stop_activation: float
    
    # 포지션 사이징
    recommended_size: float  # USD
    leverage: int
    risk_reward_ratio: float
    
    # 근거 및 분석
    primary_reasons: List[str]
    supporting_factors: List[str]
    risk_factors: List[str]
    expected_duration: str
    
    # 수익/손실 계산
    profit_scenarios: Dict[str, float]
    loss_scenarios: Dict[str, float]

class PatternRecognizer:
    """차트 패턴 인식"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def detect_breakout_patterns(self, df, current_price: float) -> Dict[str, any]:
        """브레이크아웃 패턴 감지"""
        if len(df) < 50:
            return {'pattern': None, 'strength': 0}
        
        # 최근 20개 캔들의 고점/저점 분석
        recent_highs = df['high'].rolling(window=20).max()
        recent_lows = df['low'].rolling(window=20).min()
        
        resistance = recent_highs.iloc[-1]
        support = recent_lows.iloc[-1]
        
        # 브레이크아웃 감지
        price_range = resistance - support
        resistance_break = (current_price - resistance) / price_range
        support_break = (support - current_price) / price_range
        
        if resistance_break > 0.002:  # 저항선 돌파
            return {
                'pattern': 'RESISTANCE_BREAKOUT',
                'strength': min(1.0, resistance_break * 50),
                'direction': 'LONG',
                'target': resistance + price_range * 0.5
            }
        elif support_break > 0.002:  # 지지선 이탈
            return {
                'pattern': 'SUPPORT_BREAKDOWN',
                'strength': min(1.0, support_break * 50),
                'direction': 'SHORT', 
                'target': support - price_range * 0.5
            }
        
        return {'pattern': None, 'strength': 0}
    
    def detect_reversal_patterns(self, df) -> Dict[str, any]:
        """반전 패턴 감지"""
        if len(df) < 10:
            return {'pattern': None, 'strength': 0}
        
        # 더블탑/더블바텀 패턴 감지 (간단한 버전)
        last_5_highs = df['high'].tail(5)
        last_5_lows = df['low'].tail(5)
        
        # 최근 고점이 이전 고점과 비슷한 수준인지 확인
        max_high = last_5_highs.max()
        second_max = last_5_highs.nlargest(2).iloc[1]
        
        if abs(max_high - second_max) / max_high < 0.01:  # 1% 이내 차이
            return {
                'pattern': 'DOUBLE_TOP',
                'strength': 0.7,
                'direction': 'SHORT'
            }
        
        # 최근 저점이 이전 저점과 비슷한 수준인지 확인  
        min_low = last_5_lows.min()
        second_min = last_5_lows.nsmallest(2).iloc[1]
        
        if abs(min_low - second_min) / min_low < 0.01:  # 1% 이내 차이
            return {
                'pattern': 'DOUBLE_BOTTOM',
                'strength': 0.7,
                'direction': 'LONG'
            }
        
        return {'pattern': None, 'strength': 0}

class RiskCalculator:
    """리스크 계산 및 포지션 사이징"""
    
    def __init__(self, config):
        self.config = config
    
    def calculate_position_size(self, signal_score: int, account_balance: float, 
                              entry_price: float, stop_loss: float) -> Dict[str, float]:
        """포지션 사이즈 계산"""
        
        # 신호 강도에 따른 기본 리스크 조정
        base_risk = self.config.MAX_POSITION_RATIO
        risk_multiplier = signal_score / 100.0
        adjusted_risk = base_risk * risk_multiplier
        
        # 손실 거리 계산
        risk_distance = abs(entry_price - stop_loss) / entry_price
        
        # 최대 손실금액 (계좌의 2%)
        max_loss = account_balance * 0.02
        
        # 포지션 사이즈 계산
        position_value = min(
            account_balance * adjusted_risk,  # 최대 리스크 기반
            max_loss / risk_distance  # 손절 거리 기반
        )
        
        return {
            'position_value': position_value,
            'risk_amount': position_value * risk_distance,
            'risk_percentage': (position_value * risk_distance) / account_balance * 100
        }
    
    def calculate_take_profits(self, entry_price: float, direction: str, 
                              volatility: float) -> List[float]:
        """익절 목표가 계산"""
        
        # 변동성 기반 목표가 설정
        base_target_1 = volatility * 2.0  # 2배 변동성
        base_target_2 = volatility * 4.0  # 4배 변동성
        
        if direction == 'LONG':
            tp1 = entry_price * (1 + base_target_1)
            tp2 = entry_price * (1 + base_target_2)
        else:  # SHORT
            tp1 = entry_price * (1 - base_target_1)
            tp2 = entry_price * (1 - base_target_2)
        
        return [tp1, tp2]

class SignalGenerator:
    """트레이딩 신호 생성기"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.pattern_recognizer = PatternRecognizer()
        self.risk_calculator = RiskCalculator(config)
        
        # 신호 생성 통계
        self.signal_stats = {
            'generated': 0,
            'successful': 0,
            'failed': 0
        }
    
    async def generate_signal(self, symbol: str, indicators: List[IndicatorResult], 
                            market_data=None) -> Optional[TradingSignal]:
        """메인 신호 생성 함수"""
        
        if not indicators:
            return None
        
        try:
            # 1. 기본 점수 계산
            base_score = self._calculate_base_score(indicators)
            
            # 2. 패턴 보정
            pattern_bonus = 0
            if market_data:
                pattern_bonus = await self._analyze_patterns(market_data)
            
            # 3. BTC 도미넌스 보정 (알트코인인 경우)
            btc_factor = 1.0
            if symbol != 'BTCUSDT':
                btc_factor = await self._get_btc_correlation_factor()
            
            # 4. 최종 점수 계산
            final_score = int((base_score + pattern_bonus) * btc_factor)
            final_score = max(0, min(100, final_score))  # 0-100 범위 제한
            
            # 5. 최소 점수 미달 시 신호 생성 안함
            if final_score < self.config.MIN_SIGNAL_SCORE:
                return None
            
            # 6. 신호 방향 결정
            direction = self._determine_direction(indicators)
            if not direction:
                return None
            
            # 7. 상세 신호 생성
            signal = await self._create_detailed_signal(
                symbol, direction, final_score, indicators, market_data
            )
            
            self.signal_stats['generated'] += 1
            self.logger.info(f"📊 {symbol} 신호 생성: {direction} ({final_score}점)")
            
            return signal
            
        except Exception as e:
            self.logger.error(f"❌ {symbol} 신호 생성 실패: {str(e)}")
            return None
    
    def _calculate_base_score(self, indicators: List[IndicatorResult]) -> float:
        """기본 점수 계산"""
        if not indicators:
            return 0
        
        # 시간대별 가중치 적용
        timeframe_weights = {
            '1': 0.15,   # 1분봉 - 15%
            '3': 0.15,   # 3분봉 - 15% 
            '5': 0.20,   # 5분봉 - 20%
            '15': 0.25,  # 15분봉 - 25%
            '30': 0.15,  # 30분봉 - 15%
            '60': 0.10   # 1시간봉 - 10%
        }
        
        buy_score = 0
        sell_score = 0
        total_weight = 0
        
        for indicator in indicators:
            weight = timeframe_weights.get(indicator.timeframe, 0.1)
            
            if indicator.signal == 'BUY':
                buy_score += indicator.strength * weight * 100
            elif indicator.signal == 'SELL':
                sell_score += indicator.strength * weight * 100
            
            total_weight += weight
        
        # 정규화
        if total_weight > 0:
            buy_score /= total_weight
            sell_score /= total_weight
        
        # 더 강한 방향의 점수 반환
        return max(buy_score, sell_score)
    
    def _determine_direction(self, indicators: List[IndicatorResult]) -> Optional[str]:
        """신호 방향 결정"""
        buy_strength = sum(ind.strength for ind in indicators if ind.signal == 'BUY')
        sell_strength = sum(ind.strength for ind in indicators if ind.signal == 'SELL')
        
        # 최소 차이 필요 (노이즈 제거)
        min_diff = 1.0
        
        if buy_strength - sell_strength > min_diff:
            return 'LONG'
        elif sell_strength - buy_strength > min_diff:
            return 'SHORT'
        else:
            return None
    
    async def _analyze_patterns(self, market_data) -> float:
        """패턴 분석 보정점수"""
        if not market_data or '5' not in market_data:
            return 0
        
        df = market_data['5']  # 5분봉 기준
        if df.empty:
            return 0
        
        current_price = df.iloc[-1]['close']
        
        # 브레이크아웃 패턴
        breakout = self.pattern_recognizer.detect_breakout_patterns(df, current_price)
        if breakout['pattern']:
            return breakout['strength'] * 15  # 최대 15점 보너스
        
        # 반전 패턴  
        reversal = self.pattern_recognizer.detect_reversal_patterns(df)
        if reversal['pattern']:
            return reversal['strength'] * 10  # 최대 10점 보너스
        
        return 0
    
    async def _get_btc_correlation_factor(self) -> float:
        """BTC 상관관계 팩터 조회"""
        # TODO: IndicatorEngine에서 BTC 도미넌스 팩터 가져오기
        # 임시로 기본값 반환
        return 1.0
    
    async def _create_detailed_signal(self, symbol: str, direction: str, score: int,
                                    indicators: List[IndicatorResult], market_data) -> TradingSignal:
        """상세 신호 생성"""
        
        # 현재 가격 정보
        current_price = 0
        if market_data and '1' in market_data and not market_data['1'].empty:
            current_price = market_data['1'].iloc[-1]['close']
        
        # 변동성 계산 (ATR 기반)
        volatility = self._calculate_volatility(market_data)
        
        # 진입 구간 설정
        entry_zones = self._calculate_entry_zones(current_price, direction, volatility)
        
        # 손절/익절 계산
        stop_loss = self._calculate_stop_loss(current_price, direction, volatility)
        take_profits = self.risk_calculator.calculate_take_profits(
            current_price, direction, volatility
        )
        
        # 포지션 사이징
        position_info = self.risk_calculator.calculate_position_size(
            score, self.config.TOTAL_CAPITAL, current_price, stop_loss
        )
        
        # 수익/손실 시나리오
        profit_scenarios, loss_scenarios = self._calculate_scenarios(
            current_price, take_profits, stop_loss, position_info['position_value'], direction
        )
        
        # 신호 근거 분석
        reasons = self._analyze_signal_reasons(indicators)
        
        return TradingSignal(
            symbol=symbol,
            direction=direction,
            score=score,
            confidence=score / 100.0,
            timeframe='5',  # 주 분석 시간대
            timestamp=datetime.now(),
            
            entry_price=current_price,
            entry_zones=entry_zones,
            
            stop_loss=stop_loss,
            take_profits=take_profits,
            trailing_stop_activation=current_price * (1.02 if direction == 'LONG' else 0.98),
            
            recommended_size=position_info['position_value'],
            leverage=self._calculate_optimal_leverage(score, volatility),
            risk_reward_ratio=self._calculate_risk_reward(current_price, stop_loss, take_profits[0]),
            
            primary_reasons=reasons['primary'],
            supporting_factors=reasons['supporting'],
            risk_factors=reasons['risks'],
            expected_duration=self._estimate_duration(score, volatility),
            
            profit_scenarios=profit_scenarios,
            loss_scenarios=loss_scenarios
        )
    
    def _calculate_volatility(self, market_data) -> float:
        """변동성 계산 (ATR 기반)"""
        if not market_data or '15' not in market_data:
            return 0.02  # 기본값 2%
        
        df = market_data['15']
        if len(df) < 14:
            return 0.02
        
        # True Range 계산
        df_temp = df.copy()
        df_temp['tr1'] = df_temp['high'] - df_temp['low']
        df_temp['tr2'] = abs(df_temp['high'] - df_temp['close'].shift(1))
        df_temp['tr3'] = abs(df_temp['low'] - df_temp['close'].shift(1))
        df_temp['true_range'] = df_temp[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # ATR 계산 (14 기간)
        atr = df_temp['true_range'].rolling(window=14).mean().iloc[-1]
        current_price = df.iloc[-1]['close']
        
        return atr / current_price if current_price > 0 else 0.02
    
    def _calculate_entry_zones(self, current_price: float, direction: str, 
                              volatility: float) -> List[Dict[str, float]]:
        """분할 진입 구간 계산"""
        zones = []
        
        for i, (ratio, distance) in enumerate(zip(
            self.config.SPLIT_ENTRY_RATIOS, 
            self.config.SPLIT_ENTRY_DISTANCES
        )):
            if direction == 'LONG':
                price = current_price * (1 - distance)
            else:  # SHORT
                price = current_price * (1 + distance)
            
            zones.append({
                'order': i + 1,
                'price': round(price, 4),
                'ratio': ratio,
                'amount': self.config.TOTAL_CAPITAL * self.config.MAX_POSITION_RATIO * ratio
            })
        
        return zones
    
    def _calculate_stop_loss(self, entry_price: float, direction: str, volatility: float) -> float:
        """손절가 계산"""
        # 변동성 기반 손절 (최소 2%, 최대 8%)
        stop_distance = max(0.02, min(0.08, volatility * 2.5))
        
        if direction == 'LONG':
            return entry_price * (1 - stop_distance)
        else:  # SHORT
            return entry_price * (1 + stop_distance)
    
    def _calculate_optimal_leverage(self, score: int, volatility: float) -> int:
        """최적 레버리지 계산"""
        # 높은 점수 + 낮은 변동성 = 높은 레버리지
        base_leverage = self.config.DEFAULT_LEVERAGE
        
        # 점수 보정
        score_factor = score / 100.0
        
        # 변동성 보정 (높은 변동성 = 낮은 레버리지)
        volatility_factor = max(0.5, 1 - (volatility - 0.02) / 0.06)
        
        optimal_leverage = int(base_leverage * score_factor * volatility_factor)
        
        return max(self.config.MIN_LEVERAGE, 
                  min(self.config.MAX_LEVERAGE, optimal_leverage))
    
    def _calculate_risk_reward(self, entry: float, stop: float, target: float) -> float:
        """손익비 계산"""
        risk = abs(entry - stop)
        reward = abs(target - entry)
        
        return reward / risk if risk > 0 else 0
    
    def _calculate_scenarios(self, entry_price: float, take_profits: List[float], 
                           stop_loss: float, position_value: float, direction: str) -> Tuple[Dict, Dict]:
        """수익/손실 시나리오 계산"""
        
        profit_scenarios = {}
        loss_scenarios = {}
        
        # 수익 시나리오
        for i, tp in enumerate(take_profits, 1):
            if direction == 'LONG':
                pnl = (tp - entry_price) / entry_price * position_value
            else:
                pnl = (entry_price - tp) / entry_price * position_value
            
            profit_scenarios[f'target_{i}'] = round(pnl, 2)
        
        # 손실 시나리오
        if direction == 'LONG':
            loss = (stop_loss - entry_price) / entry_price * position_value
        else:
            loss = (entry_price - stop_loss) / entry_price * position_value
        
        loss_scenarios['stop_loss'] = round(loss, 2)
        
        return profit_scenarios, loss_scenarios
    
    def _analyze_signal_reasons(self, indicators: List[IndicatorResult]) -> Dict[str, List[str]]:
        """신호 근거 분석"""
        primary_reasons = []
        supporting_factors = []
        risk_factors = []
        
        # 강한 지표들을 주요 근거로
        strong_indicators = [ind for ind in indicators if ind.strength > 0.7]
        for ind in strong_indicators[:3]:  # 상위 3개만
            primary_reasons.append(f"{ind.name}: {ind.signal} ({ind.strength:.1f})")
        
        # 중간 강도 지표들을 보조 근거로
        medium_indicators = [ind for ind in indicators if 0.4 < ind.strength <= 0.7]
        for ind in medium_indicators[:3]:
            supporting_factors.append(f"{ind.name} {ind.signal}")
        
        # 반대 신호를 위험 요소로
        opposite_signals = [ind for ind in indicators if ind.strength > 0.5]
        # TODO: 반대 방향 신호 찾는 로직 추가
        
        return {
            'primary': primary_reasons,
            'supporting': supporting_factors,
            'risks': risk_factors
        }
    
    def _estimate_duration(self, score: int, volatility: float) -> str:
        """예상 소요시간 추정"""
        if score >= 85:
            return "30분-2시간 (강한 신호)"
        elif score >= 70:
            return "1-4시간 (중간 신호)"
        else:
            return "2-8시간 (약한 신호)"
    
    def get_signal_statistics(self) -> Dict[str, any]:
        """신호 생성 통계"""
        total = self.signal_stats['generated']
        if total == 0:
            return {'success_rate': 0, 'total_generated': 0}
        
        return {
            'success_rate': self.signal_stats['successful'] / total * 100,
            'total_generated': total,
            'successful': self.signal_stats['successful'],
            'failed': self.signal_stats['failed']
        }
