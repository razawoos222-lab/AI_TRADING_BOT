# main.py - 메인 실행 파일
import asyncio
import logging
from datetime import datetime, timedelta
import traceback
from typing import Dict, List, Optional

from config import Config
from data_collector import DataCollector
from indicator_engine import IndicatorEngine
from signal_generator import SignalGenerator
from telegram_bot import TelegramBot
from position_manager import PositionManager
from utils.logger import setup_logger

class TradingBotManager:
    """메인 트레이딩 봇 관리자 클래스"""
    
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger("TradingBot", self.config.LOG_LEVEL)
        
        # 핵심 컴포넌트 초기화
        self.data_collector = DataCollector(self.config)
        self.indicator_engine = IndicatorEngine(self.config)
        self.signal_generator = SignalGenerator(self.config)
        self.telegram_bot = TelegramBot(self.config)
        self.position_manager = PositionManager(self.config)
        
        # 상태 관리
        self.is_running = False
        self.last_signal_time = {}
        self.active_positions = {}
        
    async def initialize(self):
        """시스템 초기화"""
        try:
            self.logger.info("🚀 트레이딩 봇 초기화 시작...")
            
            # API 연결 테스트
            await self.data_collector.test_connection()
            await self.telegram_bot.initialize()
            await self.position_manager.initialize()
            
            # 초기 데이터 수집
            await self.data_collector.fetch_initial_data()
            
            self.logger.info("✅ 초기화 완료!")
            await self.telegram_bot.send_startup_message()
            
        except Exception as e:
            self.logger.error(f"❌ 초기화 실패: {str(e)}")
            raise
    
    async def run_main_loop(self):
        """메인 실행 루프"""
        self.is_running = True
        self.logger.info("🔄 메인 루프 시작...")
        
        while self.is_running:
            try:
                loop_start = datetime.now()
                
                # 1. 실시간 데이터 업데이트
                await self.update_market_data()
                
                # 2. 기술적 지표 계산  
                await self.calculate_indicators()
                
                # 3. 신호 생성 및 전송
                await self.generate_and_send_signals()
                
                # 4. 포지션 관리 (자동 관리 모드인 경우)
                await self.manage_positions()
                
                # 5. 시스템 상태 체크
                await self.system_health_check()
                
                # 실행 시간 로깅
                execution_time = (datetime.now() - loop_start).total_seconds()
                self.logger.debug(f"⏱️ 루프 실행 시간: {execution_time:.2f}초")
                
                # 다음 실행까지 대기 (1분 주기)
                await asyncio.sleep(max(0, 60 - execution_time))
                
            except Exception as e:
                self.logger.error(f"❌ 메인 루프 오류: {str(e)}")
                self.logger.error(traceback.format_exc())
                await self.telegram_bot.send_error_alert(str(e))
                await asyncio.sleep(10)  # 에러 시 10초 대기
    
    async def update_market_data(self):
        """시장 데이터 업데이트"""
        try:
            # TOP 10 코인 데이터 수집
            for symbol in self.config.SYMBOLS:
                await self.data_collector.update_symbol_data(symbol)
                
        except Exception as e:
            self.logger.error(f"데이터 업데이트 실패: {str(e)}")
            raise
    
    async def calculate_indicators(self):
        """기술적 지표 계산"""
        try:
            for symbol in self.config.SYMBOLS:
                market_data = self.data_collector.get_symbol_data(symbol)
                if market_data:
                    indicators = await self.indicator_engine.calculate_all_indicators(
                        symbol, market_data
                    )
                    self.indicator_engine.update_indicators(symbol, indicators)
                    
        except Exception as e:
            self.logger.error(f"지표 계산 실패: {str(e)}")
            raise
    
    async def generate_and_send_signals(self):
        """신호 생성 및 전송"""
        try:
            for symbol in self.config.SYMBOLS:
                # 중복 신호 방지 (최소 15분 간격)
                if self.should_skip_signal(symbol):
                    continue
                
                indicators = self.indicator_engine.get_indicators(symbol)
                signal = await self.signal_generator.generate_signal(symbol, indicators)
                
                if signal and signal.score >= self.config.MIN_SIGNAL_SCORE:
                    await self.telegram_bot.send_trading_signal(signal)
                    self.last_signal_time[symbol] = datetime.now()
                    self.logger.info(f"📊 {symbol} 신호 전송: {signal.direction} ({signal.score}점)")
                    
        except Exception as e:
            self.logger.error(f"신호 생성 실패: {str(e)}")
            raise
    
    async def manage_positions(self):
        """포지션 자동 관리"""
        try:
            # 바이비트에서 현재 포지션 조회
            current_positions = await self.position_manager.get_current_positions()
            
            for position in current_positions:
                # 자동 관리가 활성화된 포지션만 처리
                if self.position_manager.is_auto_managed(position.symbol):
                    await self.position_manager.update_position_management(position)
                    
        except Exception as e:
            self.logger.error(f"포지션 관리 실패: {str(e)}")
    
    def should_skip_signal(self, symbol: str) -> bool:
        """중복 신호 방지 체크"""
        if symbol not in self.last_signal_time:
            return False
        
        time_diff = datetime.now() - self.last_signal_time[symbol]
        return time_diff < timedelta(minutes=self.config.MIN_SIGNAL_INTERVAL)
    
    async def system_health_check(self):
        """시스템 상태 점검"""
        try:
            # API 연결 상태 체크
            if not await self.data_collector.health_check():
                self.logger.warning("⚠️ 데이터 수집 API 연결 불안정")
                await self.telegram_bot.send_warning("데이터 수집 API 연결이 불안정합니다.")
            
            # 메모리 사용량 체크 (추후 구현)
            # 디스크 사용량 체크 (추후 구현)
            
        except Exception as e:
            self.logger.error(f"시스템 상태 점검 실패: {str(e)}")
    
    async def shutdown(self):
        """정상 종료 처리"""
        self.logger.info("🛑 트레이딩 봇 종료 중...")
        self.is_running = False
        
        try:
            await self.telegram_bot.send_shutdown_message()
            await self.data_collector.close()
            await self.telegram_bot.close()
            self.logger.info("✅ 정상 종료 완료")
            
        except Exception as e:
            self.logger.error(f"종료 처리 중 오류: {str(e)}")

async def main():
    """메인 실행 함수"""
    bot = None
    try:
        # 봇 초기화 및 실행
        bot = TradingBotManager()
        await bot.initialize()
        await bot.run_main_loop()
        
    except KeyboardInterrupt:
        print("\n사용자에 의한 종료 요청...")
        
    except Exception as e:
        print(f"치명적 오류: {str(e)}")
        traceback.print_exc()
        
    finally:
        if bot:
            await bot.shutdown()

if __name__ == "__main__":
    # 이벤트 루프 실행
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램이 종료되었습니다.")
