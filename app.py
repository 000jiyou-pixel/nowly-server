from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.parse
import json
import os
import re
import requests
import time
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

app = Flask(__name__)

# CORS 설정
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Content-Type", "Authorization", "Accept"],
    "methods": ["GET", "POST", "OPTIONS"]
}})

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# ==========================================
# 🔐 환경 변수 설정 (서울 핫플 키 삭제)
# ==========================================
NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY     = os.environ.get('YOUTUBE_API_KEY', '')
GAS_PROXY_URL       = os.environ.get('GAS_PROXY_URL', '')
LASTFM_API_KEY      = os.environ.get('LASTFM_API_KEY', '')
KOFIC_API_KEY       = os.environ.get('KOFIC_API_KEY', '')
TMDB_API_KEY        = os.environ.get('TMDB_API_KEY', '')
LIBRARY_API_KEY     = os.environ.get('LIBRARY_API_KEY', '')

DEFAULT_KEYWORDS = ["환율", "날씨", "삼성전자", "이재명", "손흥민", "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"]

# ==========================================
# 🟢 캐시 시스템
# ==========================================
CACHE = {}
CACHE_TTL = 600  # 10분 유지 (깃허브, 업비트 등 차단 방지)

def get_cached_data(key, fetch_func, ttl=CACHE_TTL):
    now = time.time()
    cached = CACHE.get(key)
    
    if cached and (now - cached['time']) < ttl:
        print(f"🟢 [Cache HIT] {key} (남은 시간: {int(ttl - (now - cached['time']))}초)")
        return cached['data']
        
    print(f"🔴 [Cache MISS] {key} 데이터 갱신 중...")
    data = fetch_func()
    
    is_error = False
    if isinstance(data, list) and len(data) > 0 and 'error' in data[0]:
        is_error = True
        
    CACHE[key] = {
        'data': data,
        'time': now if not is_error else now - ttl + 60 
    }
    return data

# ==========================================
# 🛠️ 1. 기존 안정화된 API들 (네이버, 트렌드, Lastfm, 스팀 등)
# ==========================================
def get_realtime_keywords():
    try:
        found, stop = [], {'기자','뉴스','속보','오늘','지금','최근','관련','발표','대한','이후','이번','지난'}
        for q in ["실시간검색어", "급상승", "오늘뉴스"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(q)}&display=20&sort=date"
            req = urllib.request.Request(url, headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET})
            data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
            for item in data.get('items', []):
                title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                for w in re.findall(r'[가-힣]{2,6}', title):
                    if w not in found and w not in stop: found.append(w)
                if len(found) >= 10: break
            if len(found) >= 10: break
        return found[:10] if len(found) >= 5 else DEFAULT_KEYWORDS
    except Exception as e:
        return DEFAULT_KEYWORDS

def fetch_naver_trends(keyword_groups):
    if not keyword_groups: return {'results': []}
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    body = json.dumps({"startDate": start_date, "endDate": end_date, "timeUnit": "date", "keywordGroups": keyword_groups}).encode('utf-8')
    try:
        req = urllib.request.Request("https://openapi.naver.com/v1/datalab/search", data=body, method='POST', headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET, 'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
    except:
        return {'results': []}

def get_google_trends():
    if not GAS_PROXY_URL: return []
    try:
        resp = requests.get(GAS_PROXY_URL, timeout=15, headers={"Accept": "application/json"})
        return resp.json().get("data", []) if resp.json().get("status") == "ok" else []
    except:
        return []

def get_steam_trends():
    url = "https://store.steampowered.com/api/featuredcategories/?cc=kr&l=korean"
    try:
        data = requests.get(url, timeout=10).json()
        return [{'rank': i+1, 'title': g.get('name'), 'image': g.get('header_image')} for i, g in enumerate(data.get('top_sellers', {}).get('items', [])[:10])]
    except Exception as e:
        return [{"error": str(e)}]

# ==========================================
# 🚀 2. 봇 차단 우회 및 수정이 적용된 API들
# ==========================================

# [수정] 구글 뉴스 (언론사 출처 정규식 삭제 적용)
def get_google_news_trends():
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(resp.text)
        trends = []
        for i, item in enumerate(root.findall('.//item')[:10]):
            raw_title = item.find('title').text if item.find('title') is not None else "제목 없음"
            # 정규식을 이용해 제목 뒤에 붙는 ' - 파이낸셜뉴스', ' | 연합뉴스' 등을 잘라냅니다.
            clean_title = re.sub(r'\s*[-|]\s*[^-|]+$', '', raw_title)
            trends.append({'rank': i+1, 'title': clean_title, 'url': item.find('link').text})
        return trends
    except Exception as e: return [{"error": str(e)}]

# [수정] 유튜브 뮤직 (카테고리 10)
def get_youtube_music_trends():
    if not YOUTUBE_API_KEY: return [{"error": "YOUTUBE_API_KEY 없음"}]
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=KR&videoCategoryId=10&maxResults=10&key={YOUTUBE_API_KEY}"
    try:
        data = requests.get(url, timeout=10).json()
        if 'error' in data: return [{"error": data['error'].get('message')}]
        return [{
            'rank': i+1, 'title': item['snippet']['title'], 'channelTitle': item['snippet']['channelTitle'],
            'url': f"https://www.youtube.com/watch?v={item['id']}",
            'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', '')
        } for i, item in enumerate(data.get('items', []))]
    except Exception as e: return [{"error": str(e)}]

