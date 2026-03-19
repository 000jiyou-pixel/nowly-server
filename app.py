from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import re
import requests  # ← 추가
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
GAS_PROXY_URL = os.environ.get('GAS_PROXY_URL', '')

DEFAULT_KEYWORDS = ["환율", "날씨", "삼성전자", "이재명", "손흥민", "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"]

def get_realtime_keywords():
    try:
        found_keywords = []
        for q in ["실시간검색어", "급상승", "오늘뉴스", "실시간뉴스"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(q)}&display=20&sort=date"
            req = urllib.request.Request(url, headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
            })
            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))
            for item in data.get('items', []):
                title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                words = re.findall(r'[가-힣]{2,6}', title)
                for w in words:
                    if w not in found_keywords and w not in ['기자', '뉴스', '속보', '오늘', '지금', '최근', '관련', '발표', '대한', '이후', '이번', '지난']:
                        found_keywords.append(w)
                if len(found_keywords) >= 10:
                    break
            if len(found_keywords) >= 10:
                break
        return found_keywords[:10] if len(found_keywords) >= 5 else DEFAULT_KEYWORDS
    except Exception as e:
        print(f"키워드 추출 실패: {e}")
        return DEFAULT_KEYWORDS

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

def get_youtube_hype_trends():
    if not YOUTUBE_API_KEY:
        return [{"error": "YOUTUBE_API_KEY 환경변수 없음"}]
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=KR&maxResults=10&key={YOUTUBE_API_KEY}"
    try:
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        if 'error' in data:
            return [{"error": data['error'].get('message', '알 수 없는 에러')}]
        hype_videos = []
        for item in data.get('items', []):
            video_id = item['id']
            snippet = item['snippet']
            statistics = item['statistics']
            thumbnails = snippet.get('thumbnails', {})
            thumbnail_url = (
                thumbnails.get('maxres', {}).get('url') or
                thumbnails.get('high', {}).get('url') or
                thumbnails.get('medium', {}).get('url') or
                f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            )
            hype_videos.append({
                'videoId': video_id,
                'title': snippet.get('title', ''),
                'channelTitle': snippet.get('channelTitle', ''),
                'viewCount': int(statistics.get('viewCount', 0)),
                'thumbnail': thumbnail_url,
                'url': f"https://www.youtube.com/watch?v={video_id}",
            })
        return hype_videos
    except urllib.error.HTTPError as e:
        return [{"error": f"HTTP {e.code}: {e.read().decode('utf-8')}"}]
    except Exception as e:
        return [{"error": str(e)}]

# --- 새롭게 수정된 구글 트렌드 함수 (JSON API 우회 방식) ---
def get_google_trends():
    if not GAS_PROXY_URL:
        print("GAS_PROXY_URL 환경변수가 설정되지 않았습니다.")
        return []
    try:
        response = requests.get(
            GAS_PROXY_URL,
            timeout=15,
            allow_redirects=True,
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            print(f"GAS 프록시 에러: {data.get('error')}")
            return []

        return data.get("data", [])

    except requests.exceptions.Timeout:
        print("GAS 프록시 요청 타임아웃")
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"GAS 프록시 연결 실패: {e}")
        return []
    except Exception as e:
        print(f"구글 트렌드 에러: {e}")
        return []
# ----------------------------------------------------

@app.route('/trends', methods=['GET'])
def get_trends():
    try:
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
        
        youtube_data = get_youtube_hype_trends()
        google_data = get_google_trends()
        
        return jsonify({
            'success': True,
            'data': trends,
            'youtube': youtube_data,
            'google': google_data,
            'source': 'auto-trend'
        })
    except Exception as e:
        print(f"전체 에러: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/debug-naver')
def debug_naver():
    client_id = os.environ.get('NAVER_CLIENT_ID', 'NOT_SET')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET', 'NOT_SET')
    try:
        url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote('오늘')}&display=5&sort=date"
        req = urllib.request.Request(url, headers={
            'X-Naver-Client-Id': client_id,
            'X-Naver-Client-Secret': client_secret,
        })
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        return jsonify({"success": True, "client_id_set": client_id != 'NOT_SET', "items_count": len(data.get('items', []))})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "client_id_set": client_id != 'NOT_SET'})

# --- 구글 트렌드 전용 디버깅 라우트 ---
@app.route('/debug-google')
def debug_google():
    data = get_google_trends()
    return jsonify({"success": True, "data": data})
# ------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)


