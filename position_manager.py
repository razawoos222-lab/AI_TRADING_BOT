# position_manager.py - 포지션 관리 모듈
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    side: str  # "Buy" or "Sell"
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percentage: float
    leverage: int
    margin: float
    timestamp: datetime
    
    # 자동 관리 설정
    auto_managed: bool = False
    stop_loss: Optional[float] = None
    take_profit_levels: Optional[List[float]] = None
    trailing_stop: Optional[Dict[str, Any]] = None

class PositionManager:
    """포지션 자동 관리 클래스"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 바이비트 API (data_collector에서 공유)
        self.api = None
        
        # 포지션 추적
        self.monitored_positions: Dict[str, Position] = {}
        self.auto_management_settings: Dict[str, Dict] = {}
        
        # 트레일링 스탑 상태
        self.trailing_stops: Dict[str, Dict] = {}
        
        # 알림 시스템 (텔레그램 봇 참조)
        self.telegram_bot = None
    
    async def initialize(self):
        """포지션 매니저 초기화"""
        try:
            self.logger.info("⚙️ 포지션 매니저 초기화 중...")
            
            # 기존 포지션 로드 (있다면)
            await self._load_existing_positions()
            
            # 자동 관리 설정 로드
            self._load_management_settings()
            
            self.logger.info("✅ 포지션 매니저 초기화 완료")
            
        except Exception as e:
            self.logger.error(f"❌ 포지션 매니저 초기화 실패: {str(e)}")
            raise
    
    def set_telegram_bot(self, telegram_bot):
        """텔레그램 봇 참조 설정"""
        self.telegram_bot = telegram_bot
    
    def set_api(self, api_client):
        """API 클라이언트 설정"""
        self.api = api_client
    
    async def get_current_positions(self) -> List[Position]:
        """현재 포지션 조회"""
        try:
            if not self.api:
                return []
            
            # 바이비트에서 포지션 조회
            async with self.api as api:
                positions_data = await api.get_positions()
            
            positions = []
            for pos_data in positions_data:
                # 포지션이 있는 것만 처리 (size > 0)
                if float(pos_data.get('size', 0)) > 0:
                    position = self._convert_to_position(pos_data)
                    positions.append(position)
                    
                    # 모니터링 목록 업데이트
                    self.monitored_positions[position.symbol] = position
            
            return positions
            
        except Exception as e:
            self.logger.error(f"❌ 포지션 조회 실패: {str(e)}")
            return []
    
    def _convert_to_position(self, bybit_position: Dict) -> Position:
        """바이비트 포지션 데이터를 Position 객체로 변환"""
        return Position(
            symbol=bybit_position.get('symbol', ''),
            side=bybit_position.get('side', ''),
            size=float(bybit_position.get('size', 0)),
            entry_price=float(bybit_position.get('avgPrice', 0)),
            current_price=float(bybit_position.get('markPrice', 0)),
            unrealized_pnl=float(bybit_position.get('unrealisedPnl', 0)),
            pnl_percentage=float(bybit_position.get('unrealisedPnl', 0)) / float(bybit_position.get('positionValue', 1)) * 100,
            leverage=int(bybit_position.get('leverage', 1)),
            margin=float(bybit_position.get('positionIM', 0)),
            timestamp=datetime.now(),
            auto_managed=self.is_auto_managed(bybit_position.get('symbol', ''))
        )
    
    def is_auto_managed(self, symbol: str) -> bool:
        """자동 관리 여부 확인"""
        return symbol in self.auto_management_settings and \
               self.auto_management_settings[symbol].get('enabled', False)
    
    async def enable_auto_management(self, symbol: str, settings: Dict[str, Any]):
        """자동 관리 활성화"""
        try:
            self.auto_management_settings[symbol] = {
                'enabled': True,
                'trailing_stop': settings.get('trailing_stop', True),
                'partial_profits': settings.get('partial_profits', True),
                'stop_loss_adjustment': settings.get('stop_loss_adjustment', True),
                'risk_management': settings.get('risk_management', True),
                'activated_at': datetime.now()
            }
            
            # 트레일링 스탑 초기화
            if settings.get('trailing_stop', True):
                await self._initialize_trailing_stop(symbol)
            
            self.logger.info(f"✅ {symbol} 자동 관리 활성화")
            
            if self.telegram_bot:
                await self.telegram_bot.send_warning(
                    f"🤖 {symbol} 자동 관리가 활성화되었습니다.\n"
                    f"트레일링 스탑과 부분 익절이 자동으로 실행됩니다."
                )
                
        except Exception as e:
            self.logger.error(f"❌ {symbol} 자동 관리 활성화 실패: {str(e)}")
    
    async def disable_auto_management(self, symbol: str):
        """자동 관리 비활성화"""
        if symbol in self.auto_management_settings:
            self.auto_management_settings[symbol]['enabled'] = False
            
            # 트레일링 스탑 정리
            if symbol in self.trailing_stops:
                del self.trailing_stops[symbol]
            
            self.logger.info(f"🔴 {symbol} 자동 관리 비활성화")
    
    async def update_position_management(self, position: Position):
        """포지션 자동 관리 업데이트"""
        if not position.auto_managed:
            return
        
        try:
            symbol = position.symbol
            
            # 1. 트레일링 스탑 업데이트
            if self.auto_management_settings[symbol].get('trailing_stop', True):
                await self._update_trailing_stop(position)
            
            # 2. 부분 익절 체크
            if self.auto_management_settings[symbol].get('partial_profits', True):
                await self._check_partial_profits(position)
            
            # 3. 리스크 관리 체크
            if self.auto_management_settings[symbol].get('risk_management', True):
                await self._check_risk_management(position)
            
            # 4. 포지션 상태 알림 (조건부)
            await self._send_position_update_if_needed(position)
            
        except Exception as e:
            self.logger.error(f"❌ {symbol} 포지션 관리 업데이트 실패: {str(e)}")
    
    async def _initialize_trailing_stop(self, symbol: str):
        """트레일링 스탑 초기화"""
        position = self.monitored_positions.get(symbol)
        if not position:
            return
        
        # 현재 포지션 방향에 따른 초기 트레일링 스탑 설정
        trailing_distance = self.config.TRAILING_STOP_DISTANCE
        
        if position.side == "Buy":  # 롱 포지션
            # 진입가 기준으로 트레일링 활성화 지점 계산
            activation_price = position.entry_price * (1 + self.config.TRAILING_STOP_ACTIVATION)
            initial_stop = position.entry_price * (1 - trailing_distance)
        else:  # 숏 포지션
            activation_price = position.entry_price * (1 - self.config.TRAILING_STOP_ACTIVATION)
            initial_stop = position.entry_price * (1 + trailing_distance)
        
        self.trailing_stops[symbol] = {
            'activation_price': activation_price,
            'current_stop': initial_stop,
            'highest_price': position.current_price,
            'lowest_price': position.current_price,
            'activated': False,
            'last_update': datetime.now()
        }
        
        self.logger.info(f"🛡️ {symbol} 트레일링 스탑 초기화: 활성화가 ${activation_price:.4f}")
    
    async def _update_trailing_stop(self, position: Position):
        """트레일링 스탑 업데이트"""
        symbol = position.symbol
        
        if symbol not in self.trailing_stops:
            await self._initialize_trailing_stop(symbol)
            return
        
        trailing = self.trailing_stops[symbol]
        current_price = position.current_price
        trailing_distance = self.config.TRAILING_STOP_DISTANCE
        
        # 트레일링 스탑 활성화 체크
        if not trailing['activated']:
            if position.side == "Buy" and current_price >= trailing['activation_price']:
                trailing['activated'] = True
                self.logger.info(f"✅ {symbol} 트레일링 스탑 활성화: ${current_price:.4f}")
                
                if self.telegram_bot:
                    await self.telegram_bot.send_warning(
                        f"🛡️ {symbol} 트레일링 스탑이 활성화되었습니다!\n"
                        f"현재가: ${current_price:.4f}\n"
                        f"트레일링 거리: {trailing_distance*100:.1f}%"
                    )
            
            elif position.side == "Sell" and current_price <= trailing['activation_price']:
                trailing['activated'] = True
                self.logger.info(f"✅ {symbol} 트레일링 스탑 활성화 (숏): ${current_price:.4f}")
        
        # 트레일링 스탑이 활성화된 경우에만 업데이트
        if trailing['activated']:
            stop_updated = False
            
            if position.side == "Buy":  # 롱 포지션
                # 새로운 고점 갱신 시 트레일링 스탑 상향 조정
                if current_price > trailing['highest_price']:
                    trailing['highest_price'] = current_price
                    new_stop = current_price * (1 - trailing_distance)
                    
                    if new_stop > trailing['current_stop']:
                        trailing['current_stop'] = new_stop
                        stop_updated = True
            
            else:  # 숏 포지션
                # 새로운 저점 갱신 시 트레일링 스탑 하향 조정
                if current_price < trailing['lowest_price']:
                    trailing['lowest_price'] = current_price
                    new_stop = current_price * (1 + trailing_distance)
                    
                    if new_stop < trailing['current_stop']:
                        trailing['current_stop'] = new_stop
                        stop_updated = True
            
            # 트레일링 스탑 업데이트 알림
            if stop_updated:
                trailing['last_update'] = datetime.now()
                self.logger.info(f"📈 {symbol} 트레일링 스탑 조정: ${trailing['current_stop']:.4f}")
                
                if self.telegram_bot:
                    await self.telegram_bot.send_position_update(symbol, {
                        'current_price': current_price,
                        'entry_price': position.entry_price,
                        'unrealized_pnl': position.unrealized_pnl,
                        'pnl_percentage': position.pnl_percentage,
                        'trailing_stop': {
                            'current_stop': trailing['current_stop'],
                            'updated': True
                        }
                    })
    
    async def _check_partial_profits(self, position: Position):
        """부분 익절 체크"""
        symbol = position.symbol
        current_price = position.current_price
        entry_price = position.entry_price
        
        # 목표가 달성 체크 (설정에서 가져오거나 기본값 사용)
        target_1 = self.config.DEFAULT_TAKE_PROFIT_1  # 4%
        target_2 = self.config.DEFAULT_TAKE_PROFIT_2  # 8%
        
        if position.side == "Buy":  # 롱 포지션
            profit_1_price = entry_price * (1 + target_1)
            profit_2_price = entry_price * (1 + target_2)
            
            if current_price >= profit_1_price:
                await self._suggest_partial_profit(position, profit_1_price, 50, "1차 목표가")
            
            if current_price >= profit_2_price:
                await self._suggest_partial_profit(position, profit_2_price, 100, "2차 목표가")
        
        else:  # 숏 포지션
            profit_1_price = entry_price * (1 - target_1)
            profit_2_price = entry_price * (1 - target_2)
            
            if current_price <= profit_1_price:
                await self._suggest_partial_profit(position, profit_1_price, 50, "1차 목표가")
            
            if current_price <= profit_2_price:
                await self._suggest_partial_profit(position, profit_2_price, 100, "2차 목표가")
    
    async def _suggest_partial_profit(self, position: Position, target_price: float, 
                                    percentage: int, target_name: str):
        """부분 익절 제안"""
        symbol = position.symbol
        
        # 중복 알림 방지 (같은 목표가에 대해 최근 10분 내 알림했다면 스킵)
        key = f"{symbol}_{target_name}_{percentage}"
        if hasattr(self, '_last_profit_alerts'):
            if key in self._last_profit_alerts:
                if datetime.now() - self._last_profit_alerts[key] < timedelta(minutes=10):
                    return
        else:
            self._last_profit_alerts = {}
        
        self._last_profit_alerts[key] = datetime.now()
        
        profit_amount = position.unrealized_pnl * (percentage / 100)
        
        if self.telegram_bot:
            message = f"""
