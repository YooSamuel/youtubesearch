import streamlit as st
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import pandas as pd
import base64
import google.generativeai as genai
import time

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

    def search_videos(self, keyword, search_filters=None, max_results=10):
        """키워드로 영상 검색 (기본 정보만)"""
        try:
            # 검색 필터 적용
            published_after = None
            if search_filters and 'time_range' in search_filters:
                if search_filters['time_range'] == '지난 1시간':
                    published_after = (datetime.utcnow() - timedelta(hours=1)).isoformat('T') + 'Z'
                elif search_filters['time_range'] == '오늘':
                    published_after = (datetime.utcnow() - timedelta(days=1)).isoformat('T') + 'Z'
                elif search_filters['time_range'] == '이번주':
                    published_after = (datetime.utcnow() - timedelta(weeks=1)).isoformat('T') + 'Z'
                elif search_filters['time_range'] == '이번달':
                    published_after = (datetime.utcnow() - timedelta(days=30)).isoformat('T') + 'Z'
                elif search_filters['time_range'] == '올해':
                    published_after = (datetime.utcnow() - timedelta(days=365)).isoformat('T') + 'Z'

            search_params = {
                'q': keyword,
                'part': 'id,snippet',
                'maxResults': max_results,
                'type': 'video',
                'order': 'relevance'
            }

            if published_after:
                search_params['publishedAfter'] = published_after

            search_response = self.youtube.search().list(**search_params).execute()

            videos = []
            total_videos = len(search_response["items"])
            
            for item in search_response["items"]:
                video_id = item["id"]["videoId"]
                
                video_response = self.youtube.videos().list(
                    part="statistics,snippet",
                    id=video_id
                ).execute()
                
                video_data = {
                    "title": item["snippet"]["title"],
                    "video_id": video_id,
                    "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                    "channel_name": item["snippet"]["channelTitle"],
                    "view_count": video_response["items"][0]["statistics"]["viewCount"],
                    "upload_date": item["snippet"]["publishedAt"],
                    "description": item["snippet"]["description"]
                }
                videos.append(video_data)
            
            return videos, None
        except Exception as e:
            return None, str(e)

    def analyze_video(self, video_id):
        """단일 영상 상세 분석"""
        try:
            video_response = self.youtube.videos().list(
                part="snippet,statistics",
                id=video_id
            ).execute()

            if not video_response['items']:
                return None, "영상을 찾을 수 없습니다."

            video_data = video_response['items'][0]
            
            # 자막 추출
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                transcript_text = ' '.join([entry['text'] for entry in transcript])
            except:
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko-KR'])
                    transcript_text = ' '.join([entry['text'] for entry in transcript])
                except:
                    transcript_text = "자막을 불러올 수 없습니다."

            title = video_data['snippet']['title']
            
            # 분석 결과 생성
            analysis_result = {
                "title": title,
                "video_id": video_id,
                "thumbnail": video_data['snippet']['thumbnails']['high']['url'],
                "channel_name": video_data['snippet']['channelTitle'],
                "transcript": transcript_text,
                "summary": self.generate_summary(transcript_text, title),
                "blog_post": self.generate_blog_post(title, transcript_text)
            }
            
            return analysis_result, None
        except Exception as e:
            return None, str(e)

    def generate_summary(self, text, title):
        """텍스트 요약 생성"""
        try:
            prompt = f"""
            다음 내용을 간단히 요약해주세요:
            제목: {title}
            내용: {text}
            
            형식:
            - 3-5개의 핵심 포인트
            - 각 포인트는 1-2문장으로 명확하게
            """
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"요약 생성 중 오류가 발생했습니다: {str(e)}"

    def generate_blog_post(self, title, text):
        """블로그 포스트 생성"""
        try:
            # 메인 키워드 추출 (제목에서 주요 키워드 추출)
            keywords = title.split()
            main_keyword = max(keywords, key=len) if keywords else "주제"

            prompt = f"""
            당신은 네이버 블로그 상위 노출 전문가입니다. 아래 영상의 내용을 기반으로
            네이버 검색 시 최상단에 노출될 수 있는 블로그 글을 작성해주세요.

            제목: {title}
            메인 키워드: {main_keyword}
            내용: {text}

            작성 조건:
            1. 길이: 한글 기준 2000자 이상
            2. '{main_keyword}' 키워드를 자연스럽게 7회 이상 사용
            3. 단락은 200-300자 내외로 구분
            4. 명확한 소제목 사용 (단, '도입부', '본론', '결론' 등의 형식적 단어 사용 금지)
            5. 구어체 사용 (예: ~해요, ~네요, ~거든요)
            6. SEO 최적화를 위한 자연스러운 키워드 배치

            글의 구조:
            1. 시작: 주제 소개 및 독자의 흥미 유발
            2. 전개: 3-4개의 소주제로 구분하여 상세 내용 설명
            3. 마무리: 핵심 내용 요약 및 독자와의 공감대 형성
            """
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"블로그 포스트 생성 중 오류가 발생했습니다: {str(e)}"

