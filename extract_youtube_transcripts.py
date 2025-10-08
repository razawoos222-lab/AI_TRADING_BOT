"""
YouTube 자막 추출기 (무료)
- URL 리스트만 입력하면 자막 자동 추출
- 디버깅 쉬운 구조
- 에러 발생 시 상세 로그
"""

from youtube_transcript_api import YouTubeTranscriptApi
import os
from datetime import datetime

# ==================== 설정 ====================
OUTPUT_FOLDER = "transcripts"  # 결과 저장 폴더
LOG_FILE = "extraction_log.txt"  # 로그 파일

# ==================== 유틸리티 함수 ====================

def log_message(message, also_print=True):
    """로그 기록 (파일 + 화면)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    # 화면 출력
    if also_print:
        print(message)
    
    # 파일 저장
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    except:
        pass  # 로그 실패해도 계속 진행

def extract_video_id(url):
    """
    YouTube URL에서 video_id 추출
    
    지원 형식:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - VIDEO_ID (직접 입력)
    """
    try:
        url = url.strip()
        
        # watch?v= 형식
        if "watch?v=" in url:
            video_id = url.split("watch?v=")[1].split("&")[0]
            return video_id
        
        # youtu.be/ 형식
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
            return video_id
        
        # 직접 ID 입력
        elif len(url) == 11:  # YouTube ID는 11자
            return url
        
        else:
            log_message(f"   ⚠️  URL 형식 인식 불가: {url}")
            return None
            
    except Exception as e:
        log_message(f"   ❌ Video ID 추출 실패: {e}")
        return None

def get_transcript(video_id):
    """
    자막 가져오기 (한국어 → 영어 → 자동생성 순)
    
    Returns:
        (자막텍스트, 언어코드) 또는 (None, None)
    """
    try_languages = [
        ['ko'],           # 한국어
        ['en'],           # 영어
        ['ko', 'en'],     # 한국어 또는 영어
    ]
    
    for languages in try_languages:
        try:
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=languages
            )
            
            # 성공
            full_text = '\n'.join([
                f"[{int(item['start'])}s] {item['text']}"
                for item in transcript
            ])
            
            detected_lang = languages[0]
            return full_text, detected_lang
            
        except Exception:
            continue  # 다음 언어 시도
    
    # 모두 실패
    return None, None

def save_transcript(video_id, transcript_text, language):
    """
    자막을 텍스트 파일로 저장
    
    파일명: transcripts/VIDEO_ID.txt
    """
    try:
        # 폴더 생성
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)
            log_message(f"📁 폴더 생성: {OUTPUT_FOLDER}/")
        
        # 파일 저장
        filepath = os.path.join(OUTPUT_FOLDER, f"{video_id}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write(f"YouTube 자막 추출\n")
            f.write(f"Video ID: {video_id}\n")
            f.write(f"URL: https://www.youtube.com/watch?v={video_id}\n")
            f.write(f"추출 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"언어: {language}\n")
            f.write("="*70 + "\n\n")
            f.write(transcript_text)
        
        file_size = os.path.getsize(filepath) / 1024  # KB
        return filepath, file_size
        
    except Exception as e:
        log_message(f"   ❌ 파일 저장 실패: {e}")
        return None, 0

# ==================== 메인 실행 ====================

def main():
    """메인 실행 함수"""
    
    print("\n" + "="*70)
    print("🎥 YouTube 자막 추출기 (무료)")
    print("="*70 + "\n")
    
    log_message("="*70, also_print=False)
    log_message("새로운 추출 작업 시작", also_print=False)
    log_message("="*70, also_print=False)
    
    # ==================== URL 리스트 ====================
    # 여기에 YouTube URL을 추가하세요
    
    video_urls = [
        "https://youtu.be/HC2iUkI8Dh8?si=M7rOpSCkpGMv7qIh",
        "https://www.youtube.com/watch?v=3N9Cox8u8SQ&list=PLgLx8FktlY2Or9S_SIw7VGHaJy3Lq4VIG&index=2",
        "https://www.youtube.com/watch?v=Zc81ldv5EV4"
    ]
    
    # ==================== 처리 시작 ====================
    
    total = len(video_urls)
    print(f"📋 총 {total}개 영상 처리 시작\n")
    log_message(f"총 {total}개 영상 처리")
    
    success_count = 0
    fail_count = 0
    results = []
    
    for idx, url in enumerate(video_urls, 1):
        print(f"\n[{idx}/{total}] 처리 중...")
        print(f"URL: {url}")
        log_message(f"\n[{idx}/{total}] {url}")
        
        # Step 1: Video ID 추출
        video_id = extract_video_id(url)
        if not video_id:
            print("   ❌ Video ID 추출 실패 - 건너뜀")
            log_message("   ❌ Video ID 추출 실패")
            fail_count += 1
            results.append((url, "실패", "Video ID 추출 실패"))
            continue
        
        print(f"   📹 Video ID: {video_id}")
        log_message(f"   Video ID: {video_id}")
        
        # Step 2: 자막 가져오기
        print(f"   📝 자막 추출 중...")
        transcript_text, language = get_transcript(video_id)
        
        if not transcript_text:
            print(f"   ❌ 자막 없음 - 건너뜀")
            log_message(f"   ❌ 자막 없음")
            fail_count += 1
            results.append((url, "실패", "자막 없음"))
            continue
        
        char_count = len(transcript_text)
        print(f"   ✅ 자막 추출 완료 ({char_count:,}자, 언어: {language})")
        log_message(f"   자막 추출: {char_count}자, 언어: {language}")
        
        # Step 3: 파일 저장
        print(f"   💾 파일 저장 중...")
        filepath, file_size = save_transcript(video_id, transcript_text, language)
        
        if filepath:
            print(f"   ✅ 저장 완료: {filepath} ({file_size:.1f} KB)")
            log_message(f"   저장: {filepath} ({file_size:.1f} KB)")
            success_count += 1
            results.append((url, "성공", f"{file_size:.1f} KB"))
        else:
            print(f"   ❌ 파일 저장 실패")
            fail_count += 1
            results.append((url, "실패", "파일 저장 실패"))
    
    # ==================== 결과 요약 ====================
    
    print("\n" + "="*70)
    print("🎉 처리 완료!")
    print("="*70)
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {fail_count}개")
    print(f"📁 저장 위치: {os.path.abspath(OUTPUT_FOLDER)}/")
    print(f"📄 로그 파일: {LOG_FILE}")
    print("="*70 + "\n")
    
    log_message(f"\n처리 완료: 성공 {success_count}개, 실패 {fail_count}개")
    
    # 상세 결과
    if results:
        print("\n📊 상세 결과:")
        print("-" * 70)
        for idx, (url, status, detail) in enumerate(results, 1):
            status_icon = "✅" if status == "성공" else "❌"
            print(f"{idx}. {status_icon} {status}: {detail}")
            print(f"   URL: {url[:50]}...")
        print("-" * 70)
    
    print("\n✨ 다음 단계:")
    print(f"1. {OUTPUT_FOLDER}/ 폴더에서 txt 파일들 확인")
    print(f"2. Claude에게 파일 내용 전달")
    print(f"3. 종합 분석 요청\n")
    
    input("Enter를 눌러 종료...")

# ==================== 실행 ====================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자가 중단했습니다.")
        log_message("사용자 중단")
    except Exception as e:
        print(f"\n\n❌ 예상치 못한 오류 발생:")
        print(f"{e}")
        log_message(f"치명적 오류: {e}")
        input("\nEnter를 눌러 종료...")
