# data_collector.py - 데이터 수집 모듈
import asyncio
import aiohttp
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time
from dataclasses import dataclass
import hmac
import hashlib
from urllib.parse import urlencode

@dataclass
class CandleData:
    """캔들 데이터 구조체"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: str

class BybitAPI:
    """바이비트 API 클라이언트"""
    
    def __init__(self, api_key: str, secret: str, testnet: bool = True):
        self.api_key = api_key
        self.secret = secret
        self.testnet = testnet
        
        # API 엔드포인트 설정
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"
        
        # 세션 및 제한 설정
        self.session = None
        self.rate_limiter = RateLimiter(120)  # 분당 120 요청
        self.logger = logging.getLogger(__name__)
    
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        if self.session:
            await self.session.close()
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """API 서명 생성"""
        # 타임스탬프 추가
        params['api_key'] = self.api_key
        params['timestamp'] = str(int(time.time() * 1000))
        
        # 매개변수 정렬 및 쿼리 스트링 생성
        query_string = urlencode(sorted(params.items()))
        
        # HMAC-SHA256 서명 생성
        signature = hmac.new(
            self.secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        params['sign'] = signature
        return params
    
    async def _make_request(self, method: str, endpoint: str, params: Dict = None, 
                          sign_required: bool = False) -> Dict:
        """API 요청 실행"""
        if not self.session:
            raise RuntimeError("API 클라이언트가 초기화되지 않았습니다.")
        
        # 요청 제한 대기
        await self.rate_limiter.wait()
        
        url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        # 서명이 필요한 경우
        if sign_required:
            params = self._generate_signature(params)
        
        try:
            if method.upper() == 'GET':
                async with self.session.get(url, params=params) as response:
                    data = await response.json()
            else:
                async with self.session.request(method, url, json=params) as response:
                    data = await response.json()
            
            # API 응답 검증
            if data.get('retCode') != 0:
                raise Exception(f"API 오류: {data.get('retMsg', 'Unknown error')}")
            
            return data.get('result', {})
            
        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP 요청 실패: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"API 요청 처리 실패: {str(e)}")
            raise
    
    async def get_kline_data(self, symbol: str, interval: str, limit: int = 200) -> List[Dict]:
        """K-라인(캔들) 데이터 조회"""
        params = {
            'category': 'linear',  # USDT Perpetual
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        data = await self._make_request('GET', '/v5/market/kline', params)
        return data.get('list', [])
    
    async def get_ticker_info(self, symbol: str) -> Dict:
        """티커 정보 조회"""
        params = {
            'category': 'linear',
            'symbol': symbol
        }
        
        data = await self._make_request('GET', '/v5/market/tickers', params)
        tickers = data.get('list', [])
        return tickers[0] if tickers else {}
    
    async def get_positions(self) -> List[Dict]:
        """현재 포지션 조회"""
        params = {
            'category': 'linear',
            'settleCoin': 'USDT'
        }
        
        data = await self._make_request('GET', '/v5/position/list', params, sign_required=True)
        return data.get('list', [])
    
    async def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            await self._make_request('GET', '/v5/market/time')
            return True
        except Exception as e:
            self.logger.error(f"연결 테스트 실패: {str(e)}")
            return False

class RateLimiter:
    """API 호출 속도 제한"""
    
    def __init__(self, max_requests_per_minute: int):
        self.max_requests = max_requests_per_minute
        self.requests = []
        self.lock = asyncio.Lock()
    
    async def wait(self):
        """요청 전 대기"""
        async with self.lock:
            now = time.time()
            
            # 1분 이전 요청 제거
            self.requests = [req_time for req_time in self.requests 
                           if now - req_time < 60]
            
            # 제한 초과 시 대기
            if len(self.requests) >= self.max_requests:
                sleep_time = 60 - (now - self.requests[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    self.requests = self.requests[1:]
            
            # 현재 요청 시간 기록
            self.requests.append(now)

class DataCollector:
    """데이터 수집 및 관리 클래스"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 바이비트 API 클라이언트
        self.api = BybitAPI(
            config.BYBIT_API_KEY,
            config.BYBIT_SECRET,
            config.BYBIT_TESTNET
        )
        
        # 데이터 저장소
        self.symbol_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        self.ticker_data: Dict[str, Dict] = {}
        
        # 상태 관리
        self.last_update: Dict[str, datetime] = {}
        self.is_initialized = False
    
    async def initialize(self):
        """데이터 수집기 초기화"""
        try:
            self.logger.info("📊 데이터 수집기 초기화 중...")
            
            # API 연결 테스트
            async with self.api as api:
                if not await api.test_connection():
                    raise Exception("바이비트 API 연결 실패")
            
            self.is_initialized = True
            self.logger.info("✅ 데이터 수집기 초기화 완료")
            
        except Exception as e:
            self.logger.error(f"데이터 수집기 초기화 실패: {str(e)}")
            raise
    
    async def test_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            async with self.api as api:
                return await api.test_connection()
        except Exception:
            return False
    
    async def fetch_initial_data(self):
        """초기 데이터 수집"""
        self.logger.info("📥 초기 데이터 수집 시작...")
        
        try:
            async with self.api as api:
                for symbol in self.config.SYMBOLS:
                    self.logger.info(f"📊 {symbol} 데이터 수집 중...")
                    
                    # 심볼별 데이터 저장소 초기화
                    self.symbol_data[symbol] = {}
                    
                    # 각 시간대별 데이터 수집
                    for timeframe in self.config.TIMEFRAMES:
                        try:
                            kline_data = await api.get_kline_data(
                                symbol, timeframe, self.config.DATA_LIMIT
                            )
                            
                            # DataFrame으로 변환
                            df = self._convert_to_dataframe(kline_data, symbol, timeframe)
                            self.symbol_data[symbol][timeframe] = df
                            
                            self.logger.debug(f"✅ {symbol} {timeframe} 데이터 수집 완료 ({len(df)}개)")
                            
                        except Exception as e:
                            self.logger.error(f"❌ {symbol} {timeframe} 데이터 수집 실패: {str(e)}")
                    
                    # 티커 데이터 수집
                    ticker = await api.get_ticker_info(symbol)
                    self.ticker_data[symbol] = ticker
                    
                    # 업데이트 시간 기록
                    self.last_update[symbol] = datetime.now()
                    
                    # API 제한을 위한 짧은 대기
                    await asyncio.sleep(0.1)
            
            self.logger.info("✅ 초기 데이터 수집 완료")
            
        except Exception as e:
            self.logger.error(f"❌ 초기 데이터 수집 실패: {str(e)}")
            raise
    
    async def update_symbol_data(self, symbol: str):
        """특정 심볼 데이터 업데이트"""
        try:
            async with self.api as api:
                # 최신 캔들 데이터 수집 (최근 50개만)
                for timeframe in self.config.TIMEFRAMES:
                    kline_data = await api.get_kline_data(symbol, timeframe, 50)
                    new_df = self._convert_to_dataframe(kline_data, symbol, timeframe)
                    
                    # 기존 데이터와 병합
                    if symbol in self.symbol_data and timeframe in self.symbol_data[symbol]:
                        existing_df = self.symbol_data[symbol][timeframe]
                        
                        # 중복 제거 후 병합
                        combined_df = pd.concat([existing_df, new_df]).drop_duplicates(
                            subset=['timestamp'], keep='last'
                        ).sort_values('timestamp')
                        
                        # 최대 길이 제한
                        if len(combined_df) > self.config.DATA_LIMIT:
                            combined_df = combined_df.tail(self.config.DATA_LIMIT)
                        
                        self.symbol_data[symbol][timeframe] = combined_df
                    else:
                        if symbol not in self.symbol_data:
                            self.symbol_data[symbol] = {}
                        self.symbol_data[symbol][timeframe] = new_df
                
                # 티커 데이터 업데이트
                ticker = await api.get_ticker_info(symbol)
                self.ticker_data[symbol] = ticker
                
                # 업데이트 시간 기록
                self.last_update[symbol] = datetime.now()
                
        except Exception as e:
            self.logger.error(f"❌ {symbol} 데이터 업데이트 실패: {str(e)}")
            raise
    
    def _convert_to_dataframe(self, kline_data: List[List], symbol: str, timeframe: str) -> pd.DataFrame:
        """K-라인 데이터를 DataFrame으로 변환"""
        if not kline_data:
            return pd.DataFrame()
        
        # 바이비트 K-라인 형식: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        df_data = []
        for kline in kline_data:
            df_data.append({
                'timestamp': int(kline[0]),
                'open': float(kline[1]),
                'high': float(kline[2]),
                'low': float(kline[3]),
                'close': float(kline[4]),
                'volume': float(kline[5]),
                'turnover': float(kline[6]),
                'symbol': symbol,
                'timeframe': timeframe
            })
        
        df = pd.DataFrame(df_data)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    def get_symbol_data(self, symbol: str, timeframe: str = None) -> Optional[pd.DataFrame]:
        """심볼 데이터 조회"""
        if symbol not in self.symbol_data:
            return None
        
        if timeframe:
            return self.symbol_data[symbol].get(timeframe)
        else:
            # 기본적으로 1분봉 반환
            return self.symbol_data[symbol].get('1')
    
    def get_ticker_data(self, symbol: str) -> Optional[Dict]:
        """티커 데이터 조회"""
        return self.ticker_data.get(symbol)
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """최신 가격 조회"""
        ticker = self.get_ticker_data(symbol)
        if ticker:
            return float(ticker.get('lastPrice', 0))
        
        # 티커 데이터가 없으면 1분봉 데이터에서 조회
        df = self.get_symbol_data(symbol, '1')
        if df is not None and not df.empty:
            return df.iloc[-1]['close']
        
        return None
    
    def get_24h_change(self, symbol: str) -> Optional[Dict[str, float]]:
        """24시간 변화량 조회"""
        ticker = self.get_ticker_data(symbol)
        if ticker:
            return {
                'price_change': float(ticker.get('price24hPcnt', 0)) * 100,
                'volume_24h': float(ticker.get('volume24h', 0)),
                'high_24h': float(ticker.get('highPrice24h', 0)),
                'low_24h': float(ticker.get('lowPrice24h', 0))
            }
        return None
    
    async def health_check(self) -> bool:
        """데이터 수집기 상태 점검"""
        try:
            # API 연결 확인
            if not await self.test_connection():
                return False
            
            # 데이터 최신성 확인 (5분 이내)
            now = datetime.now()
            for symbol in self.config.SYMBOLS:
                if symbol not in self.last_update:
                    return False
                
                if (now - self.last_update[symbol]) > timedelta(minutes=5):
                    self.logger.warning(f"⚠️ {symbol} 데이터가 오래됨: {self.last_update[symbol]}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"상태 점검 실패: {str(e)}")
            return False
    
    def get_data_status(self) -> Dict[str, Any]:
        """데이터 상태 정보 반환"""
        status = {
            'initialized': self.is_initialized,
            'symbols_count': len(self.symbol_data),
            'last_updates': {},
            'data_sizes': {}
        }
        
        for symbol in self.symbol_data:
            if symbol in self.last_update:
                status['last_updates'][symbol] = self.last_update[symbol].isoformat()
            
            status['data_sizes'][symbol] = {}
            for timeframe in self.symbol_data[symbol]:
                df = self.symbol_data[symbol][timeframe]
                status['data_sizes'][symbol][timeframe] = len(df) if df is not None else 0
        
        return status
    
    async def close(self):
        """데이터 수집기 정리"""
        self.logger.info("🛑 데이터 수집기 종료 중...")
        # 필요시 데이터 저장, 연결 정리 등
        self.is_initialized = False
        self.logger.info("✅ 데이터 수집기 종료 완료")
