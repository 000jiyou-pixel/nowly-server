from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import urllib.request
import urllib.parse
import json
import os
import re
import requests
import time
import concurrent.futures
import threading
import csv  
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 🔐 환경 변수 & 기본 설정
# ==========================================
NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY     = os.environ.get('YOUTUBE_API_KEY', '')
KOFIC_API_KEY       = os.environ.get('KOFIC_API_KEY', '')
ALADIN_TTB_KEY      = os.environ.get('ALADIN_TTB_KEY', '')

GOOGLE_TRENDS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRVGR2nB57vMAQeGNBOephsXV2A39OxcAt6nZrpro1lm3PNSPO0lyro9Juby8H7AYP_tE1PlYpfyz0V/pub?output=csv"
DEFAULT_KEYWORDS = ["환율", "날씨", "삼성전자", "이재명", "손흥민", "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"]
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
}

# ==========================================
# ⚡ 초고속 SWR 캐싱 시스템 (0.1초 응답의 핵심)
# ==========================================
CACHE = {}
CACHE_TTL = 300  
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def background_fetch_task(key, fetch_func):
    try:
        data = fetch_func()
        is_error = isinstance(data, list) and (len(data) == 0 or 'error' in data[0])
        
        if not is_error:
            CACHE[key] = {'data': data, 'time': time.time(), 'fetching': False}
        else:
            if key in CACHE:
                CACHE[key]['fetching'] = False
                CACHE[key]['time'] = time.time() - CACHE_TTL + 60 
                CACHE[key]['data'] = data 
    except Exception as e:
        print(f"[{key}] 갱신 실패: {e}")
        if key in CACHE: 
            CACHE[key]['fetching'] = False
            CACHE[key]['data'] = [{"error": str(e)}]

def get_swr_data(key, fetch_func):
    now = time.time()
    cached = CACHE.get(key)
    
    if cached:
        if (now - cached['time']) > CACHE_TTL and not cached.get('fetching'):
            CACHE[key]['fetching'] = True
            executor.submit(background_fetch_task, key, fetch_func)
        return cached['data']
    else:
        CACHE[key] = {
            'data': [{"status": "loading", "title": "🔥 데이터를 실시간으로 불러오는 중입니다...", "rank": "-"}], 
            'time': 0, 
            'fetching': True
        }
        executor.submit(background_fetch_task, key, fetch_func)
        return CACHE[key]['data']

# ==========================================
# 🔍 API 수집 함수들
# ==========================================
def get_google_trends_from_csv():
    try:
        req = urllib.request.Request(GOOGLE_TRENDS_CSV_URL, headers=BROWSER_HEADERS)
        response = urllib.request.urlopen(req, timeout=5)
        lines = [line.decode('utf-8') for line in response.readlines()]
        reader = csv.reader(lines)
        trends = []
        
        for i, row in enumerate(reader):
            if i == 0 or not row: continue
            if len(row) == 1 and ',' in row[0]: row = row[0].split(',')
            if len(row) == 0: continue
                
            keyword = row[0].strip().replace('"', '')
            search_volume = row[1].strip().replace('"', '') if len(row) > 1 else ""
            
            raw_url = row[5].strip() if len(row) > 5 else ""
            if raw_url and raw_url.startswith("./explore"):
                full_url = raw_url.replace("./explore", "https://trends.google.com/trends/explore")
            else:
                full_url = f"https://trends.google.com/trends/explore?q={urllib.parse.quote(keyword)}&geo=KR"
            
            trends.append({'rank': len(trends) + 1, 'title': keyword, 'volume': search_volume, 'url': full_url})
            if len(trends) == 10: break
                
        return trends if trends else [{"error": "스프레드시트 데이터 없음"}]
    except Exception as e:
        return [{"error": f"CSV 파싱 실패: {str(e)}"}]

def get_naver_full_trends():
    try:
        found, stop = [], {'기자','뉴스','속보','오늘','지금'}
        for q in ["실시간검색어", "급상승"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(q)}&display=20"
            req = urllib.request.Request(url, headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET})
            data = json.loads(urllib.request.urlopen(req, timeout=5).read().decode('utf-8'))
            for item in data.get('items', []):
                title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                for w in re.findall(r'[가-힣]{2,6}', title):
                    if w not in found and w not in stop: found.append(w)
        live_kw = found[:10] if len(found) >= 5 else DEFAULT_KEYWORDS
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        def fetch_trends(kw_list):
            body = json.dumps({"startDate": start_date, "endDate": end_date, "timeUnit": "date", "keywordGroups": [{"groupName": k, "keywords": [k]} for k in kw_list]}).encode('utf-8')
            req = urllib.request.Request("https://openapi.naver.com/v1/datalab/search", data=body, method='POST', headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET, 'Content-Type': 'application/json'})
            return json.loads(urllib.request.urlopen(req, timeout=5).read().decode('utf-8')).get('results', [])
        
        all_results = fetch_trends(live_kw[:5]) + fetch_trends(live_kw[5:])
        all_results.sort(key=lambda x: x['data'][-1]['ratio'] if x.get('data') else 0, reverse=True)
        return [{'rank': i+1, 'keyword': item['title']} for i, item in enumerate(all_results)]
    except: return [{"rank": i+1, "keyword": kw} for i, kw in enumerate(DEFAULT_KEYWORDS)]

