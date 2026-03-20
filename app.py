from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import re
import requests
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# CORS: 모든 출처 명시 허용 (Netlify, 로컬 등)
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
# 환경 변수
# ==========================================
NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY     = os.environ.get('YOUTUBE_API_KEY', '')
GAS_PROXY_URL       = os.environ.get('GAS_PROXY_URL', '')
LASTFM_API_KEY      = os.environ.get('LASTFM_API_KEY', '')

DEFAULT_KEYWORDS = [
    "환율", "날씨", "삼성전자", "이재명", "손흥민",
    "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"
]

# ==========================================
# 🟢 자체 인메모리 캐시 시스템 (서버 차단 방지)
# ==========================================
CACHE = {}
CACHE_TTL = 600  # 기본 캐시 유지 시간: 600초 (10분)

def get_cached_data(key, fetch_func, ttl=CACHE_TTL):
    now = time.time()
    cached = CACHE.get(key)
    
    # 캐시가 있고, 만료 시간이 지나지 않았으면 캐시 데이터 즉시 반환
    if cached and (now - cached['time']) < ttl:
        print(f"🟢 [Cache HIT] {key} (남은 시간: {int(ttl - (now - cached['time']))}초)")
        return cached['data']
        
    # 캐시가 없거나 만료되었으면 API를 새로 찔러서 데이터 갱신
    print(f"🔴 [Cache MISS] {key} 데이터 새로 갱신 중...")
    data = fetch_func()
    
    # 만약 API 호출이 에러가 났다면, 10분이나 에러를 보여줄 수 없으니 1분(60초) 뒤에 다시 시도하도록 설정
    is_error = False
    if isinstance(data, list) and len(data) > 0 and 'error' in data[0]:
        is_error = True
        
    CACHE[key] = {
        'data': data,
        'time': now if not is_error else now - ttl + 60 
    }
    
    return data


# ==========================================
# 네이버 실시간 키워드 + 데이터랩
# ==========================================
def get_realtime_keywords():
    try:
        found = []
        stop = {'기자','뉴스','속보','오늘','지금','최근','관련','발표','대한','이후','이번','지난'}
        for q in ["실시간검색어", "급상승", "오늘뉴스", "실시간뉴스"]:
            url = (
                f"https://openapi.naver.com/v1/search/news.json"
                f"?query={urllib.parse.quote(q)}&display=20&sort=date"
            )
            req = urllib.request.Request(url, headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
            })
            data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
            for item in data.get('items', []):
                title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                for w in re.findall(r'[가-힣]{2,6}', title):
                    if w not in found and w not in stop:
                        found.append(w)
                if len(found) >= 10: break
            if len(found) >= 10: break
        return found[:10] if len(found) >= 5 else DEFAULT_KEYWORDS
    except Exception as e:
        print(f"[네이버 키워드] {e}")
        return DEFAULT_KEYWORDS

def fetch_naver_trends(keyword_groups):
    if not keyword_groups: return {'results': []}
    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    body = json.dumps({
        "startDate": start_date, "endDate": end_date,
        "timeUnit": "date", "keywordGroups": keyword_groups
    }).encode('utf-8')
    try:
        req = urllib.request.Request(
            "https://openapi.naver.com/v1/datalab/search",
            data=body, method='POST',
            headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET, 'Content-Type': 'application/json'}
        )
        return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
    except Exception as e:
        print(f"[네이버 데이터랩] {e}")
        return {'results': []}


