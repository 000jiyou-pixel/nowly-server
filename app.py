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

# CORS: 모든 출처 허용
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
# 🔐 환경 변수 설정
# ==========================================
NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY     = os.environ.get('YOUTUBE_API_KEY', '')
GAS_PROXY_URL       = os.environ.get('GAS_PROXY_URL', '') 
LASTFM_API_KEY      = os.environ.get('LASTFM_API_KEY', '')
KOFIC_API_KEY       = os.environ.get('KOFIC_API_KEY', '')
ALADIN_TTB_KEY      = os.environ.get('ALADIN_TTB_KEY', '')

DEFAULT_KEYWORDS = ["환율", "날씨", "삼성전자", "이재명", "손흥민", "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"]

# 🛡️ 봇 차단 방어벽 우회용 브라우저 위장 헤더
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}

# ==========================================
# 🟢 캐시 시스템 (서버 부하 방지)
# ==========================================
CACHE = {}
CACHE_TTL = 600  # 10분 유지

def get_cached_data(key, fetch_func, ttl=CACHE_TTL):
    now = time.time()
    cached = CACHE.get(key)
    
    if cached and (now - cached['time']) < ttl:
        return cached['data']
        
    print(f"🔄 [{key}] 데이터 새로 갱신 중...")
    data = fetch_func()
    
    is_error = isinstance(data, list) and len(data) > 0 and 'error' in data[0]
    CACHE[key] = {
        'data': data,
        'time': now if not is_error else now - ttl + 60 
    }
    return data

# ==========================================
# 🔍 1. 종합 & 뉴스 (네이버, 구글 뉴스, 구글 트렌드, SBS)
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
    except: return DEFAULT_KEYWORDS

def fetch_naver_trends(keyword_groups):
    if not keyword_groups: return {'results': []}
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    body = json.dumps({"startDate": start_date, "endDate": end_date, "timeUnit": "date", "keywordGroups": keyword_groups}).encode('utf-8')
    try:
        req = urllib.request.Request("https://openapi.naver.com/v1/datalab/search", data=body, method='POST', headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET, 'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
    except: return {'results': []}

def get_google_news_trends():
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
        root = ET.fromstring(resp.text)
        trends = []
        for i, item in enumerate(root.findall('.//item')[:10]):
            raw_title = item.find('title').text if item.find('title') is not None else "제목 없음"
            clean_title = re.sub(r'\s*[-|]\s*[^-|]+$', '', raw_title)
            trends.append({'rank': i+1, 'title': clean_title, 'url': item.find('link').text})
        return trends
    except Exception as e: return [{"error": str(e)}]

def get_google_trends():
    if not GAS_PROXY_URL: return [{"error": "GAS_PROXY_URL 없음"}]
    try:
        resp = requests.get(GAS_PROXY_URL, timeout=15, headers={"Accept": "application/json"})
        data = resp.json()
        if data.get("status") == "ok":
            return [{'rank': i+1, 'title': item.get('title'), 'url': item.get('url')} for i, item in enumerate(data.get("data", [])[:10])]
        return []
    except Exception as e: return [{"error": str(e)}]

def get_sbs_news_trends():
    url = "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=14"
    try:
        root = ET.fromstring(requests.get(url, headers=BROWSER_HEADERS, timeout=10).text)
        return [{'rank': i+1, 'title': item.find('title').text, 'url': item.find('link').text} for i, item in enumerate(root.findall('.//item')[:10])]
    except Exception as e: return [{"error": str(e)}]

# ==========================================
# 🎵 2. 오디오 & 음악 (유튜브 뮤직, 애플뮤직, 팟캐스트)
# ==========================================
def get_youtube_music_trends():
    if not YOUTUBE_API_KEY: return [{"error": "YOUTUBE_API_KEY 없음"}]
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=KR&videoCategoryId=10&maxResults=10&key={YOUTUBE_API_KEY}"
    try:
        data = requests.get(url, timeout=10).json()
        if 'error' in data: return [{"error": data['error'].get('message')}]
        return [{'rank': i+1, 'title': item['snippet']['title'], 'channelTitle': item['snippet']['channelTitle'], 'url': f"https://www.youtube.com/watch?v={item['id']}", 'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', '')} for i, item in enumerate(data.get('items', []))]
    except Exception as e: return [{"error": str(e)}]

