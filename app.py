from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import re
import requests
import base64
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# --- 환경 변수 설정 ---
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
GAS_PROXY_URL = os.environ.get('GAS_PROXY_URL', '')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', '')

DEFAULT_KEYWORDS = ["환율", "날씨", "삼성전자", "이재명", "손흥민", "GPT", "아이유", "뉴진스", "비트코인", "넷플릭스"]


# ==========================================
# 네이버
# ==========================================

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
                    if w not in found_keywords and w not in [
                        '기자', '뉴스', '속보', '오늘', '지금', '최근',
                        '관련', '발표', '대한', '이후', '이번', '지난'
                    ]:
                        found_keywords.append(w)
                if len(found_keywords) >= 10:
                    break
            if len(found_keywords) >= 10:
                break
        return found_keywords[:10] if len(found_keywords) >= 5 else DEFAULT_KEYWORDS
    except Exception as e:
        print(f"[네이버 키워드] 추출 실패: {e}")
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
        print(f"[네이버 데이터랩] API 에러: {e}")
        return {'results': []}


# ==========================================
# 유튜브
# ==========================================

def get_youtube_hype_trends():
    if not YOUTUBE_API_KEY:
        return [{"error": "YOUTUBE_API_KEY 환경변수 없음"}]
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics&chart=mostPopular"
        f"&regionCode=KR&maxResults=10&key={YOUTUBE_API_KEY}"
    )
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        if 'error' in data:
            return [{"error": data['error'].get('message', '알 수 없는 에러')}]
        hype_videos = []
        for item in data.get('items', []):
            video_id = item['id']
            snippet = item['snippet']
            statistics = item.get('statistics', {})
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
        error_msg = e.read().decode('utf-8')
        print(f"[유튜브] HTTP {e.code}: {error_msg}")
        return [{"error": f"HTTP {e.code}: {error_msg}"}]
    except Exception as e:
        print(f"[유튜브] 에러: {e}")
        return [{"error": str(e)}]


# ==========================================
# 구글 트렌드 (GAS 프록시)
# ==========================================

def get_google_trends():
    if not GAS_PROXY_URL:
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
            return []
        return data.get("data", [])
    except Exception as e:
        print(f"[구글 트렌드] 에러: {e}")
        return []


# ==========================================
# 스포티파이 (수정)
# ==========================================