# ==========================================
# 유튜브 인기 급상승 (전체)
# ==========================================
def get_youtube_hype_trends():
    if not YOUTUBE_API_KEY: return [{"error": "YOUTUBE_API_KEY 환경변수 없음"}]
    url = (f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=KR&maxResults=10&key={YOUTUBE_API_KEY}")
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        if 'error' in data: return [{"error": data['error'].get('message', '알 수 없는 에러')}]
        result = []
        for item in data.get('items', []):
            vid, sn, st, th = item['id'], item['snippet'], item.get('statistics', {}), item['snippet'].get('thumbnails', {})
            result.append({
                'videoId': vid, 'title': sn.get('title', ''), 'channelTitle': sn.get('channelTitle', ''),
                'viewCount': int(st.get('viewCount', 0)),
                'thumbnail': th.get('maxres', {}).get('url') or th.get('high', {}).get('url') or th.get('medium', {}).get('url') or f"https://img.youtube.com/vi/{vid}/mqdefault.jpg",
                'url': f"https://www.youtube.com/watch?v={vid}",
            })
        return result
    except Exception as e:
        print(f"[유튜브] {e}")
        return [{"error": str(e)}]


# ==========================================
# 구글 트렌드 (GAS 프록시)
# ==========================================
def get_google_trends():
    if not GAS_PROXY_URL: return []
    try:
        resp = requests.get(GAS_PROXY_URL, timeout=15, allow_redirects=True, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []) if data.get("status") == "ok" else []
    except Exception as e:
        print(f"[구글 트렌드] {e}")
        return []


# ==========================================
# Last.fm 한국 음악 차트 트렌드
# ==========================================
def get_lastfm_trends():
    if not LASTFM_API_KEY: return [{"error": "LASTFM_API_KEY 환경변수 없음"}]
    url = f"http://ws.audioscrobbler.com/2.0/?method=geo.gettoptracks&country=south+korea&api_key={LASTFM_API_KEY}&format=json&limit=10"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        if 'error' in data: return [{"error": f"Last.fm API 오류: {data.get('message', '알 수 없는 에러')}"}]
        tracks = data.get('tracks', {}).get('track', [])
        if not tracks: return [{"error": "Last.fm 데이터 없음"}]
        result = []
        for i, track in enumerate(tracks):
            images = track.get('image', [])
            image_url = images[-1].get('#text', '') if images else ""
            result.append({
                'rank': i + 1, 'keyword': track.get('name', ''), 'title': track.get('name', ''),
                'artist': track.get('artist', {}).get('name', ''), 'listeners': f"{int(track.get('listeners', 0)):,}명",
                'image': image_url, 'url': track.get('url', ''),
            })
        return result
    except Exception as e:
        print(f"[Last.fm] {e}")
        return [{"error": f"Last.fm 연동 오류: {str(e)}"}]


# ==========================================
# 스팀
# ==========================================
def _fetch_current_players(appid: str) -> int:
    try:
        url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=8).read().decode('utf-8'))
        return int(data.get('response', {}).get('player_count', 0))
    except Exception: return 0

def _get_steam_names(appids: list) -> dict:
    result = {}
    def fetch_spy(appid):
        try:
            data = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://steamspy.com/api.php?request=appdetails&appid={appid}", headers={'User-Agent': 'Mozilla/5.0'}), timeout=8).read().decode('utf-8'))
            if data and data.get('name'): return appid, data['name']
        except Exception: pass
        return appid, None

    with ThreadPoolExecutor(max_workers=5) as ex:
        for appid, name in ex.map(fetch_spy, appids):
            if name: result[appid] = name

    missing = [a for a in appids if a not in result]
    if missing:
        try:
            store = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://store.steampowered.com/api/appdetails?appids={','.join(missing)}&cc=kr&l=korean&filters=basic", headers={'User-Agent': 'Mozilla/5.0'}), timeout=12).read().decode('utf-8'))
            for appid in missing:
                if store.get(appid, {}).get('success') and store.get(appid, {}).get('data', {}).get('name'): result[appid] = store[appid]['data']['name']
        except Exception: pass
    return result

def get_steam_trends():
    try:
        url  = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10).read().decode('utf-8'))
        ranks = data.get('response', {}).get('ranks', [])
        if not ranks: return [{"error": "Steam 랭킹 데이터 없음"}]

        top_10 = ranks[:10]
        appids = [str(g['appid']) for g in top_10]

        with ThreadPoolExecutor(max_workers=15) as ex:
            names_future = ex.submit(_get_steam_names, appids)
            player_futures = {ex.submit(_fetch_current_players, aid): aid for aid in appids}
            names = names_future.result()
            players = {aid: future.result() for future, aid in [(f, player_futures[f]) for f in as_completed(player_futures)]}

        trends = []
        for i, game in enumerate(top_10):
            appid = str(game['appid'])
            current = players.get(appid, 0)
            trends.append({
                'rank': i + 1, 'keyword': names.get(appid) or f"App {appid}",
                'concurrent_players': f"{current:,}" if current else "집계 중", 'peak_players': f"{int(game.get('peak_in_game') or 0):,}",
                'image': f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg", 'url': f"https://store.steampowered.com/app/{appid}/",
            })
        return trends
    except Exception as e:
        print(f"[Steam] {e}")
        return [{"error": f"Steam 오류: {str(e)}"}]


