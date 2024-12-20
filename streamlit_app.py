import streamlit as st
from urllib.parse import urlparse, parse_qs
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime
import pandas as pd
import base64
import google.generativeai as genai

class YouTubeAnalyzer:
    def __init__(self, api_key, gemini_key):
        self.api_key = api_key
        self.youtube = googleapiclient.discovery.build(
            "youtube", "v3", developerKey=api_key
        )
        genai.configure(api_key=gemini_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def get_video_id(self, url):
        """YouTube URL에서 video_id 추출"""
        parsed_url = urlparse(url)
        if parsed_url.hostname == 'youtu.be':
            return parsed_url.path[1:]
        if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed_url.path == '/watch':
                return parse_qs(parsed_url.query)['v'][0]
        return None

    def analyze_single_video(self, video_url):
        """단일 영상 분석"""
        video_id = self.get_video_id(video_url)
        if not video_id:
            return None, "잘못된 YouTube URL입니다."

        try:
            # 영상 정보 가져오기
            video_response = self.youtube.videos().list(
                part="snippet,statistics",
                id=video_id
            ).execute()

            if not video_response['items']:
                return None, "영상을 찾을 수 없습니다."

            video_data = video_response['items'][0]
            
            # 자막 가져오기
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                transcript_text = ' '.join([entry['text'] for entry in transcript])
                timestamps = [
                    {
                        'time': entry['start'],
                        'text': entry['text'],
                        'duration': entry['duration']
                    }
                    for entry in transcript
                ]
            except:
                transcript_text = "자막을 불러올 수 없습니다."
                timestamps = []

            # 요약 및 분석 생성
            title = video_data['snippet']['title']
            summary = self.generate_summary(transcript_text, title)
            structured_note = self.generate_structured_note(transcript_text, title)
            blog_post = self.generate_blog_post(title, transcript_text, summary)

            return {
                'title': title,
                'video_id': video_id,
                'thumbnail': video_data['snippet']['thumbnails']['high']['url'],
                'channel_name': video_data['snippet']['channelTitle'],
                'view_count': video_data['statistics']['viewCount'],
                'transcript': transcript_text,
                'timestamps': timestamps,
                'summary': summary,
                'structured_note': structured_note,
                'blog_post': blog_post
            }, None

        except Exception as e:
            return None, str(e)

    def generate_summary(self, text, title):
        """텍스트 요약 생성"""
        prompt = f"""
        다음 내용을 간단히 요약해주세요:
        제목: {title}
        내용: {text}
        
        형식:
        - 3-5개의 핵심 포인트
        - 각 포인트는 1-2문장으로 명확하게
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except:
            return "요약을 생성할 수 없습니다."

    def generate_structured_note(self, text, title):
        """구조화된 노트 생성"""
        prompt = f"""
        다음 내용을 학습 노트 형식으로 정리해주세요:
        제목: {title}
        내용: {text}
        
        다음 구조로 작성해주세요:
        1. 핵심 개념
        2. 주요 논점
        3. 세부 내용 정리
        4. 중요 포인트
        5. 추가 학습 사항
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except:
            return "노트를 생성할 수 없습니다."

    def generate_blog_post(self, title, text, summary):
        """블로그 포스트 생성"""
        prompt = f"""
        다음 내용을 블로그 포스트 형식으로 작성해주세요:
        제목: {title}
        요약: {summary}
        내용: {text}
        
        다음 구조로 작성:
        1. 흥미로운 제목
        2. 도입부
        3. 주요 내용 (2-3개 섹션)
        4. 결론
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except:
            return "블로그 포스트를 생성할 수 없습니다."

def main():
    st.set_page_config(layout="wide", page_title="YouTube 분석기")

    # 사이드바 - 네비게이션
    with st.sidebar:
        st.title("🎥 YouTube 분석기")
        nav = st.radio(
            "메뉴",
            ["🏠 홈", "🔍 발견", "📚 내 지식"],
            captions=["시작 페이지", "YouTube 영상 검색/분석", "저장된 노트 보기"]
        )

    # API 키 설정
    if 'api_keys' in st.secrets:
        youtube_key = st.secrets['api_keys']['youtube']
        gemini_key = st.secrets['api_keys']['gemini']
    else:
        youtube_key = st.session_state.get('youtube_key', '')
        gemini_key = st.session_state.get('gemini_key', '')

    # 메인 컨텐츠
    if nav == "🏠 홈":
        st.title("YouTube 영상 분석 도구")
        st.write("YouTube 영상을 분석하고 학습 자료로 변환하세요!")
        
        # API 키 입력
        with st.expander("API 키 설정"):
            youtube_key = st.text_input("YouTube API 키", value=youtube_key, type="password")
            gemini_key = st.text_input("Gemini API 키", value=gemini_key, type="password")
            if st.button("저장"):
                st.session_state['youtube_key'] = youtube_key
                st.session_state['gemini_key'] = gemini_key
                st.success("API 키가 저장되었습니다!")

    elif nav == "🔍 발견":
        st.title("YouTube 영상 검색 및 분석")
        tab1, tab2 = st.tabs(["🔍 영상 검색", "🎯 단일 영상 분석"])
        
        with tab1:
            st.subheader("키워드로 영상 검색")
            col1, col2 = st.columns([4, 1])
            with col1:
                keyword = st.text_input("검색어를 입력하세요")
            with col2:
                search_button = st.button("검색", use_container_width=True)
            
            if keyword and search_button:
                with st.spinner("검색 중..."):
                    try:
                        scraper = YouTubeScraper(youtube_key, gemini_key)
                        videos, error = scraper.search_videos(keyword, max_results=10)
                        
                        if error:
                            st.error(f"오류가 발생했습니다: {error}")
                        else:
                            st.success(f"{len(videos)}개의 영상을 찾았습니다!")
                            
                            for video in videos:
                                with st.container():
                                    col1, col2, col3 = st.columns([1, 2, 1])
                                    
                                    with col1:
                                        st.image(video.get('thumbnail', ''), use_container_width=True)
                                    
                                    with col2:
                                        st.subheader(video.get('title', '제목 없음'))
                                        st.write(f"채널: {video.get('channel_name', '채널명 없음')}")
                                        st.write(f"조회수: {int(video.get('view_count', 0)):,}회")
                                    
                                    with col3:
                                        if st.button("저장", key=f"save_{video['video_id']}"):
                                            save_to_knowledge_base(video)
                                            st.success("내 지식에 저장되었습니다!")
                                    
                                    st.markdown("---")
                    except Exception as e:
                        st.error(f"예기치 않은 오류가 발생했습니다: {str(e)}")
            
        with tab2:
    st.subheader("YouTube 영상 분석")
    col1, col2 = st.columns([4, 1])
    with col1:
        video_url = st.text_input("YouTube 영상 URL을 입력하세요")
    with col2:
        analyze_button = st.button("분석", use_container_width=True)
    
    if video_url and analyze_button:
        progress_bar = st.progress(0)
        progress_text = st.empty()
        
        # 분석 진행 상태 표시
        for i in range(5):
            progress_bar.progress((i + 1) * 20)
            if i == 0:
                progress_text.text("영상 정보 가져오는 중...")
            elif i == 1:
                progress_text.text("자막 추출 중...")
            elif i == 2:
                progress_text.text("요약 생성 중...")
            elif i == 3:
                progress_text.text("노트 작성 중...")
            elif i == 4:
                progress_text.text("블로그 글 생성 중...")
            time.sleep(0.5)
        
        analyzer = YouTubeAnalyzer(youtube_key, gemini_key)
        video_data, error = analyzer.analyze_single_video(video_url)
        
        progress_bar.empty()
        progress_text.empty()
        
        if error:
            st.error(error)
        else:
            # 영상 정보 표시
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.image(video_data['thumbnail'], use_container_width=True)
            with col2:
                st.subheader(video_data['title'])
                st.write(f"채널: {video_data['channel_name']}")
                st.write(f"조회수: {int(video_data['view_count']):,}회")
            with col3:
                save_button = st.button("저장", key=f"save_single_{video_data['video_id']}")
                if save_button:
                    with st.spinner("저장 중..."):
                        save_to_knowledge_base(video_data)
                        time.sleep(1)  # 저장 진행 표시를 위한 지연
                        st.success("내 지식에 저장되었습니다!")
            
            # 탭으로 분석 결과 표시
            tabs = st.tabs(["📝 요약 노트", "📜 스크립트", "📚 블로그"])
            
            with tabs[0]:
                st.markdown(video_data['structured_note'])
            
            with tabs[1]:
                st.markdown(video_data['transcript'])
            
            with tabs[2]:
                st.markdown(video_data['blog_post'])

# 내 지식 탭 부분 수정
elif nav == "📚 내 지식":
    st.title("저장된 노트")
    
    if 'knowledge_base' not in st.session_state:
        st.session_state.knowledge_base = []
    
    if not st.session_state.knowledge_base:
        st.write("저장된 노트가 없습니다.")
    else:
        for idx, video in enumerate(st.session_state.knowledge_base):
            with st.container():
                # 기본 정보 표시
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    st.image(video.get('thumbnail', ''), use_container_width=True)
                with col2:
                    st.subheader(video.get('title', '제목 없음'))
                    st.write(f"채널: {video.get('channel_name', '채널명 없음')}")
                with col3:
                    if st.button("삭제", key=f"delete_{idx}"):
                        with st.spinner("삭제 중..."):
                            st.session_state.knowledge_base.pop(idx)
                            time.sleep(0.5)  # 삭제 진행 표시를 위한 지연
                            st.rerun()
                
                # 자세히 보기 확장 패널
                with st.expander("자세히 보기"):
                    detail_tabs = st.tabs(["📝 요약 노트", "📜 스크립트", "📚 블로그"])
                    
                    with detail_tabs[0]:
                        st.markdown(video.get('structured_note', '요약 노트가 없습니다.'))
                    
                    with detail_tabs[1]:
                        st.markdown(video.get('transcript', '스크립트가 없습니다.'))
                    
                    with detail_tabs[2]:
                        st.markdown(video.get('blog_post', '블로그 글이 없습니다.'))
                
                st.markdown("---")
                
def save_to_knowledge_base(video_data):
    if 'knowledge_base' not in st.session_state:
        st.session_state.knowledge_base = []
    
    # 중복 체크
    if not any(v.get('video_id') == video_data.get('video_id') for v in st.session_state.knowledge_base):
        st.session_state.knowledge_base.append(video_data)

if __name__ == "__main__":
    main()