def get_spotify_token():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    url = "https://accounts.spotify.com/api/token"
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_base64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Basic {auth_base64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    try:
        response = urllib.request.urlopen(req, timeout=10)
        res_data = json.loads(response.read().decode('utf-8'))
        return res_data.get('access_token')
    except urllib.error.HTTPError as e:
        print(f"[Spotify 토큰] HTTP {e.code}: {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"[Spotify 토큰] 에러: {e}")
        return None


def _parse_spotify_playlist(data):
    """플레이리스트 응답에서 트랙 목록 파싱 (공통 헬퍼)"""
    trends = []
    for item in data.get('items', []):
        if not item:
            continue
        track = item.get('track')
        if not track or track.get('type') != 'track':
            continue
        title = track.get('name', 'Unknown')
        artists = ", ".join([a.get('name', '') for a in track.get('artists', [])])
        images = track.get('album', {}).get('images', [])
        album_image = images[0].get('url', '') if images else ''
        external_url = track.get('external_urls', {}).get('spotify', '')
        trends.append({
            'rank': len(trends) + 1,
            'keyword': f"{title} - {artists}",
            'title': title,
            'artist': artists,
            'image': album_image,
            'url': external_url
        })
        if len(trends) >= 10:
            break
    return trends


def _fetch_spotify_playlist(token, playlist_id, market=None):
    """단일 플레이리스트 fetch, 성공 시 트랙 리스트 반환 / 실패 시 None"""
    market_param = f"&market={market}" if market else ""
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=20{market_param}"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        return _parse_spotify_playlist(data)
    except urllib.error.HTTPError as e:
        print(f"[Spotify] 플레이리스트 {playlist_id} HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[Spotify] 플레이리스트 {playlist_id} 에러: {e}")
        return None


def get_spotify_trends():
    token = get_spotify_token()
    if not token:
        return [{"error": "Spotify 토큰 발급 실패 (API 키를 확인하세요)"}]

    # 우선순위대로 시도할 플레이리스트 목록
    # Client Credentials로 접근 가능한 공개 플레이리스트만 사용
    candidates = [
        ("37i9dQZEVXbMDoHDwVN2tF", None),       # Global Top 50 (시장 제한 없음)
        ("37i9dQZEVXbJiZcmkflKDy", "KR"),        # Korea Top 50
        ("37i9dQZEVXbNxXF4SkHj9F", None),        # Global Top 50 (구 ID)
        ("37i9dQZF1DXcBWIGoYBM5M", None),        # Today's Top Hits
    ]

    for playlist_id, market in candidates:
        tracks = _fetch_spotify_playlist(token, playlist_id, market)
        if tracks:
            print(f"[Spotify] 플레이리스트 {playlist_id} 성공 ({len(tracks)}곡)")
            return tracks

    return [{"error": "Spotify 모든 플레이리스트 접근 실패 - 네트워크 또는 API 키를 확인하세요"}]


# ==========================================
# 스팀 (수정)
# ==========================================

def _get_steam_game_details(appids):
    """Steam Store API로 게임 상세정보 조회, 실패 시 빈 dict 반환"""
    try:
        appids_str = ",".join(appids)
        url = (
            f"https://store.steampowered.com/api/appdetails"
            f"?appids={appids_str}&cc=kr&l=korean"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=15)
        return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        print(f"[Steam] appdetails 조회 실패: {e}")
        return {}


def get_steam_trends():
    try:
        # GetMostPlayedGames로 현재 인기 게임 랭킹 조회
        url = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        raw = response.read().decode('utf-8')
        data = json.loads(raw)

        ranks = data.get('response', {}).get('ranks', [])
        if not ranks:
            print(f"[Steam] ranks 비어 있음. 전체 응답: {raw[:300]}")
            return [{"error": "Steam 랭킹 데이터 없음"}]

        top_10 = ranks[:10]
        appids = [str(g['appid']) for g in top_10]

        # 게임 상세 정보 (실패해도 폴백으로 진행)
        details_data = _get_steam_game_details(appids)

        trends = []
        for i, game in enumerate(top_10):
            appid = str(game['appid'])
            # 필드명 안전 처리 (API 버전별로 다를 수 있음)
            concurrent = int(game.get('concurrent_in_game') or game.get('concurrent', 0))
            peak = int(game.get('peak_in_game') or game.get('peak', concurrent))

            game_info = details_data.get(appid, {})
            if game_info.get('success') and game_info.get('data'):
                name = game_info['data'].get('name') or f"App {appid}"
                image = game_info['data'].get('header_image') or \
                    f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
            else:
                # Store API 실패 시 CDN URL로 폴백
                name = f"App {appid}"
                image = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

            trends.append({
                'rank': i + 1,
                'keyword': name,
                'concurrent_players': f"{concurrent:,}",
                'peak_players': f"{peak:,}",
                'image': image,
                'url': f"https://store.steampowered.com/app/{appid}/"
            })

        return trends

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[Steam] HTTP {e.code}: {error_body}")
        return [{"error": f"Steam HTTP {e.code}"}]
    except json.JSONDecodeError as e:
        print(f"[Steam] JSON 파싱 실패: {e}")
        return [{"error": "Steam API 응답 파싱 실패"}]
    except Exception as e:
        print(f"[Steam] 에러: {type(e).__name__}: {e}")
        return [{"error": f"Steam 오류: {type(e).__name__}"}]


# ==========================================
# 깃허브
# ==========================================

def get_github_trends():
    try:
        last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        url = (
            f"https://api.github.com/search/repositories"
            f"?q=created:>{last_week}&sort=stars&order=desc&per_page=10"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        trends = []
        for i, item in enumerate(data.get('items', [])):
            trends.append({
                'rank': i + 1,
                'keyword': item.get('full_name', ''),
                'description': item.get('description') or '설명 없음',
                'stars': f"{item.get('stargazers_count', 0):,}",
                'language': item.get('language') or '언어 미상',
                'url': item.get('html_url', '')
            })
        return trends
    except urllib.error.HTTPError as e:
        print(f"[GitHub] HTTP {e.code}: {e.read().decode('utf-8')}")
        return [{"error": f"GitHub HTTP {e.code}"}]
    except Exception as e:
        print(f"[GitHub] 에러: {e}")
        return [{"error": str(e)}]


# ==========================================
# 업비트
# ==========================================

def get_upbit_trends():
    try:
        # 1. 모든 마켓 정보 (심볼 → 한글명 매핑)
        market_url = "https://api.upbit.com/v1/market/all?isDetails=false"
        market_req = urllib.request.Request(
            market_url, headers={'Accept': 'application/json'}
        )
        market_res = urllib.request.urlopen(market_req, timeout=10)
        market_data = json.loads(market_res.read().decode('utf-8'))

        krw_markets = []
        market_names = {}
        for item in market_data:
            if item['market'].startswith('KRW-'):
                krw_markets.append(item['market'])
                market_names[item['market']] = item['korean_name']

        # 2. 원화 마켓 현재가 및 거래대금
        markets_str = ",".join(krw_markets)
        ticker_url = f"https://api.upbit.com/v1/ticker?markets={markets_str}"
        ticker_req = urllib.request.Request(
            ticker_url, headers={'Accept': 'application/json'}
        )
        ticker_res = urllib.request.urlopen(ticker_req, timeout=10)
        ticker_data = json.loads(ticker_res.read().decode('utf-8'))

        # 3. 24시간 거래대금 기준 내림차순 정렬
        sorted_tickers = sorted(
            ticker_data,
            key=lambda x: x.get('acc_trade_price_24h', 0),
            reverse=True
        )

        trends = []
        for i, ticker in enumerate(sorted_tickers[:10]):
            market_code = ticker['market']
            korean_name = market_names.get(market_code, market_code)
            price = ticker.get('trade_price', 0)
            change_rate = ticker.get('signed_change_rate', 0) * 100
            trade_volume_24h = ticker.get('acc_trade_price_24h', 0)
            symbol = market_code.replace("KRW-", "")

            if trade_volume_24h >= 1_000_000_000_000:
                volume_str = f"{trade_volume_24h / 1_000_000_000_000:.1f}조 원"
            else:
                volume_str = f"{int(trade_volume_24h / 100_000_000):,}억 원"

            trends.append({
                'rank': i + 1,
                'keyword': f"{korean_name} ({symbol})",
                'price': f"{price:,}원",
                'change_rate': f"{change_rate:+.2f}%",
                'volume': volume_str,
                'url': f"https://upbit.com/exchange?code=CRIX.UPBIT.{market_code}"
            })

        return trends
    except urllib.error.HTTPError as e:
        print(f"[업비트] HTTP {e.code}: {e.read().decode('utf-8')}")
        return [{"error": f"업비트 HTTP {e.code}"}]
    except Exception as e:
        print(f"[업비트] 에러: {e}")
        return [{"error": str(e)}]


# ==========================================
# API 라우트
# ==========================================

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
        spotify_data = get_spotify_trends()
        steam_data = get_steam_trends()
        github_data = get_github_trends()
        upbit_data = get_upbit_trends()

        return jsonify({
            'success': True,
            'data': trends,
            'youtube': youtube_data,
            'google': google_data,
            'spotify': spotify_data,
            'steam': steam_data,
            'github': github_data,
            'upbit': upbit_data,
            'source': 'auto-trend'
        })
    except Exception as e:
        print(f"[/trends] 전체 에러: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/debug-naver')
def debug_naver():
    keywords = get_realtime_keywords()
    return jsonify({"status": "ok", "keywords": keywords})


@app.route('/debug-google')
def debug_google():
    data = get_google_trends()
    return jsonify({"success": True, "data": data})


@app.route('/debug-spotify')
def debug_spotify():
    data = get_spotify_trends()
    return jsonify({"success": True, "data": data})


@app.route('/debug-steam')
def debug_steam():
    data = get_steam_trends()
    return jsonify({"success": True, "data": data})


@app.route('/debug-github')
def debug_github():
    data = get_github_trends()
    return jsonify({"success": True, "data": data})


@app.route('/debug-upbit')
def debug_upbit():
    data = get_upbit_trends()
    return jsonify({"success": True, "data": data})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