# ==========================================
# 깃허브
# ==========================================
def get_github_trends():
    try:
        last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        url  = f"https://api.github.com/search/repositories?q=created:>{last_week}&sort=stars&order=desc&per_page=10"
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10).read().decode('utf-8'))
        return [{
            'rank': i + 1, 'keyword': item.get('full_name', ''), 'description': item.get('description') or '설명 없음',
            'stars': f"{item.get('stargazers_count', 0):,}", 'language': item.get('language') or '언어 미상', 'url': item.get('html_url', ''),
        } for i, item in enumerate(data.get('items', []))]
    except Exception as e:
        print(f"[GitHub] {e}")
        return [{"error": str(e)}]


# ==========================================
# 업비트 (KRW 마켓 거래대금 순위)
# ==========================================
def get_upbit_trends():
    try:
        market_data = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.upbit.com/v1/market/all?isDetails=false", headers={'Accept': 'application/json'}), timeout=10).read().decode('utf-8'))
        krw_markets = [item['market'] for item in market_data if item['market'].startswith('KRW-')]
        market_names = {item['market']: item['korean_name'] for item in market_data if item['market'].startswith('KRW-')}

        ticker_data = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets)}", headers={'Accept': 'application/json'}), timeout=10).read().decode('utf-8'))
        sorted_tickers = sorted(ticker_data, key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)

        trends = []
        for i, ticker in enumerate(sorted_tickers[:10]):
            mc, vol = ticker['market'], ticker.get('acc_trade_price_24h', 0)
            trends.append({
                'rank': i + 1, 'keyword': f"{market_names.get(mc, mc)} ({mc.replace('KRW-', '')})",
                'price': f"{ticker.get('trade_price', 0):,}원", 'change_rate': f"{ticker.get('signed_change_rate', 0) * 100:+.2f}%",
                'volume': f"{vol / 1_000_000_000_000:.1f}조 원" if vol >= 1_000_000_000_000 else f"{int(vol / 100_000_000):,}억 원",
                'url': f"https://upbit.com/exchange?code=CRIX.UPBIT.{mc}",
            })
        return trends
    except Exception as e:
        print(f"[업비트] {e}")
        return [{"error": str(e)}]


# ==========================================
# 🟢 위키백과 한국어 인기 문서 (어제 기준)
# ==========================================
def get_wikipedia_trends():
    yesterday = datetime.now() - timedelta(days=1)
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/ko.wikipedia/all-access/{yesterday.strftime('%Y')}/{yesterday.strftime('%m')}/{yesterday.strftime('%d')}"
    try:
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'NOWLY-Trend-Bot/1.0'}), timeout=10).read().decode('utf-8'))
        articles = data.get('items', [])[0].get('articles', [])
        exclude_keywords = ['위키백과:', '특수:', '파일:', '분류:', '사용자:', '포털:', '대문']
        
        trends = []
        rank = 1
        for article in articles:
            title = article.get('article', '').replace('_', ' ')
            if any(title.startswith(ex) or title == ex for ex in exclude_keywords): continue
            trends.append({
                'rank': rank, 'keyword': title, 'views': f"{article.get('views', 0):,}회",
                'url': f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(article.get('article', ''))}"
            })
            rank += 1
            if rank > 10: break
        return trends
    except Exception as e:
        print(f"[위키백과] 오류: {e}")
        return [{"error": f"위키백과 연동 오류: {str(e)}"}]


# ==========================================
# 🟢 애니메이션 트렌드 (AniList + MAL 통합)
# ==========================================
def get_anime_trends():
    try:
        anime_scores, anime_details = {}, {}

        # 1. AniList (GraphQL)
        query = """query { Page(page: 1, perPage: 15) { media(sort: TRENDING_DESC, type: ANIME) { title { romaji english } coverImage { large } siteUrl } } }"""
        res_ani = json.loads(urllib.request.urlopen(urllib.request.Request('https://graphql.anilist.co', data=json.dumps({'query': query}).encode('utf-8'), headers={'Content-Type': 'application/json'}), timeout=10).read().decode('utf-8'))
        
        for i, anime in enumerate(res_ani.get('data', {}).get('Page', {}).get('media', [])):
            titles = anime.get('title', {})
            title = titles.get('english') or titles.get('romaji') or 'Unknown'
            norm_title = re.sub(r'[^a-z0-9]', '', title.lower())
            anime_scores[norm_title] = 15 - i
            anime_details[norm_title] = {'keyword': title, 'title': title, 'image': anime.get('coverImage', {}).get('large', ''), 'url': anime.get('siteUrl', ''), 'sources': ['AniList']}

        # 2. MyAnimeList (Jikan API)
        res_mal = json.loads(urllib.request.urlopen(urllib.request.Request('https://api.jikan.moe/v4/top/anime?filter=airing&limit=15', headers={'User-Agent': 'Mozilla/5.0 (NOWLY-Trend-Bot)'}), timeout=10).read().decode('utf-8'))
        
        for i, anime in enumerate(res_mal.get('data', [])):
            title = anime.get('title_english') or anime.get('title') or 'Unknown'
            norm_title = re.sub(r'[^a-z0-9]', '', title.lower())
            if norm_title in anime_scores:
                anime_scores[norm_title] += (15 - i)
                if 'MAL' not in anime_details[norm_title]['sources']: anime_details[norm_title]['sources'].append('MAL')
            else:
                anime_scores[norm_title] = 15 - i
                anime_details[norm_title] = {'keyword': title, 'title': title, 'image': anime.get('images', {}).get('jpg', {}).get('large_image_url', ''), 'url': anime.get('url', ''), 'sources': ['MAL']}

        sorted_animes = sorted(anime_scores.items(), key=lambda x: x[1], reverse=True)
        return [{
            'rank': rank + 1, 'keyword': anime_details[nt]['keyword'], 'title': anime_details[nt]['title'],
            'image': anime_details[nt]['image'], 'url': anime_details[nt]['url'], 'score': score, 'sources': anime_details[nt]['sources']
        } for rank, (nt, score) in enumerate(sorted_animes[:10])]
    except Exception as e:
        print(f"[애니 트렌드] 오류: {e}")
        return [{"error": f"애니 API 연동 오류: {str(e)}"}]


