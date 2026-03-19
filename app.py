from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import re
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

# ==========================================
# 환경 변수
# ==========================================
NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY     = os.environ.get('YOUTUBE_API_KEY', '')
GAS_PROXY_URL       = os.environ.get('GAS_PROXY_URL', '')

DEFAULT_KEYWORDS = [
    "환율", "날씨", "삼성전자", "이재명", "손흥민",
    "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"
]


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
                if len(found) >= 10:
                    break
            if len(found) >= 10:
                break
        return found[:10] if len(found) >= 5 else DEFAULT_KEYWORDS
    except Exception as e:
        print(f"[네이버 키워드] {e}")
        return DEFAULT_KEYWORDS


def fetch_naver_trends(keyword_groups):
    if not keyword_groups:
        return {'results': []}
    end_date   = datetime.now().strftime('%Y-%m-%d')
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
            data=body, method='POST',
            headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
                'Content-Type': 'application/json'
            }
        )
        return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
    except Exception as e:
        print(f"[네이버 데이터랩] {e}")
        return {'results': []}


# ==========================================
# 유튜브 인기 급상승 (전체)
# ==========================================

def get_youtube_hype_trends():
    if not YOUTUBE_API_KEY:
        return [{"error": "YOUTUBE_API_KEY 환경변수 없음"}]
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        "?part=snippet,statistics&chart=mostPopular"
        f"&regionCode=KR&maxResults=10&key={YOUTUBE_API_KEY}"
    )
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        if 'error' in data:
            return [{"error": data['error'].get('message', '알 수 없는 에러')}]
        result = []
        for item in data.get('items', []):
            vid = item['id']
            sn  = item['snippet']
            st  = item.get('statistics', {})
            th  = sn.get('thumbnails', {})
            result.append({
                'videoId':      vid,
                'title':        sn.get('title', ''),
                'channelTitle': sn.get('channelTitle', ''),
                'viewCount':    int(st.get('viewCount', 0)),
                'thumbnail': (
                    th.get('maxres', {}).get('url') or
                    th.get('high',   {}).get('url') or
                    th.get('medium', {}).get('url') or
                    f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"
                ),
                'url': f"https://www.youtube.com/watch?v={vid}",
            })
        return result
    except urllib.error.HTTPError as e:
        print(f"[유튜브] HTTP {e.code}: {e.read().decode('utf-8')}")
        return [{"error": f"HTTP {e.code}"}]
    except Exception as e:
        print(f"[유튜브] {e}")
        return [{"error": str(e)}]


# ==========================================
# 구글 트렌드 (GAS 프록시)
# ==========================================

def get_google_trends():
    if not GAS_PROXY_URL:
        return []
    try:
        resp = requests.get(
            GAS_PROXY_URL, timeout=15,
            allow_redirects=True,
            headers={"Accept": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []) if data.get("status") == "ok" else []
    except Exception as e:
        print(f"[구글 트렌드] {e}")
        return []


# ==========================================
# 유튜브 뮤직 차트 (Spotify 대체)
# videoCategoryId=10 (Music) + regionCode=KR
# ==========================================

def get_spotify_trends():
    if not YOUTUBE_API_KEY:
        return [{"error": "YOUTUBE_API_KEY 환경변수 없음"}]
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        "?part=snippet,statistics"
        "&chart=mostPopular"
        "&regionCode=KR"
        "&videoCategoryId=10"
        "&maxResults=10"
        f"&key={YOUTUBE_API_KEY}"
    )
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        if 'error' in data:
            msg = data['error'].get('message', '알 수 없는 에러')
            print(f"[YT Music] {msg}")
            return [{"error": f"YouTube API 오류: {msg}"}]
        items = data.get('items', [])
        if not items:
            return [{"error": "YouTube 음악 차트 데이터 없음"}]
        result = []
        for i, item in enumerate(items):
            vid = item['id']
            sn  = item.get('snippet', {})
            st  = item.get('statistics', {})
            th  = sn.get('thumbnails', {})
            # "아티스트명 - Topic" → "아티스트명" 정리
            artist = re.sub(r'\s*-\s*Topic$', '', sn.get('channelTitle', '')).strip()
            result.append({
                'rank':      i + 1,
                'keyword':   sn.get('title', ''),
                'title':     sn.get('title', ''),
                'artist':    artist,
                'image': (
                    th.get('maxres', {}).get('url') or
                    th.get('high',   {}).get('url') or
                    th.get('medium', {}).get('url') or
                    f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"
                ),
                'url':       f"https://www.youtube.com/watch?v={vid}",
                'viewCount': int(st.get('viewCount', 0)),
                'videoId':   vid,
            })
        return result
    except urllib.error.HTTPError as e:
        print(f"[YT Music] HTTP {e.code}: {e.read().decode('utf-8')[:200]}")
        return [{"error": f"YouTube HTTP {e.code}"}]
    except Exception as e:
        print(f"[YT Music] {type(e).__name__}: {e}")
        return [{"error": f"YouTube Music 오류: {type(e).__name__}"}]