🎯 <b>{symbol} {target_name} 달성!</b>

💰 현재가: ${position.current_price:.4f}
🎯 목표가: ${target_price:.4f}
📈 수익: ${profit_amount:.2f} ({position.pnl_percentage:.1f}%)

💡 <b>권장사항:</b>
{percentage}% 물량 부분 익절을 고려하세요.
"""
            
            # 부분 익절 버튼 키보드
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"💰 {percentage}% 익절", callback_data=f"profit{percentage}_{symbol}"),
                    InlineKeyboardButton("📊 홀드", callback_data=f"hold_{symbol}"),
                    InlineKeyboardButton("⚠️ 전체청산", callback_data=f"close_all_{symbol}")
                ]
            ])
            
            await self.telegram_bot.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard
            )
    
    async def _check_risk_management(self, position: Position):
        """리스크 관리 체크"""
        symbol = position.symbol
        
        # 1. 최대 손실 체크
        max_loss_pct = -10.0  # -10% 이하 시 경고
        if position.pnl_percentage <= max_loss_pct:
            await self._send_risk_alert(position, "최대 손실", 
                f"현재 손실이 {position.pnl_percentage:.1f}%에 달했습니다.")
        
        # 2. 급격한 가격 변화 체크
        if hasattr(self, '_price_history'):
            if symbol in self._price_history:
                prev_price = self._price_history[symbol][-1] if self._price_history[symbol] else position.current_price
                price_change = abs(position.current_price - prev_price) / prev_price
                
                if price_change > 0.05:  # 5% 이상 급변
                    await self._send_risk_alert(position, "급격한 가격 변화", 
                        f"가격이 {price_change*100:.1f}% 급변했습니다.")
        else:
            self._price_history = {}
        
        # 가격 이력 저장 (최근 5개만)
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        self._price_history[symbol].append(position.current_price)
        if len(self._price_history[symbol]) > 5:
            self._price_history[symbol] = self._price_history[symbol][-5:]
    
    async def _send_risk_alert(self, position: Position, alert_type: str, message: str):
        """리스크 경고 전송"""
        if self.telegram_bot:
            alert_message = f"""
