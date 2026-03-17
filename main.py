from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import json
import os
import re
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
# 유튜브 API 키 환경변수 추가
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

# 1. 시그널(signal.bz) 사이트에서 한국 실시간 검색어를 직접 뽑아오는 함수
def get_realtime_keywords():
    try:
        url = "https://signal.bz/news"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        response = urllib.request.urlopen(req, timeout=10)
        html = response.read().decode('utf-8')
        
        keywords_raw = re.findall(r'class="rank-text">([^<]+)</span>', html)
        
        keywords = []
        for kw in keywords_raw:
            if kw not in keywords:
                keywords.append(kw)
            if len(keywords) >= 10:
                break
                
        if not keywords:
            raise Exception("시그널 사이트에서 키워드를 찾지 못했습니다.")
            
        return keywords
        
    except Exception as e:
        print(f"키워드 추출 실패: {e}")
        return ["날씨", "비트코인", "환율", "삼성전자", "넷플릭스", "손흥민", "이재명", "아이유", "뉴진스", "GPT"]

# 2. 네이버 데이터랩 API로 점수 매기기
def fetch_naver_trends(keyword_groups):
    if not keyword_groups: 
        return {'results': []}
        
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    body = json.dumps({
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": keyword_groups
    }).encode('utf-8')
    
    try:
        req = urllib.request.Request(
            "https://openapi.naver.com/v1/datalab/search",
            data=body,
            method='POST',
            headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
                'Content-Type': 'application/json'
            }
        )
        response = urllib.request.urlopen(req, timeout=10)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"네이버 API 에러: {e}")
        return {'results': []}

# 3. 유튜브 Hype(인기 급상승) 동영상 리스트 가져오기 (새로 추가됨 ⭐️)
def get_youtube_hype_trends():
    if not YOUTUBE_API_KEY:
        print("유튜브 API 키가 없습니다.")
        return []
        
    # 한국(KR) 지역의 유튜브 인기 급상승(mostPopular) 데이터 요청
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=KR&maxResults=5&key={YOUTUBE_API_KEY}"
    
    try:
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        
        hype_videos = []
        for item in data.get('items', []):
            video_info = {
                'platform': 'youtube',
                'title': item['snippet']['title'],
                'channel': item['snippet']['channelTitle'],
                'views': item['statistics'].get('viewCount', '0'),
                'thumbnail': item['snippet']['thumbnails']['medium']['url'] if 'medium' in item['snippet']['thumbnails'] else '',
                'link': f"https://www.youtube.com/watch?v={item['id']}"
            }
            hype_videos.append(video_info)
            
        return hype_videos
    except Exception as e:
        print(f"유튜브 API 에러: {e}")
        return []

@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        # 네이버 트렌드 데이터 수집
        live_keywords = get_realtime_keywords()
        group1 = [{"groupName": kw, "keywords": [kw]} for kw in live_keywords[:5]]
        group2 = [{"groupName": kw, "keywords": [kw]} for kw in live_keywords[5:10]]
        
        result1 = fetch_naver_trends(group1)
        result2 = fetch_naver_trends(group2)
        all_results = result1.get('results', []) + result2.get('results', [])
        
        results_sorted = sorted(
            all_results,
            key=lambda x: x['data'][-1]['ratio'] if x.get('data') else 0,
            reverse=True
        )
        
        trends = []
        for i, item in enumerate(results_sorted):
            ratio = item['data'][-1]['ratio'] if item.get('data') else 0
            trends.append({
                'rank': i + 1,
                'keyword': item['title'],
                'change': 'new' if i < 2 else 'up' if i < 5 else 'same',
                'heat': min(int(ratio), 100),
                'sources': ['실시간검색어'],
            })
            
        # 유튜브 Hype 데이터 수집 추가
        youtube_data = get_youtube_hype_trends()
            
        # 기존 네이버 데이터(trends)와 유튜브 데이터(youtube_data)를 한 번에 프론트엔드로 발송
        return jsonify({
            'success': True, 
            'data': trends, 
            'youtube': youtube_data, 
            'source': 'auto-trend'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