def get_apple_music_trends():
    url = "https://rss.applemarketingtools.com/api/v2/kr/music/most-played/10/songs.json"
    try: return [{'rank': i+1, 'title': s['name'], 'artist': s['artistName'], 'image': s['artworkUrl100']} for i, s in enumerate(requests.get(url, headers=BROWSER_HEADERS, timeout=10).json().get('feed', {}).get('results', []))]
    except Exception as e: return [{"error": str(e)}]

def get_apple_podcast_trends():
    url = "https://rss.applemarketingtools.com/api/v2/kr/podcasts/top/10/podcasts.json"
    try: return [{'rank': i+1, 'title': p['name'], 'artist': p['artistName'], 'image': p['artworkUrl100']} for i, p in enumerate(requests.get(url, headers=BROWSER_HEADERS, timeout=10).json().get('feed', {}).get('results', []))]
    except Exception as e: return [{"error": str(e)}]

# ==========================================
# 💻 3. IT & 개발 (GitHub, HackerNews)
# ==========================================
def get_github_trends():
    last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    url = f"https://api.github.com/search/repositories?q=created:>{last_week}&sort=stars&order=desc&per_page=10"
    headers = BROWSER_HEADERS.copy()
    headers['Accept'] = 'application/vnd.github.v3+json'
    try: return [{'rank': i+1, 'keyword': item.get('full_name', ''), 'description': item.get('description') or '설명 없음', 'url': item.get('html_url', '')} for i, item in enumerate(requests.get(url, headers=headers, timeout=10).json().get('items', []))]
    except Exception as e: return [{"error": str(e)}]

def get_hackernews_trends():
    try:
        ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", headers=BROWSER_HEADERS, timeout=10).json()[:10]
        return [{'rank': i+1, 'title': requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", headers=BROWSER_HEADERS, timeout=5).json().get('title'), 'url': f"https://news.ycombinator.com/item?id={sid}"} for i, sid in enumerate(ids)]
    except Exception as e: return [{"error": str(e)}]

# ==========================================
# 💰 4. 금융 (Upbit, CoinGecko)
# ==========================================
def get_upbit_trends():
    try:
        markets = requests.get("https://api.upbit.com/v1/market/all?isDetails=false", headers=BROWSER_HEADERS, timeout=10).json()
        krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]
        tickers = requests.get(f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets)}", headers=BROWSER_HEADERS, timeout=10).json()
        tickers.sort(key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)
        return [{'rank': i+1, 'keyword': t['market'], 'price': f"{t.get('trade_price', 0):,}원", 'url': f"https://upbit.com/exchange?code=CRIX.UPBIT.{t['market']}"} for i, t in enumerate(tickers[:10])]
    except Exception as e: return [{"error": str(e)}]

def get_coingecko_trends():
    try: return [{'rank': i+1, 'title': c['item']['name'], 'symbol': c['item']['symbol'], 'image': c['item']['small']} for i, c in enumerate(requests.get("https://api.coingecko.com/api/v3/search/trending", headers=BROWSER_HEADERS, timeout=10).json().get('coins', [])[:10])]
    except Exception as e: return [{"error": str(e)}]

# ==========================================
# 🎮 5. 게임 (Steam, 애플 클래식 게임)
# ==========================================
def get_steam_trends():
    try: return [{'rank': i+1, 'title': g.get('name'), 'image': g.get('header_image')} for i, g in enumerate(requests.get("https://store.steampowered.com/api/featuredcategories/?cc=kr&l=korean", headers=BROWSER_HEADERS, timeout=10).json().get('top_sellers', {}).get('items', [])[:10])]
    except Exception as e: return [{"error": str(e)}]

