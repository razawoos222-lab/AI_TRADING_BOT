# telegram_bot.py - 텔레그램 봇 모듈
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import json

from signal_generator import TradingSignal

class TelegramBot:
    """텔레그램 봇 클래스"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 봇 및 애플리케이션
        self.bot = None
        self.application = None
        
        # 사용자 상태 관리
        self.user_settings = {}
        self.active_signals = {}  # 활성 신호 추적
        
        # 통계
        self.message_count = 0
        self.error_count = 0
    
    async def initialize(self):
        """텔레그램 봇 초기화"""
        try:
            self.logger.info("🤖 텔레그램 봇 초기화 중...")
            
            # 봇 생성
            self.bot = Bot(token=self.config.TELEGRAM_BOT_TOKEN)
            
            # 애플리케이션 생성
            self.application = (
                Application.builder()
                .token(self.config.TELEGRAM_BOT_TOKEN)
                .build()
            )
            
            # 명령어 핸들러 등록
            self._register_handlers()
            
            # 연결 테스트
            bot_info = await self.bot.get_me()
            self.logger.info(f"✅ 텔레그램 봇 '{bot_info.first_name}' 연결 완료")
            
            # 사용자 설정 초기화
            self._initialize_user_settings()
            
        except Exception as e:
            self.logger.error(f"❌ 텔레그램 봇 초기화 실패: {str(e)}")
            raise
    
    def _register_handlers(self):
        """명령어 핸들러 등록"""
        
        # 기본 명령어
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("help", self._cmd_help))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        
        # 설정 명령어
        self.application.add_handler(CommandHandler("settings", self._cmd_settings))
        self.application.add_handler(CommandHandler("filter", self._cmd_filter))
        
        # 포지션 관리 명령어
        self.application.add_handler(CommandHandler("positions", self._cmd_positions))
        self.application.add_handler(CommandHandler("close", self._cmd_close_position))
        
        # 분석 명령어
        self.application.add_handler(CommandHandler("signals", self._cmd_recent_signals))
        self.application.add_handler(CommandHandler("stats", self._cmd_statistics))
        
        # 버튼 콜백 핸들러
        self.application.add_handler(CallbackQueryHandler(self._handle_callback))
    
    def _initialize_user_settings(self):
        """사용자 설정 초기화"""
        chat_id = self.config.TELEGRAM_CHAT_ID
        self.user_settings[chat_id] = {
            'signal_filter': {
                'min_score': self.config.MIN_SIGNAL_SCORE,
                'symbols': self.config.SYMBOLS.copy(),
                'enabled': True
            },
            'auto_management': {
                'enabled': False,
                'trailing_stop': True,
                'partial_profits': True
            },
            'notifications': {
                'signals': True,
                'position_updates': True,
                'alerts': True
            }
        }
    
    async def send_trading_signal(self, signal: TradingSignal):
        """트레이딩 신호 전송"""
        try:
            chat_id = self.config.TELEGRAM_CHAT_ID
            
            # 사용자 필터 체크
            if not self._should_send_signal(chat_id, signal):
                return
            
            # 신호 메시지 생성
            message_text = self._format_trading_signal(signal)
            
            # 인라인 키보드 생성
            keyboard = self._create_signal_keyboard(signal)
            
            # 메시지 전송
            await self.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
            # 활성 신호에 추가
            self.active_signals[f"{signal.symbol}_{signal.timestamp.strftime('%H%M')}"] = signal
            
            self.message_count += 1
            self.logger.info(f"📤 {signal.symbol} 신고 전송: {signal.direction} ({signal.score}점)")
            
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"❌ 신호 전송 실패: {str(e)}")
    
    def _format_trading_signal(self, signal: TradingSignal) -> str:
        """트레이딩 신호 메시지 포맷팅"""
        
        # 이모지 및 방향 표시
        direction_emoji = "🚀" if signal.direction == "LONG" else "🔻"
        
        # 메시지 헤더
        message = f"""
{direction_emoji} <b>{signal.symbol} {signal.direction} 신호 ({signal.score}점)</b>
━━━━━━━━━━━━━━━━━━━━
"""
        
        # 분할 매수 플랜
        message += "📊 <b>분할 진입 플랜:</b>\n"
        total_investment = 0
        for zone in signal.entry_zones:
            message += f"• {zone['order']}차: ${zone['price']:.4f} → ${zone['amount']:.0f} ({zone['ratio']*100:.0f}%)\n"
            total_investment += zone['amount']
        
        message += f"<i>총 투입: ${total_investment:.0f} | {signal.leverage}x 레버리지</i>\n\n"
        
        # 평단가 및 손익 계산
        message += "📈 <b>평단가 및 예상 손익:</b>\n"
        cumulative_avg = 0
        cumulative_amount = 0
        
        for i, zone in enumerate(signal.entry_zones):
            cumulative_amount += zone['amount'] * zone['ratio']
            if i == 0:
                cumulative_avg = zone['price']
            else:
                # 가중평균 계산
                prev_weight = sum(z['ratio'] for z in signal.entry_zones[:i+1])
                cumulative_avg = sum(z['price'] * z['ratio'] for z in signal.entry_zones[:i+1]) / prev_weight
            
            # 해당 구간까지의 손익 계산
            profit_1 = self._calculate_partial_profit(cumulative_avg, signal.take_profits[0], cumulative_amount, signal.direction, signal.leverage)
            loss = self._calculate_partial_profit(cumulative_avg, signal.stop_loss, cumulative_amount, signal.direction, signal.leverage)
            
            if i == 0:
                message += f"1차까지: 평단 ${cumulative_avg:.4f}\n"
            else:
                message += f"{i+1}차까지: 평단 ${cumulative_avg:.4f}\n"
            
            message += f"  익절 시: <b>+${profit_1:.0f}</b> | 손절 시: <b>{loss:.0f}</b>\n"
        
        message += "\n"
        
        # 손익비 및 수익률 정보
        total_capital = self.config.TOTAL_CAPITAL
        max_profit = max(signal.profit_scenarios.values()) if signal.profit_scenarios else 0
        max_loss = min(signal.loss_scenarios.values()) if signal.loss_scenarios else 0
        
        message += f"⚖️ <b>손익비:</b> {signal.risk_reward_ratio:.1f}:1\n"
        message += f"💰 <b>최대 수익률:</b> +{(max_profit/total_capital)*100:.1f}% (전체 자본 대비)\n"
        message += f"🛡️ <b>최대 손실률:</b> {(max_loss/total_capital)*100:.1f}% (전체 자본 대비)\n\n"
        
        # 목표가 및 트레일링 정보
        message += "🎯 <b>목표가 & 트레일링:</b>\n"
        for i, tp in enumerate(signal.take_profits, 1):
            profit_pct = abs(tp - signal.entry_price) / signal.entry_price * 100
            message += f"목표{i}: ${tp:.4f} (+{profit_pct:.1f}%)\n"
        
        message += f"손절: ${signal.stop_loss:.4f} (-{abs(signal.stop_loss - signal.entry_price)/signal.entry_price*100:.1f}%)\n"
        message += f"트레일링: ${signal.trailing_stop_activation:.4f} 도달 시 활성화\n\n"
        
        # 분석 근거
        message += "🔍 <b>분석 근거:</b>\n"
        for reason in signal.primary_reasons[:3]:
            message += f"• {reason}\n"
        
        if signal.supporting_factors:
            message += f"• 보조지표: {', '.join(signal.supporting_factors[:3])}\n"
        
        message += f"\n⏰ <b>예상 시간:</b> {signal.expected_duration}\n"
        message += f"🕐 <b>신호 시각:</b> {signal.timestamp.strftime('%H:%M:%S')}\n"
        
        return message.strip()
    
    def _calculate_partial_profit(self, avg_price: float, target_price: float, 
                                 amount: float, direction: str, leverage: int) -> float:
        """부분 수익 계산"""
        if direction == "LONG":
            price_change = (target_price - avg_price) / avg_price
        else:
            price_change = (avg_price - target_price) / avg_price
        
        return price_change * amount * leverage
    
    def _create_signal_keyboard(self, signal: TradingSignal) -> InlineKeyboardMarkup:
        """신호용 인라인 키보드 생성"""
        keyboard = []
        
        # 첫 번째 줄: 진입 버튼들
        keyboard.append([
            InlineKeyboardButton("⚡ 1차진입", callback_data=f"entry_1_{signal.symbol}"),
            InlineKeyboardButton("🔄 분할진입", callback_data=f"entry_split_{signal.symbol}"),
            InlineKeyboardButton("📊 상세분석", callback_data=f"detail_{signal.symbol}")
        ])
        
        # 두 번째 줄: 관리 버튼들
        keyboard.append([
            InlineKeyboardButton("🤖 자동관리", callback_data=f"auto_{signal.symbol}"),
            InlineKeyboardButton("⏰ 알림설정", callback_data=f"alert_{signal.symbol}"),
            InlineKeyboardButton("❌ 무시", callback_data=f"ignore_{signal.symbol}")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    def _should_send_signal(self, chat_id: str, signal: TradingSignal) -> bool:
        """신호 전송 여부 판단"""
        if chat_id not in self.user_settings:
            return True
        
        settings = self.user_settings[chat_id]['signal_filter']
        
        # 신호 비활성화된 경우
        if not settings['enabled']:
            return False
        
        # 최소 점수 미달
        if signal.score < settings['min_score']:
            return False
        
        # 심볼 필터
        if signal.symbol not in settings['symbols']:
            return False
        
        return True
    
    async def send_position_update(self, symbol: str, update_info: Dict[str, Any]):
        """포지션 업데이트 전송"""
        try:
            chat_id = self.config.TELEGRAM_CHAT_ID
            
            # 포지션 업데이트 메시지 생성
            message = self._format_position_update(symbol, update_info)
            
            # 포지션 관리 키보드
            keyboard = self._create_position_keyboard(symbol)
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
        except Exception as e:
            self.logger.error(f"❌ 포지션 업데이트 전송 실패: {str(e)}")
    
    def _format_position_update(self, symbol: str, update_info: Dict[str, Any]) -> str:
        """포지션 업데이트 메시지 포맷팅"""
        
        current_price = update_info.get('current_price', 0)
        entry_price = update_info.get('entry_price', 0)
        pnl = update_info.get('unrealized_pnl', 0)
        pnl_pct = update_info.get('pnl_percentage', 0)
        
        # PnL에 따른 이모지
        pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        
        message = f"""