# ==========================================
# 스팀
# ==========================================

def _fetch_current_players(appid: str) -> int:
    """
    ISteamUserStats/GetNumberOfCurrentPlayers 로 실시간 동시접속자 수 조회.
    실패 시 0 반환.
    """
    try:
        url = (
            "https://api.steampowered.com/ISteamUserStats"
            f"/GetNumberOfCurrentPlayers/v1/?appid={appid}"
        )
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8'))
        return int(data.get('response', {}).get('player_count', 0))
    except Exception as e:
        print(f"[Steam 실시간] appid {appid}: {e}")
        return 0


def _get_steam_names(appids: list) -> dict:
    """
    SteamSpy 우선 병렬 조회 → 실패한 appid는 Steam Store API fallback.
    반환: {appid: name}
    """
    result = {}

    def fetch_spy(appid):
        try:
            url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
            req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8'))
            if data and data.get('name'):
                return appid, data['name']
        except Exception as e:
            print(f"[SteamSpy] {appid}: {e}")
        return appid, None

    with ThreadPoolExecutor(max_workers=5) as ex:
        for appid, name in ex.map(fetch_spy, appids):
            if name:
                result[appid] = name

    # Store API fallback
    missing = [a for a in appids if a not in result]
    if missing:
        try:
            url = (
                f"https://store.steampowered.com/api/appdetails"
                f"?appids={','.join(missing)}&cc=kr&l=korean&filters=basic"
            )
            req   = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            store = json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8'))
            for appid in missing:
                info = store.get(appid, {})
                if info.get('success') and info.get('data', {}).get('name'):
                    result[appid] = info['data']['name']
        except Exception as e:
            print(f"[Steam Store fallback] {e}")

    return result


def get_steam_trends():
    try:
        # 1. 인기 순위 조회
        url  = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        raw  = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        data = json.loads(raw)

        ranks = data.get('response', {}).get('ranks', [])
        if not ranks:
            print(f"[Steam] ranks 비어 있음: {raw[:200]}")
            return [{"error": "Steam 랭킹 데이터 없음"}]

        top_10 = ranks[:10]
        appids = [str(g['appid']) for g in top_10]

        # 2. 이름 조회 + 실시간 동시접속자를 병렬로 동시에 처리
        with ThreadPoolExecutor(max_workers=15) as ex:
            names_future   = ex.submit(_get_steam_names, appids)
            player_futures = {ex.submit(_fetch_current_players, aid): aid for aid in appids}

            names   = names_future.result()
            players = {}
            for future in as_completed(player_futures):
                aid = player_futures[future]
                players[aid] = future.result()

        # 3. 결과 조합
        trends = []
        for i, game in enumerate(top_10):
            appid   = str(game['appid'])
            peak    = int(game.get('peak_in_game') or 0)
            current = players.get(appid, 0)
            name    = names.get(appid) or f"App {appid}"
            trends.append({
                'rank':               i + 1,
                'keyword':            name,
                'concurrent_players': f"{current:,}" if current else "집계 중",
                'peak_players':       f"{peak:,}",
                'image':              f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                'url':                f"https://store.steampowered.com/app/{appid}/",
            })

        return trends

    except urllib.error.HTTPError as e:
        print(f"[Steam] HTTP {e.code}: {e.read().decode('utf-8')}")
        return [{"error": f"Steam HTTP {e.code}"}]
    except json.JSONDecodeError as e:
        print(f"[Steam] JSON 파싱 실패: {e}")
        return [{"error": "Steam API 응답 파싱 실패"}]
    except Exception as e:
        print(f"[Steam] {type(e).__name__}: {e}")
        return [{"error": f"Steam 오류: {type(e).__name__}"}]


# ==========================================
# 깃허브
# ==========================================

