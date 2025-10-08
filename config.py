# config.py - 설정 파일
import os
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class Config:
    """트레이딩 봇 설정 클래스"""
    
    # =============================================================================
    # API 설정 (환경변수 또는 직접 입력)
    # =============================================================================
    BYBIT_API_KEY: str = os.getenv('BYBIT_API_KEY', 'Y4l4YahsrMU62STpt17')
    BYBIT_SECRET: str = os.getenv('BYBIT_SECRET', 'sdjLI0Ag9aEqOsYar46Bj9G0IwGpNeJ5RRfG')
    BYBIT_TESTNET: bool = True  # 테스트넷 사용 여부 (처음엔 True 권장)
    
    TELEGRAM_BOT_TOKEN: str = os.getenv('8423339826:AAHmToz5OflYj6LYYvfu6Fege878B5Cdmf4')
    TELEGRAM_CHAT_ID: str = os.getenv('296985422')
    
    # =============================================================================
    # 거래 설정
    # =============================================================================
    SYMBOLS: List[str] = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
        'DOGEUSDT', 'LINKUSDT', 'ADAUSDT', 'MATICUSDT', 'SHIBUSDT'
    ]
    
    # 계좌 설정
    TOTAL_CAPITAL: float = 3000.0  # 총 자본금 (USD)
    MAX_POSITION_RATIO: float = 0.2  # 단일 포지션 최대 비중 (20%)
    DAILY_LOSS_LIMIT: float = 0.05  # 일일 손실 한도 (5%)
    MAX_CONCURRENT_POSITIONS: int = 3  # 최대 동시 포지션 수
    
    # 레버리지 설정
    DEFAULT_LEVERAGE: int = 10
    MAX_LEVERAGE: int = 20
    MIN_LEVERAGE: int = 5
    
    # =============================================================================
    # 신호 생성 설정
    # =============================================================================
    MIN_SIGNAL_SCORE: int = 70  # 최소 신호 점수 (70점 이상만 전송)
    MIN_SIGNAL_INTERVAL: int = 15  # 같은 코인 신호 간격 (분)
    
    # BTC 도미넌스 가중치
    BTC_DOMINANCE_WEIGHTS: Dict[str, float] = {
        'STRONG_BULL': 2.0,      # BTC 강한 상승 시 알트 신호 2배
        'BULL': 1.5,             # BTC 상승 시 1.5배
        'SIDEWAYS': 1.0,         # BTC 횡보 시 기본
        'BEAR': 0.7,             # BTC 하락 시 0.7배
        'STRONG_BEAR': 0.3       # BTC 강한 하락 시 0.3배
    }
    
    # =============================================================================
    # 기술적 지표 설정
    # =============================================================================
    INDICATOR_WEIGHTS: Dict[str, Dict[str, float]] = {
        'SCALPING': {  # 스캘핑 (1-5분)
            'VOLUME': 0.25,
            'PRICE_ACTION': 0.20,
            'MOMENTUM': 0.15,
            'BTC_CORRELATION': 0.15,
            'SUPPORT_RESISTANCE': 0.10,
            'PATTERNS': 0.10,
            'SENTIMENT': 0.05
        },
        'SWING': {  # 스윙 (15분-1시간)
            'TECHNICAL_INDICATORS': 0.22,
            'BTC_CORRELATION': 0.18,
            'VOLUME': 0.16,
            'PATTERNS': 0.14,
            'SUPPORT_RESISTANCE': 0.12,
            'MOMENTUM': 0.10,
            'SENTIMENT': 0.08
        },
        'POSITION': {  # 포지션 (일봉 이상)
            'FUNDAMENTALS': 0.25,
            'MACRO_ECONOMICS': 0.20,
            'BTC_LONGTERM': 0.15,
            'ONCHAIN_DATA': 0.15,
            'TECHNICAL_INDICATORS': 0.12,
            'NEWS_SENTIMENT': 0.08,
            'SOCIAL_SENTIMENT': 0.05
        }
    }
    
    # RSI 설정
    RSI_PERIODS: List[int] = [14, 21, 50]
    RSI_OVERBOUGHT: int = 70
    RSI_OVERSOLD: int = 30
    
    # 이동평균 설정  
    MA_PERIODS: List[int] = [8, 21, 50, 200]
    EMA_PERIODS: List[int] = [8, 21, 50, 200]
    
    # MACD 설정
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    
    # 볼린저 밴드 설정
    BB_PERIOD: int = 20
    BB_STD: float = 2.0
    
    # =============================================================================
    # 포지션 관리 설정
    # =============================================================================
    # 기본 손절/익절 설정
    DEFAULT_STOP_LOSS: float = 0.05  # 5% 손절
    DEFAULT_TAKE_PROFIT_1: float = 0.04  # 4% 1차 익절
    DEFAULT_TAKE_PROFIT_2: float = 0.08  # 8% 2차 익절
    
    # 트레일링 스탑 설정
    TRAILING_STOP_ACTIVATION: float = 0.02  # 2% 수익 시 트레일링 활성화
    TRAILING_STOP_DISTANCE: float = 0.015   # 1.5% 트레일링 거리
    
    # 분할 진입 설정
    SPLIT_ENTRY_RATIOS: List[float] = [0.3, 0.3, 0.4]  # 30%, 30%, 40%
    SPLIT_ENTRY_DISTANCES: List[float] = [0.005, 0.01, 0.025]  # 0.5%, 1%, 2.5%
    
    # =============================================================================
    # 데이터 수집 설정
    # =============================================================================
    TIMEFRAMES: List[str] = ['1', '3', '5', '15', '30', '60', '240', 'D']
    DATA_LIMIT: int = 200  # 캔들 수집 개수
    
    # API 호출 제한
    API_RATE_LIMIT: int = 120  # 분당 API 호출 제한
    REQUEST_TIMEOUT: int = 30   # 요청 타임아웃 (초)
    
    # =============================================================================
    # 텔레그램 설정
    # =============================================================================
    TELEGRAM_SETTINGS: Dict[str, Any] = {
        'SIGNAL_DETAIL_LEVEL': 'DETAILED',  # SIMPLE, DETAILED, ADVANCED
        'ENABLE_BUTTONS': True,
        'ENABLE_CHARTS': False,  # 차트 이미지 전송 여부
        'MAX_MESSAGE_LENGTH': 4096,
        'RETRY_ATTEMPTS': 3,
        'RETRY_DELAY': 5
    }
    
    # =============================================================================
    # 로깅 설정
    # =============================================================================
    LOG_LEVEL: str = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FILE: str = 'logs/trading_bot.log'
    LOG_MAX_SIZE: int = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT: int = 5
    
    # =============================================================================
    # 백테스팅 설정
    # =============================================================================
    BACKTEST_ENABLED: bool = True
    BACKTEST_DAYS: int = 30  # 백테스팅 기간
    BACKTEST_MIN_TRADES: int = 10  # 최소 거래 수
    
    # =============================================================================
    # 유튜브 학습 설정 (추후 구현)
    # =============================================================================
    YOUTUBE_LEARNING: Dict[str, Any] = {
        'ENABLED': False,  # 추후 활성화
        'CHANNELS': [
            'Benjamin Cowen',
            'Coin Bureau',
            'The Trading Channel',
            'Smart Money Concepts'
        ],
        'LEARNING_SCHEDULE': '03:00',  # 새벽 3시 학습
        'MIN_SUCCESS_RATE': 0.7  # 70% 이상 성공률만 적용
    }
    
    # =============================================================================
    # 개발/디버그 설정
    # =============================================================================
    DEBUG_MODE: bool = True  # 개발 중에는 True
    PAPER_TRADING: bool = True  # 모의 거래 (실제 주문 X)
    SEND_TEST_SIGNALS: bool = True  # 테스트 신호 전송
    
    def __post_init__(self):
        """설정 검증 및 초기화 후 처리"""
        self.validate_config()
        self.create_directories()
    
    def validate_config(self):
        """설정값 검증"""
        # API 키 검증
        if self.BYBIT_API_KEY == 'Y4l4YahsrMU62STpt17':
            raise ValueError("바이비트 API 키를 설정해주세요!")
        
        if self.TELEGRAM_BOT_TOKEN == '8423339826:AAHmToz5OflYj6LYYvfu6Fege878B5Cdmf4':
            raise ValueError("텔레그램 봇 토큰을 설정해주세요!")
        
        # 비율 검증
        if not 0 < self.MAX_POSITION_RATIO <= 1:
            raise ValueError("MAX_POSITION_RATIO는 0과 1 사이여야 합니다!")
        
        if sum(self.SPLIT_ENTRY_RATIOS) != 1.0:
            raise ValueError("SPLIT_ENTRY_RATIOS의 합은 1.0이어야 합니다!")
    
    def create_directories(self):
        """필요한 디렉토리 생성"""
        directories = ['logs', 'data', 'backtest_results']
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def get_symbol_config(self, symbol: str) -> Dict[str, Any]:
        """특정 심볼에 대한 설정 반환"""
        return {
            'leverage': self.DEFAULT_LEVERAGE,
            'stop_loss': self.DEFAULT_STOP_LOSS,
            'take_profit_1': self.DEFAULT_TAKE_PROFIT_1,
            'take_profit_2': self.DEFAULT_TAKE_PROFIT_2,
            'position_size': self.TOTAL_CAPITAL * self.MAX_POSITION_RATIO
        }
    
    def update_setting(self, key: str, value: Any):
        """런타임 설정 업데이트"""
        if hasattr(self, key):
            setattr(self, key, value)
            return True
        return False

# 전역 설정 인스턴스
config = Config()