# [수정] 벨로그 (헤더 위장)
def get_velog_trends():
    url = "https://v2.velog.io/graphql"
    query = """query TrendingPosts($limit: Int, $timeframe: String) { trendingPosts(limit: $limit, timeframe: $timeframe) { title user { username } url_slug } }"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://velog.io/', 'Content-Type': 'application/json'}
    try:
        data = requests.post(url, json={"query": query, "variables": {"limit": 10, "timeframe": "week"}}, headers=headers, timeout=10).json()
        return [{'rank': i+1, 'title': p['title'], 'author': p['user']['username'], 'url': f"https://velog.io/@{p['user']['username']}/{p['url_slug']}"} for i, p in enumerate(data.get('data', {}).get('trendingPosts', []))]
    except Exception as e: return [{"error": str(e)}]

# [수정] 깃허브 (헤더 위장)
def get_github_trends():
    try:
        last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        url  = f"https://api.github.com/search/repositories?q=created:>{last_week}&sort=stars&order=desc&per_page=10"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': 'application/vnd.github.v3+json'}
        data = requests.get(url, headers=headers, timeout=10).json()
        return [{'rank': i + 1, 'keyword': item.get('full_name', ''), 'description': item.get('description') or '설명 없음', 'url': item.get('html_url', '')} for i, item in enumerate(data.get('items', []))]
    except Exception as e: return [{"error": str(e)}]

# [수정] 업비트 (헤더 위장)
def get_upbit_trends():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        markets = requests.get("https://api.upbit.com/v1/market/all?isDetails=false", headers=headers, timeout=10).json()
        krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]
        tickers = requests.get(f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets)}", headers=headers, timeout=10).json()
        tickers.sort(key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)
        return [{'rank': i+1, 'keyword': t['market'], 'price': f"{t.get('trade_price', 0):,}원", 'url': f"https://upbit.com/exchange?code=CRIX.UPBIT.{t['market']}"} for i, t in enumerate(tickers[:10])]
    except Exception as e: return [{"error": str(e)}]

# [수정] 앱스토어 (헤더 위장 및 최신 규격)
def get_apple_games_trends():
    url = "https://rss.applemarketingtools.com/api/v2/kr/apps/top-free/10/apps.json"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        data = requests.get(url, headers=headers, timeout=10).json()
        return [{'rank': i+1, 'title': app.get('name'), 'artist': app.get('artistName'), 'image': app.get('artworkUrl100'), 'url': app.get('url')} for i, app in enumerate(data.get('feed', {}).get('results', []))]
    except Exception as e: return [{"error": str(e)}]

# [수정] 알라딘 도서 (헤더 위장 및 XML 파싱 안정화)
def get_book_rss_trends():
    url = "http://www.aladin.co.kr/rsscenter/go.aspx?rssType=1&type=Bestseller"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': 'text/xml'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        root = ET.fromstring(resp.text)
        return [{'rank': i+1, 'title': item.find('title').text, 'url': item.find('link').text} for i, item in enumerate(root.findall('.//item')[:10])]
    except Exception as e: return [{"error": str(e)}]

# 영진위 박스오피스 (KOFIC_API_KEY 확인 필수)
def get_kofic_trends():
    if not KOFIC_API_KEY: return [{"error": "KOFIC_API_KEY 환경변수가 설정되지 않았습니다."}]
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    url = f"http://kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json?key={KOFIC_API_KEY}&targetDt={yesterday}"
    try:
        data = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        return [{'rank': int(m['rank']), 'title': m['movieNm'], 'audiAcc': f"{int(m['audiAcc']):,}명"} for m in data.get('boxOfficeResult', {}).get('dailyBoxOfficeList', [])[:10]]
    except Exception as e: return [{"error": str(e)}]

# 코인게코, 애플뮤직, 팟캐스트, TMDB, 도서관 유지
def get_coingecko_trends():
    try:
        data = requests.get("https://api.coingecko.com/api/v3/search/trending", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        return [{'rank': i+1, 'title': c['item']['name'], 'symbol': c['item']['symbol'], 'image': c['item']['small']} for i, c in enumerate(data.get('coins', [])[:10])]
    except Exception as e: return [{"error": str(e)}]

def get_apple_music_trends():
    try:
        data = requests.get("https://rss.applemarketingtools.com/api/v2/kr/music/most-played/10/songs.json", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        return [{'rank': i+1, 'title': s['name'], 'artist': s['artistName'], 'image': s['artworkUrl100']} for i, s in enumerate(data.get('feed', {}).get('results', []))]
    except Exception as e: return [{"error": str(e)}]

def get_apple_podcast_trends():
    try:
        data = requests.get("https://rss.applemarketingtools.com/api/v2/kr/podcasts/top/10/podcasts.json", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        return [{'rank': i+1, 'title': p['name'], 'artist': p['artistName'], 'image': p['artworkUrl100']} for i, p in enumerate(data.get('feed', {}).get('results', []))]
    except Exception as e: return [{"error": str(e)}]

def get_tmdb_trends():
    if not TMDB_API_KEY: return [{"error": "TMDB_API_KEY 없음"}]
    url = f"https://api.themoviedb.org/3/discover/tv?api_key={TMDB_API_KEY}&language=ko-KR&sort_by=popularity.desc&watch_region=KR&page=1"
    try:
        data = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        return [{'rank': i+1, 'title': s.get('name') or s.get('original_name')} for i, s in enumerate(data.get('results', [])[:10])]
    except Exception as e: return [{"error": str(e)}]

def get_hackernews_trends():
    try:
        ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()[:10]
        trends = []
        for i, sid in enumerate(ids):
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5).json()
            trends.append({'rank': i+1, 'title': item.get('title'), 'url': item.get('url')})
        return trends
    except Exception as e: return [{"error": str(e)}]


# ==========================================
# 🚀 최종 라우트 통합 (서울 핫플 삭제)
# ==========================================
@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        def fetch_naver_full():
            live_kw = get_realtime_keywords()
            r1 = fetch_naver_trends([{"groupName": kw, "keywords": [kw]} for kw in live_kw[:5]])
            r2 = fetch_naver_trends([{"groupName": kw, "keywords": [kw]} for kw in live_kw[5:]])
            all_results = r1.get('results', []) + r2.get('results', [])
            all_results.sort(key=lambda x: x['data'][-1]['ratio'] if x.get('data') else 0, reverse=True)
            return [{'rank': i+1, 'keyword': item['title']} for i, item in enumerate(all_results)]

        return jsonify({
            'success': True,
            'data':          get_cached_data('naver', fetch_naver_full),
            'news_google':   get_cached_data('news_google', get_google_news_trends),
            
            'youtube_music': get_cached_data('youtube_music', get_youtube_music_trends),
            'music_apple':   get_cached_data('music_apple', get_apple_music_trends),
            'podcast':       get_cached_data('podcast', get_apple_podcast_trends),
            
            'velog':         get_cached_data('velog', get_velog_trends),
            'github':        get_cached_data('github', get_github_trends),
            'hackernews':    get_cached_data('hackernews', get_hackernews_trends),
            
            'upbit':         get_cached_data('upbit', get_upbit_trends),
            'coingecko':     get_cached_data('coingecko', get_coingecko_trends),
            
            'steam':         get_cached_data('steam', get_steam_trends),
            'mobile_game':   get_cached_data('apple_game', get_apple_games_trends),
            
            'movie':         get_cached_data('kofic', get_kofic_trends),
            'ott':           get_cached_data('tmdb', get_tmdb_trends),
            'books':         get_cached_data('books_rss', get_book_rss_trends),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health(): return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