def get_github_trends():
    try:
        last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        url  = (
            f"https://api.github.com/search/repositories"
            f"?q=created:>{last_week}&sort=stars&order=desc&per_page=10"
        )
        req  = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        return [
            {
                'rank':        i + 1,
                'keyword':     item.get('full_name', ''),
                'description': item.get('description') or '설명 없음',
                'stars':       f"{item.get('stargazers_count', 0):,}",
                'language':    item.get('language') or '언어 미상',
                'url':         item.get('html_url', ''),
            }
            for i, item in enumerate(data.get('items', []))
        ]
    except urllib.error.HTTPError as e:
        print(f"[GitHub] HTTP {e.code}: {e.read().decode('utf-8')}")
        return [{"error": f"GitHub HTTP {e.code}"}]
    except Exception as e:
        print(f"[GitHub] {e}")
        return [{"error": str(e)}]


# ==========================================
# 업비트 (KRW 마켓 거래대금 순위)
# ==========================================

def get_upbit_trends():
    try:
        req = urllib.request.Request(
            "https://api.upbit.com/v1/market/all?isDetails=false",
            headers={'Accept': 'application/json'}
        )
        market_data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))

        krw_markets  = []
        market_names = {}
        for item in market_data:
            if item['market'].startswith('KRW-'):
                krw_markets.append(item['market'])
                market_names[item['market']] = item['korean_name']

        ticker_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets)}"
        req = urllib.request.Request(ticker_url, headers={'Accept': 'application/json'})
        ticker_data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))

        sorted_tickers = sorted(
            ticker_data,
            key=lambda x: x.get('acc_trade_price_24h', 0),
            reverse=True
        )

        trends = []
        for i, ticker in enumerate(sorted_tickers[:10]):
            mc  = ticker['market']
            sym = mc.replace("KRW-", "")
            vol = ticker.get('acc_trade_price_24h', 0)
            trends.append({
                'rank':        i + 1,
                'keyword':     f"{market_names.get(mc, mc)} ({sym})",
                'price':       f"{ticker.get('trade_price', 0):,}원",
                'change_rate': f"{ticker.get('signed_change_rate', 0) * 100:+.2f}%",
                'volume': (
                    f"{vol / 1_000_000_000_000:.1f}조 원"
                    if vol >= 1_000_000_000_000
                    else f"{int(vol / 100_000_000):,}억 원"
                ),
                'url': f"https://upbit.com/exchange?code=CRIX.UPBIT.{mc}",
            })
        return trends

    except urllib.error.HTTPError as e:
        print(f"[업비트] HTTP {e.code}: {e.read().decode('utf-8')}")
        return [{"error": f"업비트 HTTP {e.code}"}]
    except Exception as e:
        print(f"[업비트] {e}")
        return [{"error": str(e)}]


# ==========================================
# API 라우트
# ==========================================

@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        live_kw = get_realtime_keywords()
        r1 = fetch_naver_trends([{"groupName": kw, "keywords": [kw]} for kw in live_kw[:5]])
        r2 = fetch_naver_trends([{"groupName": kw, "keywords": [kw]} for kw in live_kw[5:]])
        all_results = r1.get('results', []) + r2.get('results', [])
        all_results.sort(
            key=lambda x: x['data'][-1]['ratio'] if x.get('data') else 0,
            reverse=True
        )
        naver_trends = [
            {
                'rank':    i + 1,
                'keyword': item['title'],
                'change':  'new' if i < 2 else 'up' if i < 5 else 'same',
                'heat':    min(int(item['data'][-1]['ratio']) if item.get('data') else 0, 100),
                'sources': ['실시간검색어'],
            }
            for i, item in enumerate(all_results)
        ]
        return jsonify({
            'success': True,
            'data':    naver_trends,
            'youtube': get_youtube_hype_trends(),
            'google':  get_google_trends(),
            'spotify': get_spotify_trends(),
            'steam':   get_steam_trends(),
            'github':  get_github_trends(),
            'upbit':   get_upbit_trends(),
            'source':  'auto-trend',
        })
    except Exception as e:
        print(f"[/trends] {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/debug-naver')
def debug_naver():
    return jsonify({"status": "ok", "keywords": get_realtime_keywords()})

@app.route('/debug-google')
def debug_google():
    return jsonify({"success": True, "data": get_google_trends()})

@app.route('/debug-spotify')
def debug_spotify():
    return jsonify({"success": True, "data": get_spotify_trends()})

@app.route('/debug-steam')
def debug_steam():
    return jsonify({"success": True, "data": get_steam_trends()})

@app.route('/debug-github')
def debug_github():
    return jsonify({"success": True, "data": get_github_trends()})

@app.route('/debug-upbit')
def debug_upbit():
    return jsonify({"success": True, "data": get_upbit_trends()})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
