import streamlit as st
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime
import pandas as pd
import json
import base64

class YouTubeScraper:
    def __init__(self, api_key):
        self.api_key = api_key
        self.youtube = googleapiclient.discovery.build(
            "youtube", "v3", developerKey=api_key
        )

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
            with st.progress(0) as progress_bar:
                total_videos = len(search_response["items"])
                
                for i, item in enumerate(search_response["items"]):
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

                    try:
                        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                        transcript_text = ' '.join([entry['text'] for entry in transcript])
                    except:
                        transcript_text = "자막을 불러올 수 없습니다."

                    video_data = {
                        "title": item["snippet"]["title"],
                        "video_id": video_id,
                        "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                        "channel_name": item["snippet"]["channelTitle"],
                        "channel_subscribers": channel_response["items"][0]["statistics"]["subscriberCount"],
                        "view_count": video_response["items"][0]["statistics"]["viewCount"],
                        "upload_date": item["snippet"]["publishedAt"],
                        "transcript": transcript_text
                    }
                    videos.append(video_data)
                    
                    # 진행률 업데이트
                    progress_bar.progress((i + 1) / total_videos)

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

    # 사이드바 설정
    with st.sidebar:
        st.header("검색 설정")
        api_key = st.text_input("YouTube API 키", type="password", help="YouTube Data API v3 키를 입력하세요")
        keyword = st.text_input("검색 키워드", help="검색하고 싶은 키워드를 입력하세요")
        max_results = st.slider("검색 결과 수", 1, 50, 5, help="가져올 영상의 수를 선택하세요")
        
        if st.button("검색", use_container_width=True):
            if not api_key or not keyword:
                st.error("API 키와 검색어를 모두 입력해주세요.")
            else:
                with st.spinner("검색 중..."):
                    scraper = YouTubeScraper(api_key)
                    videos, error = scraper.search_videos(keyword, max_results)
                    
                    if error:
                        st.error(f"오류가 발생했습니다: {error}")
                    else:
                        st.session_state.videos = videos
                        st.session_state.keyword = keyword
                        st.success("검색이 완료되었습니다!")

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
                    st.image(video['thumbnail'], use_column_width=True)
                
                with col2:
                    st.subheader(video['title'])
                    st.markdown(f"**채널명:** {video['channel_name']}")
                    st.markdown(f"**구독자 수:** {int(video['channel_subscribers']):,}명")
                    st.markdown(f"**조회수:** {int(video['view_count']):,}회")
                    st.markdown(f"**업로드 날짜:** {video['upload_date'][:10]}")
                    st.markdown(f"**영상 링크:** [YouTube에서 보기](https://www.youtube.com/watch?v={video['video_id']})")
                
                with st.expander("자막 보기"):
                    st.markdown(video['transcript'])
                
                st.markdown("---")

if __name__ == "__main__":
    main()