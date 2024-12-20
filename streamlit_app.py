import streamlit as st
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime
import pandas as pd
import base64
import google.generativeai as genai

class YouTubeScraper:
    def __init__(self, api_key, gemini_key):
        self.api_key = api_key
        self.youtube = googleapiclient.discovery.build(
            "youtube", "v3", developerKey=api_key
        )
        # Gemini 모델 설정
        genai.configure(api_key=gemini_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def summarize_transcript(self, transcript_text):
        """Gemini를 사용하여 자막 텍스트 요약"""
        if transcript_text == "이 영상에서는 자막을 사용할 수 없습니다.":
            return "자막이 없어 요약을 생성할 수 없습니다."
        
        try:
            prompt = f"""
            다음 유튜브 영상의 자막을 요약해주세요. 핵심 내용을 3-5개의 간단한 문장으로 정리해주세요.
            영상 자막:
            {transcript_text}
            """
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"요약 생성 중 오류가 발생했습니다: {str(e)}"

    def search_videos(self, keyword, max_results=5):
        try:
            search_response = self.youtube.search().list(
                q=keyword,
                part="id,snippet",
                maxResults=max_results,
                type="video",
                order="viewCount"
            ).execute()

            videos = []
            total_videos = len(search_response["items"])
            
            # 진행률 표시를 위한 단일 progress bar 생성
            progress_bar = st.progress(0)
            progress_text = st.empty()
                
            for i, item in enumerate(search_response["items"]):
                # 진행률 업데이트
                current_progress = (i + 1) / total_videos
                progress_bar.progress(current_progress)
                progress_text.text(f'동영상 정보 수집 중... ({i+1}/{total_videos})')
                
                video_id = item["id"]["videoId"]
                
                video_response = self.youtube.videos().list(
                    part="statistics,snippet",
                    id=video_id
                ).execute()
                
                channel_id = item["snippet"]["channelId"]
                channel_response = self.youtube.channels().list(
                    part="statistics",
                    id=channel_id
                ).execute()

                # 자막 처리 개선
                try:
                    # 먼저 한국어 자막 시도
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                    transcript_text = ' '.join([entry['text'] for entry in transcript])
                except:
                    try:
                        # 한국어 자막이 없으면 자동 생성된 한국어 자막 시도
                        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko-KR'])
                        transcript_text = ' '.join([entry['text'] for entry in transcript])
                    except:
                        try:
                            # 모든 가능한 자막 목록 확인
                            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                            
                            # 번역 가능한 자막이 있는지 확인
                            try:
                                # 영어 자막을 한국어로 번역 시도
                                translated = transcript_list.find_transcript(['en']).translate('ko')
                                transcript_text = ' '.join([entry['text'] for entry in translated.fetch()])
                            except:
                                # 가능한 첫 번째 자막을 한국어로 번역
                                first_transcript = next(iter(transcript_list))
                                translated = first_transcript.translate('ko')
                                transcript_text = ' '.join([entry['text'] for entry in translated.fetch()])
                        except:
                            transcript_text = "이 영상에서는 자막을 사용할 수 없습니다."

                # 자막 요약 생성
                summary = self.summarize_transcript(transcript_text)

                video_data = {
                    "title": item["snippet"]["title"],
                    "video_id": video_id,
                    "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                    "channel_name": item["snippet"]["channelTitle"],
                    "channel_subscribers": channel_response["items"][0]["statistics"]["subscriberCount"],
                    "view_count": video_response["items"][0]["statistics"]["viewCount"],
                    "upload_date": item["snippet"]["publishedAt"],
                    "transcript": transcript_text,
                    "summary": summary
                }
                videos.append(video_data)

            # 진행 완료 후 progress bar와 text 제거
            progress_bar.empty()
            progress_text.empty()
            
            return videos, None
        except Exception as e:
            return None, str(e)

def generate_markdown(videos, keyword):
    content = f"# YouTube 검색 결과: {keyword}\n\n"
    content += f"검색 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for video in videos:
        content += f"## {video['title']}\n\n"
        content += f"- 영상 링크: https://www.youtube.com/watch?v={video['video_id']}\n"
        content += f"- 썸네일: ![[{video['thumbnail']}]]\n"
        content += f"- 채널명: {video['channel_name']}\n"
        content += f"- 구독자 수: {int(video['channel_subscribers']):,}명\n"
        content += f"- 조회수: {int(video['view_count']):,}회\n"
        content += f"- 업로드 날짜: {video['upload_date'][:10]}\n\n"
        content += "### 영상 내용 요약\n\n"
        content += f"{video['summary']}\n\n"
        content += "### 영상 자막\n\n"
        content += f"{video['transcript']}\n\n"
        content += "---\n\n"
    
    return content

def get_download_link(content, filename):
    """마크다운 파일 다운로드 링크 생성"""
    b64 = base64.b64encode(content.encode()).decode()
    return f'<a href="data:text/markdown;base64,{b64}" download="{filename}">마크다운 파일 다운로드</a>'

def main():
    st.set_page_config(page_title="YouTube 영상 정보 수집기", page_icon="🎥", layout="wide")
    
    st.title("YouTube 영상 정보 수집기 🎥")
    st.markdown("---")

    # API 키들을 secrets에서 가져오기
    if 'api_keys' in st.secrets:
        default_youtube_key = st.secrets['api_keys']['youtube']
        default_gemini_key = st.secrets['api_keys']['gemini']
    else:
        default_youtube_key = ""
        default_gemini_key = ""
        st.warning("API 키가 설정되어 있지 않습니다. Streamlit Secrets에서 설정해주세요.")

    # 사이드바 설정
    with st.sidebar:
        st.header("검색 설정")
        youtube_api_key = st.text_input(
            "YouTube API 키", 
            value=default_youtube_key,
            type="password" if default_youtube_key else "default",
            help="YouTube Data API v3 키를 입력하세요"
        )
        gemini_api_key = st.text_input(
            "Gemini API 키",
            value=default_gemini_key,
            type="password" if default_gemini_key else "default",
            help="Gemini API 키를 입력하세요"
        )
        keyword = st.text_input("검색 키워드", help="검색하고 싶은 키워드를 입력하세요")
        max_results = st.slider("검색 결과 수", 1, 50, 15, help="가져올 영상의 수를 선택하세요")
        
        search_button = st.button("검색", use_container_width=True)
        
        if search_button:
            if not youtube_api_key:
                st.error("YouTube API 키를 입력해주세요.")
            elif not gemini_api_key:
                st.error("Gemini API 키를 입력해주세요.")
            elif not keyword:
                st.error("검색어를 입력해주세요.")
            else:
                with st.spinner("검색 중..."):
                    try:
                        scraper = YouTubeScraper(youtube_api_key, gemini_api_key)
                        videos, error = scraper.search_videos(keyword, max_results)
                        
                        if error:
                            st.error(f"오류가 발생했습니다: {error}")
                        else:
                            st.session_state.videos = videos
                            st.session_state.keyword = keyword
                            st.success("검색이 완료되었습니다!")
                    except Exception as e:
                        st.error(f"예기치 않은 오류가 발생했습니다: {str(e)}")

    # 메인 컨텐츠
    if 'videos' in st.session_state and st.session_state.videos:
        videos = st.session_state.videos
        keyword = st.session_state.keyword

        # 마크다운 다운로드 버튼
        markdown_content = generate_markdown(videos, keyword)
        filename = f"youtube_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        st.markdown(get_download_link(markdown_content, filename), unsafe_allow_html=True)
        st.markdown("---")

        # 검색 결과 표시
        for video in videos:
            with st.container():
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.image(video['thumbnail'], use_container_width=True)
                
                with col2:
                    st.subheader(video['title'])
                    st.markdown(f"**채널명:** {video['channel_name']}")
                    st.markdown(f"**구독자 수:** {int(video['channel_subscribers']):,}명")
                    st.markdown(f"**조회수:** {int(video['view_count']):,}회")
                    st.markdown(f"**업로드 날짜:** {video['upload_date'][:10]}")
                    st.markdown(f"**영상 링크:** [YouTube에서 보기](https://www.youtube.com/watch?v={video['video_id']})")
                
                with st.expander("내용 요약"):
                    st.markdown(video['summary'])
                    
                with st.expander("전체 자막"):
                    st.markdown(video['transcript'])
                
                st.markdown("---")

if __name__ == "__main__":
    main()