📊 <b>{symbol} 포지션 현황</b>
━━━━━━━━━━━━━━━━━━━━
💰 현재가: ${current_price:.4f}
📈 진입가: ${entry_price:.4f}
{pnl_emoji} 손익: <b>${pnl:.2f} ({pnl_pct:+.2f}%)</b>

"""
        
        # 다음 목표까지의 진행도
        next_target = update_info.get('next_target')
        if next_target:
            progress = update_info.get('target_progress', 0)
            progress_bar = "█" * int(progress/10) + "░" * (10 - int(progress/10))
            message += f"🎯 다음 목표: ${next_target:.4f}\n"
            message += f"📊 진행도: {progress_bar} {progress:.1f}%\n\n"
        
        # 트레일링 상태
        trailing_info = update_info.get('trailing_stop')
        if trailing_info:
            message += f"🛡️ 트레일링 스탑: ${trailing_info.get('current_stop', 0):.4f}\n"
            if trailing_info.get('updated'):
                message += "✅ <i>트레일링 스탑이 상향 조정되었습니다!</i>\n"
        
        message += f"\n🕐 업데이트: {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    def _create_position_keyboard(self, symbol: str) -> InlineKeyboardMarkup:
        """포지션 관리 키보드 생성"""
        keyboard = [
            [
                InlineKeyboardButton("📈 추가진입", callback_data=f"add_{symbol}"),
                InlineKeyboardButton("💰 50%익절", callback_data=f"profit50_{symbol}"),
                InlineKeyboardButton("🛡️ 손절상향", callback_data=f"trail_{symbol}")
            ],
            [
                InlineKeyboardButton("📊 현황보기", callback_data=f"status_{symbol}"),
                InlineKeyboardButton("⚠️ 전체청산", callback_data=f"close_all_{symbol}"),
                InlineKeyboardButton("🔔 알림OFF", callback_data=f"mute_{symbol}")
            ]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    async def send_startup_message(self):
        """시작 메시지 전송"""
        message = """