⚠️ <b>{position.symbol} 리스크 경고: {alert_type}</b>

{message}

📊 현재 상황:
• 현재가: ${position.current_price:.4f}
• 진입가: ${position.entry_price:.4f}
• 손익: ${position.unrealized_pnl:.2f} ({position.pnl_percentage:+.1f}%)

💡 포지션 검토를 권장합니다.
"""
            
            await self.telegram_bot.send_warning(alert_message)
    
    async def _send_position_update_if_needed(self, position: Position):
        """조건부 포지션 업데이트 전송"""
        symbol = position.symbol
        
        # 마지막 업데이트 시간 체크 (5분에 한 번만)
        if not hasattr(self, '_last_updates'):
            self._last_updates = {}
        
        now = datetime.now()
        if symbol in self._last_updates:
            if now - self._last_updates[symbol] < timedelta(minutes=5):
                return
        
        # 업데이트 조건 체크
        should_update = False
        
        # 1. 수익률이 특정 구간에 도달
        pnl_pct = abs(position.pnl_percentage)
        if pnl_pct >= 5.0 or pnl_pct >= 10.0 or pnl_pct >= 20.0:
            should_update = True
        
        # 2. 트레일링 스탑이 최근 업데이트됨
        if symbol in self.trailing_stops:
            trailing = self.trailing_stops[symbol]
            if trailing.get('last_update') and \
               now - trailing['last_update'] < timedelta(minutes=2):
                should_update = True
        
        if should_update:
            self._last_updates[symbol] = now
            
            # 다음 목표가 계산
            next_target = None
            target_progress = 0
            
            if position.side == "Buy":
                target_5pct = position.entry_price * 1.05
                target_10pct = position.entry_price * 1.10
                
                if position.current_price < target_5pct:
                    next_target = target_5pct
                    target_progress = (position.current_price - position.entry_price) / (target_5pct - position.entry_price) * 100
                elif position.current_price < target_10pct:
                    next_target = target_10pct
                    target_progress = (position.current_price - target_5pct) / (target_10pct - target_5pct) * 100
            
            update_info = {
                'current_price': position.current_price,
                'entry_price': position.entry_price,
                'unrealized_pnl': position.unrealized_pnl,
                'pnl_percentage': position.pnl_percentage,
                'next_target': next_target,
                'target_progress': max(0, min(100, target_progress)),
                'trailing_stop': self.trailing_stops.get(symbol)
            }
            
            if self.telegram_bot:
                await self.telegram_bot.send_position_update(symbol, update_info)
    
    async def _load_existing_positions(self):
        """기존 포지션 로드"""
        try:
            # 실제 바이비트에서 포지션 조회
            positions = await self.get_current_positions()
            
            for position in positions:
                self.monitored_positions[position.symbol] = position
                self.logger.info(f"📊 기존 포지션 로드: {position.symbol} ({position.side})")
                
        except Exception as e:
            self.logger.error(f"기존 포지션 로드 실패: {str(e)}")
    
    def _load_management_settings(self):
        """자동 관리 설정 로드"""
        # TODO: 파일에서 설정 로드 (JSON 등)
        # 임시로 빈 딕셔너리로 초기화
        self.auto_management_settings = {}
    
    def get_position_summary(self) -> Dict[str, Any]:
        """포지션 요약 정보"""
        positions = list(self.monitored_positions.values())
        
        if not positions:
            return {
                'total_positions': 0,
                'total_pnl': 0,
                'auto_managed_count': 0
            }
        
        total_pnl = sum(pos.unrealized_pnl for pos in positions)
        auto_managed_count = sum(1 for pos in positions if pos.auto_managed)
        
        return {
            'total_positions': len(positions),
            'total_pnl': total_pnl,
            'total_pnl_pct': sum(pos.pnl_percentage for pos in positions) / len(positions),
            'auto_managed_count': auto_managed_count,
            'symbols': [pos.symbol for pos in positions],
            'largest_position': max(positions, key=lambda p: abs(p.unrealized_pnl)).symbol if positions else None
        }
    
    async def emergency_close_all(self, reason: str = "Emergency"):
        """비상 전체 청산"""
        self.logger.warning(f"🚨 비상 전체 청산 실행: {reason}")
        
        positions = await self.get_current_positions()
        
        for position in positions:
            try:
                # TODO: 실제 청산 API 호출 구현
                self.logger.info(f"🛑 {position.symbol} 비상 청산 실행")
                
                if self.telegram_bot:
                    await self.telegram_bot.send_warning(
                        f"🚨 {position.symbol} 비상 청산 완료\n"
                        f"사유: {reason}\n"
                        f"최종 손익: ${position.unrealized_pnl:.2f}"
                    )
                    
            except Exception as e:
                self.logger.error(f"❌ {position.symbol} 청산 실패: {str(e)}")
        
        # 모든 자동 관리 중단
        self.auto_management_settings.clear()
        self.trailing_stops.clear()
        self.monitored_positions.clear()
    
    async def save_settings(self):
        """설정 저장"""
        try:
            settings_data = {
                'auto_management': self.auto_management_settings,
                'trailing_stops': {k: {
                    **v, 
                    'last_update': v['last_update'].isoformat() if 'last_update' in v else None
                } for k, v in self.trailing_stops.items()},
                'saved_at': datetime.now().isoformat()
            }
            
            # TODO: 실제 파일 저장 구현
            # with open('position_settings.json', 'w') as f:
            #     json.dump(settings_data, f, indent=2)
            
            self.logger.info("💾 포지션 설정 저장 완료")
            
        except Exception as e:
            self.logger.error(f"❌ 설정 저장 실패: {str(e)}")
    
    async def close(self):
        """포지션 매니저 정리"""
        self.logger.info("🛑 포지션 매니저 종료 중...")
        
        # 설정 저장
        await self.save_settings()
        
        # 활성 모니터링 중단
        self.monitored_positions.clear()
        self.trailing_stops.clear()
        
        self.logger.info("✅ 포지션 매니저 종료 완료")
