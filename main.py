from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')

KEYWORD_GROUPS = [
    {"groupName": "정치/사회", "keywords": ["이재명", "윤석열", "국회"]},
    {"groupName": "연예/문화", "keywords": ["아이유", "뉴진스", "무한도전"]},
    {"groupName": "스포츠", "keywords": ["손흥민", "KBO", "류현진"]},
    {"groupName": "경제", "keywords": ["비트코인", "삼성전자", "환율"]},
    {"groupName": "IT/테크", "keywords": ["GPT", "갤럭시", "애플"]},
    {"groupName": "생활", "keywords": ["미세먼지", "날씨", "부동산"]},
]

@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        body = json.dumps({
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "date",
            "keywordGroups": KEYWORD_GROUPS
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://openapi.naver.com/v1/datalab/search",
            data=body,
            headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
                'Content-Type': 'application/json'
            }
        )

        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode('utf-8'))

        results_sorted = sorted(
            result.get('results', []),
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
                'heat': int(ratio),
                'sources': ['네이버']
            })

        return jsonify({'success': True, 'data': trends, 'source': 'naver'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
