from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')

# 1. 구글 트렌드 우회해서 실시간 키워드 가져오는 함수 (수정됨 ⭐️)
def get_realtime_keywords():
    try:
        # 구글에 직접 안 가고, rss2json 이라는 우회 서비스를 통해 한국 구글 트렌드를 가져옵니다.
        url = "https://api.rss2json.com/v1/api.json?rss_url=https%3A%2F%2Ftrends.google.com%2Ftrends%2Ftrendingsearches%2Fdaily%2Frss%3Fgeo%3DKR"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        
        keywords = []
        for item in data.get('items', []):
            title = item.get('title')
            if title and title not in keywords:
                keywords.append(title)
            if len(keywords) >= 10:
                break
                
        # 만약 우회 서비스에서도 못 가져왔다면 에러를 발생시킵니다.
        if not keywords:
            raise Exception("키워드를 찾을 수 없음")
            
        return keywords
        
    except Exception as e:
        print(f"키워드 추출 실패: {e}")
        return ["날씨", "비트코인", "환율", "삼성전자", "넷플릭스", "손흥민", "이재명", "아이유", "뉴진스", "GPT"]

# 2. 네이버 데이터랩 API
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
                'sources': ['구글/네이버'],
            })
            
        return jsonify({'success': True, 'data': trends, 'source': 'auto-trend'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