# [오류 해결] 리스트/딕셔너리 예외 완벽 대응
def get_apple_games_trends():
    url = "https://itunes.apple.com/kr/rss/topfreeapplications/limit=10/genre=6014/json"
    try:
        data = requests.get(url, headers=BROWSER_HEADERS, timeout=10).json()
        entries = data.get('feed', {}).get('entry', [])
        if isinstance(entries, dict): entries = [entries] # 아이템이 1개일 경우 리스트화
        
        trends = []
        for i, item in enumerate(entries[:10]):
            # 1. URL 안전 추출
            app_url = item.get('id', {}).get('label', '')
            if not app_url:
                link_data = item.get('link')
                if isinstance(link_data, list) and len(link_data) > 0:
                    app_url = link_data[0].get('attributes', {}).get('href', '')
                elif isinstance(link_data, dict):
                    app_url = link_data.get('attributes', {}).get('href', '')

            # 2. 이미지 안전 추출
            img_data = item.get('im:image')
            img_url = ''
            if isinstance(img_data, list) and len(img_data) > 0:
                img_url = img_data[-1].get('label', '') # 가장 해상도 높은 마지막 이미지
            elif isinstance(img_data, dict):
                img_url = img_data.get('label', '')

            # 3. 최종 데이터 조립
            trends.append({
                'rank': i+1,
                'title': item.get('im:name', {}).get('label', '제목 없음'),
                'artist': item.get('im:artist', {}).get('label', ''),
                'image': img_url,
                'url': app_url
            })
            
        return trends
    except Exception as e: 
        return [{"error": f"앱스토어 연동 오류: {str(e)}"}]

# ==========================================
# 🎬 6. 미디어, 도서 & 애니 (KOFIC, 알라딘 공식, AniList 복구)
# ==========================================
def get_kofic_trends():
    if not KOFIC_API_KEY: return [{"error": "KOFIC_API_KEY 설정 필요"}]
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    url = f"http://kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json?key={KOFIC_API_KEY}&targetDt={yesterday}"
    try: return [{'rank': int(m['rank']), 'title': m['movieNm'], 'audiAcc': f"{int(m['audiAcc']):,}명"} for m in requests.get(url, headers=BROWSER_HEADERS, timeout=10).json().get('boxOfficeResult', {}).get('dailyBoxOfficeList', [])[:10]]
    except Exception as e: return [{"error": str(e)}]

def get_aladin_official_trends():
    if not ALADIN_TTB_KEY: return [{"error": "ALADIN_TTB_KEY 환경변수 설정 필요"}]
    url = f"http://www.aladin.co.kr/ttb/api/ItemList.aspx?ttbkey={ALADIN_TTB_KEY}&QueryType=Bestseller&MaxResults=10&start=1&SearchTarget=Book&output=js&Version=20131101"
    try:
        data = requests.get(url, timeout=10).json()
        if 'item' not in data: return [{"error": "알라딘 API 응답 실패"}]
        return [{'rank': i+1, 'title': item.get('title'), 'author': item.get('author', '').split(',')[0], 'image': item.get('cover'), 'url': item.get('link')} for i, item in enumerate(data.get('item', []))]
    except Exception as e: return [{"error": str(e)}]

def get_anime_trends():
    query = """query { Page(page: 1, perPage: 10) { media(sort: TRENDING_DESC, type: ANIME) { title { romaji english } coverImage { large } siteUrl } } }"""
    try:
        data = requests.post('https://graphql.anilist.co', json={'query': query}, timeout=10).json()
        return [{
            'rank': i+1, 
            'title': m['title'].get('english') or m['title'].get('romaji', '제목 없음'), 
            'image': m['coverImage'].get('large'), 
            'url': m['siteUrl']
        } for i, m in enumerate(data.get('data', {}).get('Page', {}).get('media', []))]
    except Exception as e: 
        return [{"error": f"애니리스트 연동 오류: {str(e)}"}]

# ==========================================
# 🚀 최종 라우트 맵핑
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
            'trends_google': get_cached_data('trends_google', get_google_trends),
            'news_sbs':      get_cached_data('news_sbs', get_sbs_news_trends),
            
            'youtube_music': get_cached_data('youtube_music', get_youtube_music_trends),
            'music_apple':   get_cached_data('music_apple', get_apple_music_trends),
            'podcast':       get_cached_data('podcast', get_apple_podcast_trends),
            
            'github':        get_cached_data('github', get_github_trends),
            'hackernews':    get_cached_data('hackernews', get_hackernews_trends),
            
            'upbit':         get_cached_data('upbit', get_upbit_trends),
            'coingecko':     get_cached_data('coingecko', get_coingecko_trends),
            
            'steam':         get_cached_data('steam', get_steam_trends),
            'mobile_game':   get_cached_data('apple_game', get_apple_games_trends),
            
            'movie':         get_cached_data('kofic', get_kofic_trends),
            'books':         get_cached_data('books_official', get_aladin_official_trends),
            'anime':         get_cached_data('anime', get_anime_trends)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health(): return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