def get_google_news_trends():
    try:
        resp = requests.get("https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", headers=BROWSER_HEADERS, timeout=5)
        root = ET.fromstring(resp.text)
        return [{'rank': i+1, 'title': re.sub(r'\s*[-|]\s*[^-|]+$', '', item.find('title').text), 'url': item.find('link').text} for i, item in enumerate(root.findall('.//item')[:10])]
    except Exception as e: return [{"error": str(e)}]

def get_youtube_music_trends():
    if not YOUTUBE_API_KEY: return [{"error": "API KEY 없음"}]
    try:
        data = requests.get(f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=KR&videoCategoryId=10&maxResults=10&key={YOUTUBE_API_KEY}", timeout=5).json()
        return [{'rank': i+1, 'title': item['snippet']['title'], 'url': f"https://www.youtube.com/watch?v={item['id']}"} for i, item in enumerate(data.get('items', []))]
    except Exception as e: return [{"error": str(e)}]

def get_github_trends():
    last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    try: return [{'rank': i+1, 'keyword': item.get('full_name', ''), 'url': item.get('html_url', '')} for i, item in enumerate(requests.get(f"https://api.github.com/search/repositories?q=created:>{last_week}&sort=stars&order=desc&per_page=10", headers={'Accept': 'application/vnd.github.v3+json', **BROWSER_HEADERS}, timeout=5).json().get('items', []))]
    except Exception as e: return [{"error": str(e)}]

def get_upbit_trends():
    try:
        markets = requests.get("https://api.upbit.com/v1/market/all?isDetails=false", headers=BROWSER_HEADERS, timeout=5).json()
        krw_markets = [m['market'] for m in markets if m['market'].startswith('KRW-')]
        tickers = requests.get(f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets)}", headers=BROWSER_HEADERS, timeout=5).json()
        tickers.sort(key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)
        return [{'rank': i+1, 'keyword': t['market'], 'price': f"{t.get('trade_price', 0):,}원"} for i, t in enumerate(tickers[:10])]
    except Exception as e: return [{"error": str(e)}]

def get_kofic_trends():
    if not KOFIC_API_KEY: return [{"error": "API KEY 없음"}]
    try: return [{'rank': int(m['rank']), 'title': m['movieNm']} for m in requests.get(f"http://kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json?key={KOFIC_API_KEY}&targetDt={(datetime.now() - timedelta(days=1)).strftime('%Y%m%d')}", headers=BROWSER_HEADERS, timeout=5).json().get('boxOfficeResult', {}).get('dailyBoxOfficeList', [])[:10]]
    except Exception as e: return [{"error": str(e)}]

def get_aladin_official_trends():
    if not ALADIN_TTB_KEY: return [{"error": "API KEY 없음"}]
    try: return [{'rank': i+1, 'title': item.get('title'), 'author': item.get('author', '').split(',')[0]} for i, item in enumerate(requests.get(f"http://www.aladin.co.kr/ttb/api/ItemList.aspx?ttbkey={ALADIN_TTB_KEY}&QueryType=Bestseller&MaxResults=10&start=1&SearchTarget=Book&output=js&Version=20131101", timeout=5).json().get('item', []))]
    except Exception as e: return [{"error": str(e)}]


# ==========================================
# 🚀 라우트: 웹사이트 화면 띄우기 & 데이터 반환
# ==========================================
TASKS = {
    'data': get_naver_full_trends,
    'google_trend': get_google_trends_from_csv, 
    'news_google': get_google_news_trends,
    'youtube_music': get_youtube_music_trends,
    'github': get_github_trends,
    'upbit': get_upbit_trends,
    'movie': get_kofic_trends,
    'books': get_aladin_official_trends,
}

# ⭐️ 여기가 바뀌었습니다! 썰렁한 글자 대신 index.html 화면을 전송합니다.
@app.route('/')
def home(): 
    return send_from_directory('public', 'index.html')

# ⭐️ style.css 같은 꾸미기 파일도 보낼 수 있게 길을 열어줍니다.
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('public', filename)

# ⭐️ 기존의 데이터 전송용 주소
@app.route('/trends', methods=['GET'])
def get_trends():
    results = {'success': True}
    for key, func in TASKS.items():
        results[key] = get_swr_data(key, func)
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