# ==========================================
# API 라우트
# ==========================================
@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        # 네이버 트렌드는 실시간 검색어 수집 후 데이터랩을 찔러야 하므로, 래퍼 함수를 만들어 통째로 캐싱
        def fetch_naver_full():
            live_kw = get_realtime_keywords()
            r1 = fetch_naver_trends([{"groupName": kw, "keywords": [kw]} for kw in live_kw[:5]])
            r2 = fetch_naver_trends([{"groupName": kw, "keywords": [kw]} for kw in live_kw[5:]])
            all_results = r1.get('results', []) + r2.get('results', [])
            all_results.sort(key=lambda x: x['data'][-1]['ratio'] if x.get('data') else 0, reverse=True)
            return [{
                'rank': i + 1, 'keyword': item['title'], 'change': 'new' if i < 2 else 'up' if i < 5 else 'same',
                'heat': min(int(item['data'][-1]['ratio']) if item.get('data') else 0, 100), 'sources': ['실시간검색어'],
            } for i, item in enumerate(all_results)]

        # 모든 데이터를 get_cached_data 헬퍼 함수를 통해 호출 (10분 유지)
        return jsonify({
            'success': True,
            'data':    get_cached_data('naver', fetch_naver_full),
            'youtube': get_cached_data('youtube', get_youtube_hype_trends),
            'google':  get_cached_data('google', get_google_trends),
            'music':   get_cached_data('music', get_lastfm_trends),
            'steam':   get_cached_data('steam', get_steam_trends),
            'github':  get_cached_data('github', get_github_trends),
            'upbit':   get_cached_data('upbit', get_upbit_trends),
            'wiki':    get_cached_data('wiki', get_wikipedia_trends),
            'anime':   get_cached_data('anime', get_anime_trends),
            'source':  'auto-trend',
        })
    except Exception as e:
        print(f"[/trends] 메인 오류: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/health')
def health(): return jsonify({'status': 'ok'})

# 개별 디버그 라우트들도 전부 캐시를 타도록 수정해서 안전함!
@app.route('/debug-naver')
def debug_naver(): return jsonify({"success": True, "data": get_cached_data('naver', get_realtime_keywords)})
@app.route('/debug-google')
def debug_google(): return jsonify({"success": True, "data": get_cached_data('google', get_google_trends)})
@app.route('/debug-music')
def debug_music(): return jsonify({"success": True, "data": get_cached_data('music', get_lastfm_trends)})
@app.route('/debug-steam')
def debug_steam(): return jsonify({"success": True, "data": get_cached_data('steam', get_steam_trends)})
@app.route('/debug-github')
def debug_github(): return jsonify({"success": True, "data": get_cached_data('github', get_github_trends)})
@app.route('/debug-upbit')
def debug_upbit(): return jsonify({"success": True, "data": get_cached_data('upbit', get_upbit_trends)})
@app.route('/debug-wiki')
def debug_wiki(): return jsonify({"success": True, "data": get_cached_data('wiki', get_wikipedia_trends)})
@app.route('/debug-anime')
def debug_anime(): return jsonify({"success": True, "data": get_cached_data('anime', get_anime_trends)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
