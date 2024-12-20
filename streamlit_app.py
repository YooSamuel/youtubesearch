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

    def summarize_transcript(self, transcript_text, title):
        """일반적인 내용 요약 생성"""
        if transcript_text == "이 영상에서는 자막을 사용할 수 없습니다.":
            return "자막이 없어 요약을 생성할 수 없습니다."
        
        try:
            prompt = f"""
            다음 유튜브 영상의 자막을 간단히 요약해주세요:
            
            제목: {title}
            자막: {transcript_text}
            
            요청사항:
            1. 3-5개의 핵심 포인트로 요약
            2. 쉽고 명확한 언어 사용
            3. 중요한 내용 위주로 정리
            """
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"요약 생성 중 오류가 발생했습니다: {str(e)}"

    def generate_structured_summary(self, transcript_text, title):
        """구조적/교육적 관점의 요약 생성"""
        if transcript_text == "이 영상에서는 자막을 사용할 수 없습니다.":
            return "자막이 없어 요약을 생성할 수 없습니다."
        
        try:
            prompt = f"""
            다음 유튜브 영상의 내용을 교육적/구조적 관점에서 분석해주세요:
            
            제목: {title}
            내용: {transcript_text}
            
            다음 형식으로 작성해주세요:
            1. 주요 개념 정리
            2. 핵심 논점 분석
            3. 단계별 설명 (있는 경우)
            4. 실제 적용 방안
            5. 추가 학습 포인트
            
            전문적이고 교육적인 톤으로 작성하되, 이해하기 쉽게 설명해주세요.
            """
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"구조적 요약 생성 중 오류가 발생했습니다: {str(e)}"

    def generate_blog_post(self, title, transcript_text, summary):
        """블로그 포스트 생성"""
        try:
            prompt = f"""
            다음 유튜브 영상의 정보를 바탕으로 블로그 포스트를 작성해주세요:
            
            제목: {title}
            요약: {summary}
            내용: {transcript_text}
            
            다음 구조로 작성해주세요:
            1. 눈에 띄는 제목
            2. 흥미로운 도입부
            3. 핵심 내용 설명 (2-3개 섹션)
            4. 실제 적용 방법이나 시사점
            5. 결론 및 정리
            
            블로그 스타일로 자연스럽고 흥미롭게 작성해주세요.
            각 섹션은 소제목을 포함하고, 읽기 쉽게 단락을 나눠주세요.
            """
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"블로그 포스트 생성 중 오류가 발생했습니다: {str(e)}"

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
            
            progress_bar = st.progress(0)
            progress_text = st.empty()
                
            for i, item in enumerate(search_response["items"]):
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

                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                    transcript_text = ' '.join([entry['text'] for entry in transcript])
                except:
                    try:
                        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko-KR'])
                        transcript_text = ' '.join([entry['text'] for entry in transcript])
                    except:
                        try:
                            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                            try:
                                translated = transcript_list.find_transcript(['en']).translate('ko')
                                transcript_text = ' '.join([entry['text'] for entry in translated.fetch()])
                            except:
                                first_transcript = next(iter(transcript_list))
                                translated = first_transcript.translate('ko')
                                transcript_text = ' '.join([entry['text'] for entry in translated.fetch()])
                        except:
                            transcript_text = "이 영상에서는 자막을 사용할 수 없습니다."

                title = item["snippet"]["title"]
                summary = self.summarize_transcript(transcript_text, title)
                structured_summary = self.generate_structured_summary(transcript_text, title)
                blog_post = self.generate_blog_post(title, transcript_text, summary)

                video_data = {
                    "title": title,
                    "video_id": video_id,
                    "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                    "channel_name": item["snippet"]["channelTitle"],
                    "channel_subscribers": channel_response["items"][0]["statistics"]["subscriberCount"],
                    "view_count": video_response["items"][0]["statistics"]["viewCount"],
                    "upload_date": item["snippet"]["publishedAt"],
                    "transcript": transcript_text,
                    "summary": summary,
                    "structured_summary": structured_summary,
                    "blog_post": blog_post
                }
                videos.append(video_data)

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
        
        # 영상 요약 부분
        content += "### 영상 요약\n\n"
        content += f"{video.get('summary', '요약을 생성할 수 없습니다.')}\n\n"
        
        # 구조적 요약 부분
        content += "### 구조적 요약\n\n"
        content += f"{video.get('structured_summary', '구조적 요약을 생성할 수 없습니다.')}\n\n"
        
        # 블로그 포스트 부분
        content += "### 블로그 포스트\n\n"
        content += f"{video.get('blog_post', '블로그 포스트를 생성할 수 없습니다.')}\n\n"
        
        # 전체 스크립트 부분
        content += "### 전체 스크립트\n\n"
        content += f"{video.get('transcript', '스크립트를 불러올 수 없습니다.')}\n\n"
        
        content += "---\n\n"
    
    return content

def get_download_link(content, filename):
    b64 = base64.b64encode(content.encode()).decode()
    return f'<a href="data:text/markdown;base64,{b64}" download="{filename}">마크다운 파일 다운로드</a>'

def main():
    st.set_page_config(page_title="YouTube 영상 정보 수집기", page_icon="🎥", layout="wide")
    
    st.title("YouTube 영상 정보 수집기 🎥")
    st.markdown("---")

    if 'api_keys' in st.secrets:
        default_youtube_key = st.secrets['api_keys']['youtube']
        default_gemini_key = st.secrets['api_keys']['gemini']
    else:
        default_youtube_key = ""
        default_gemini_key = ""
        st.warning("API 키가 설정되어 있지 않습니다. Streamlit Secrets에서 설정해주세요.")

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

     if 'videos' in st.session_state and st.session_state.videos:
        videos = st.session_state.videos
        keyword = st.session_state.keyword

        markdown_content = generate_markdown(videos, keyword)
        filename = f"youtube_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        st.markdown(get_download_link(markdown_content, filename), unsafe_allow_html=True)
        st.markdown("---")

        for video in videos:
            with st.container():
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.image(video.get('thumbnail', ''), use_container_width=True)
                
                with col2:
                    st.subheader(video.get('title', '제목 없음'))
                    st.markdown(f"**채널명:** {video.get('channel_name', '채널명 없음')}")
                    st.markdown(f"**구독자 수:** {int(video.get('channel_subscribers', 0)):,}명")
                    st.markdown(f"**조회수:** {int(video.get('view_count', 0)):,}회")
                    st.markdown(f"**업로드 날짜:** {video.get('upload_date', '')[:10]}")
                    st.markdown(f"**영상 링크:** [YouTube에서 보기](https://www.youtube.com/watch?v={video.get('video_id', '')})")
                
                tab1, tab2, tab3 = st.tabs(["영상 요약", "전체 스크립트", "블로그 포스트"])
                
                with tab1:
                    col3, col4 = st.columns(2)
                    with col3:
                        st.markdown("### 일반 요약")
                        st.markdown(video.get('summary', '요약을 생성할 수 없습니다.'))
                    with col4:
                        st.markdown("### 구조적 요약")
                        st.markdown(video.get('structured_summary', '구조적 요약을 생성할 수 없습니다.'))
                
                with tab2:
                    st.markdown("### 전체 스크립트")
                    st.markdown(video.get('transcript', '스크립트를 불러올 수 없습니다.'))
                
                with tab3:
                    st.markdown(video.get('blog_post', '블로그 포스트를 생성할 수 없습니다.'))
                
                st.markdown("---")

if __name__ == "__main__":
    main()