def save_to_knowledge_base(video_data):
    """지식 베이스에 저장"""
    if 'knowledge_base' not in st.session_state:
        st.session_state.knowledge_base = []
    
    # 중복 체크
    if not any(v.get('video_id') == video_data.get('video_id') for v in st.session_state.knowledge_base):
        st.session_state.knowledge_base.append(video_data)

def main():
    st.set_page_config(layout="wide", page_title="YouTube 분석기")

    # 사이드바 - 네비게이션
    with st.sidebar:
        st.title("🎥 YouTube 분석기")
        nav = st.radio(
            "메뉴",
            ["🏠 홈", "🔍 발견", "📊 분석", "📚 내 지식"],
            captions=["시작 페이지", "YouTube 영상 검색", "영상 상세 분석", "저장된 노트 보기"]
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
        st.title("YouTube 영상 검색")
        
        # 검색 필터
        with st.expander("검색 필터"):
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("구분")
                search_type = st.selectbox("영상 종류", ["전체", "뉴스", "웹사이트"])
            with col2:
                st.subheader("업로드 날짜")
                time_range = st.selectbox(
                    "기간 선택",
                    ["전체 날짜", "지난 1시간", "오늘", "이번주", "이번달", "올해"]
                )

        # 검색창
        col1, col2 = st.columns([4, 1])
        with col1:
            keyword = st.text_input("검색어를 입력하세요")
        with col2:
            search_button = st.button("검색", use_container_width=True)
        
        if keyword and search_button:
            search_filters = {
                "type": search_type if search_type != "전체" else None,
                "time_range": time_range if time_range != "전체 날짜" else None
            }
            
            with st.spinner("검색 중..."):
                try:
                    analyzer = YouTubeAnalyzer(youtube_key, gemini_key)
                    videos, error = analyzer.search_videos(keyword, search_filters)
                    
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
                                    st.write(f"업로드: {video.get('upload_date', '')[:10]}")
                                
                                with col3:
                                    video_url = f"https://youtube.com/watch?v={video['video_id']}"
                                    if st.button("분석하기", key=f"analyze_{video['video_id']}"):
                                        st.session_state['analysis_url'] = video_url
                                        st.session_state['current_tab'] = "📊 분석"
                                        st.rerun()
                                
                                st.markdown("---")
                except Exception as e:
                    st.error(f"예기치 않은 오류가 발생했습니다: {str(e)}")

    elif nav == "📊 분석":
       st.title("YouTube 영상 분석")
       
       # URL 입력
       video_url = st.text_input(
           "YouTube 영상 URL을 입력하세요",
           value=st.session_state.get('analysis_url', '')
       )
       
       analyze_button = st.button("분석", use_container_width=True)
       
       if video_url and analyze_button:
           with st.spinner("영상 분석 중..."):
               analyzer = YouTubeAnalyzer(youtube_key, gemini_key)
               video_id = analyzer.get_video_id(video_url)
               
               if not video_id:
                   st.error("올바른 YouTube URL을 입력해주세요.")
               else:
                   analysis_result, error = analyzer.analyze_video(video_id)
                   if error:
                       st.error(error)
                   else:
                       col1, col2 = st.columns([1, 3])
                       with col1:
                           st.image(analysis_result['thumbnail'], use_container_width=True)
                       with col2:
                           st.subheader(analysis_result['title'])
                           st.write(f"채널: {analysis_result['channel_name']}")

                       # 분석 결과 탭으로 표시
                       tabs = st.tabs(["📝 요약", "📜 스크립트", "📚 블로그"])
                       with tabs[0]:
                           st.markdown(analysis_result['summary'])
                       with tabs[1]:
                           st.markdown(analysis_result['transcript'])
                       with tabs[2]:
                           st.markdown(analysis_result['blog_post'])
                       
                       # 저장 버튼
                       if st.button("내 지식에 저장", key="save_analysis"):
                           with st.spinner("저장 중..."):
                               save_to_knowledge_base(analysis_result)
                               st.success("내 지식에 저장되었습니다!")

    elif nav == "📚 내 지식":
        st.title("저장된 노트")
       
        if 'knowledge_base' not in st.session_state:
            st.session_state.knowledge_base = []
       
        if not st.session_state.knowledge_base:
            st.write("저장된 노트가 없습니다.")
        else:
            for idx, video in enumerate(st.session_state.knowledge_base):
                with st.container():
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
                            time.sleep(0.5)
                            st.rerun()
                   
                   # 자세히 보기 확장 패널
                with st.expander("자세히 보기"):
                    detail_tabs = st.tabs(["📝 요약", "📜 스크립트", "📚 블로그"])
                    with detail_tabs[0]:
                        st.markdown(video.get('summary', '요약을 생성할 수 없습니다.'))
                    with detail_tabs[1]:
                        st.markdown(video.get('transcript', '스크립트를 불러올 수 없습니다.'))
                    with detail_tabs[2]:
                        st.markdown(video.get('blog_post', '블로그 글을 생성할 수 없습니다.'))
                   
                   st.markdown("---")

if __name__ == "__main__":
   main()