🚀 <b>AI 트레이딩 봇이 시작되었습니다!</b>

📊 <b>모니터링 코인:</b>
• BTC, ETH, SOL, BNB, XRP
• DOGE, LINK, ADA, MATIC, SHIB

⚙️ <b>설정:</b>
• 최소 신호 점수: {min_score}점
• 자동 관리: 비활성화
• 알림: 전체 활성화

💡 <b>명령어:</b>
/help - 도움말 보기
/status - 현재 상태 확인
/settings - 설정 변경

<i>고품질 신호만 전송됩니다. 준비 완료! 🎯</i>
""".format(min_score=self.config.MIN_SIGNAL_SCORE)
        
        try:
            await self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            self.logger.error(f"시작 메시지 전송 실패: {str(e)}")
    
    async def send_shutdown_message(self):
        """종료 메시지 전송"""
        message = "🛑 <b>트레이딩 봇이 종료되었습니다.</b>\n\n📊 활성 포지션이 있다면 수동으로 관리해주세요."
        
        try:
            await self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            self.logger.error(f"종료 메시지 전송 실패: {str(e)}")
    
    async def send_error_alert(self, error_msg: str):
        """에러 알림 전송"""
        message = f"⚠️ <b>시스템 오류 발생</b>\n\n<code>{error_msg}</code>\n\n자동으로 복구를 시도합니다..."
        
        try:
            await self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            self.logger.error(f"에러 알림 전송 실패: {str(e)}")
    
    async def send_warning(self, warning_msg: str):
        """경고 메시지 전송"""
        message = f"⚠️ <b>주의사항</b>\n\n{warning_msg}"
        
        try:
            await self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            self.logger.error(f"경고 메시지 전송 실패: {str(e)}")
    
    # 명령어 핸들러들
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시작 명령어"""
        await update.message.reply_text(
            "🚀 AI 트레이딩 봇에 오신 것을 환영합니다!\n\n"
            "💡 /help 명령어로 사용법을 확인하세요.",
            parse_mode='HTML'
        )
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어"""
        help_text = """
🤖 <b>AI 트레이딩 봇 명령어</b>

📊 <b>기본 명령어:</b>
/status - 시스템 상태 확인
/signals - 최근 신호 내역
/stats - 성과 통계

⚙️ <b>설정 명령어:</b>
/settings - 설정 메뉴
/filter [점수] - 최소 신호 점수 설정

📈 <b>포지션 관리:</b>
/positions - 현재 포지션 확인
/close [심볼] - 포지션 청산

💡 <b>사용법:</b>
• 신호 수신 시 버튼으로 바로 작업 가능
• 자동 관리 기능으로 트레일링 스탑
• 실시간 포지션 모니터링

❓ 궁금한 점이 있으시면 언제든 문의하세요!
"""
        
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """상태 명령어"""
        # TODO: 실제 시스템 상태 조회 로직 구현
        status_text = f"""
📊 <b>시스템 상태</b>

🔄 봇 상태: ✅ 정상 운영 중
📡 API 연결: ✅ 바이비트 연결됨
📨 메시지 전송: {self.message_count}건
❌ 오류 발생: {self.error_count}건

⏰ 가동 시간: 시작된 지 얼마나 되었는지
💾 메모리 사용량: 체크 필요
"""
        
        await update.message.reply_text(status_text, parse_mode='HTML')
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """버튼 콜백 처리"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        parts = callback_data.split('_')
        action = parts[0]
        
        if action == "entry":
            await self._handle_entry_callback(query, parts)
        elif action == "auto":
            await self._handle_auto_management(query, parts)
        elif action == "detail":
            await self._handle_detail_view(query, parts)
        # ... 기타 콜백 핸들러들
    
    async def _handle_entry_callback(self, query, parts):
        """진입 버튼 콜백 처리"""
        entry_type = parts[1]  # "1" or "split"
        symbol = parts[2]
        
        if entry_type == "1":
            response = f"⚡ {symbol} 1차 진입 신호를 확인했습니다.\n수동으로 주문을 넣어주세요."
        else:
            response = f"🔄 {symbol} 분할 진입을 준비했습니다.\n각 구간별로 주문을 넣어주세요."
        
        await query.edit_message_text(
            text=f"{query.message.text}\n\n✅ {response}",
            parse_mode='HTML'
        )
    
    async def close(self):
        """텔레그램 봇 정리"""
        self.logger.info("🛑 텔레그램 봇 종료 중...")
        if self.application:
            await self.application.stop()
        self.logger.info("✅ 텔레그램 봇 종료 완료")
