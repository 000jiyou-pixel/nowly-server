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

def fetch_naver_trends(keyword_groups):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

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
        # 1차 요청 (5개)
        group1 = [
            {"groupName": "손흥민", "keywords": ["손흥민"]},
            {"groupName": "이재명", "keywords": ["이재명"]},
            {"groupName": "비트코인", "keywords": ["비트코인"]},
            {"groupName": "아이유", "keywords": ["아이유"]},
            {"groupName": "뉴진스", "keywords": ["뉴진스"]},
        ]
        # 2차 요청 (5개)
        group2 = [
            {"groupName": "날씨", "keywords": ["날씨"]},
            {"groupName": "삼성전자", "keywords": ["삼성전자"]},
            {"groupName": "환율", "keywords": ["환율"]},
            {"groupName": "GPT", "keywords": ["GPT"]},
            {"groupName": "넷플릭스", "keywords": ["넷플릭스"]},
        ]

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
                'heat': int(ratio),
                'sources': ['네이버']
            })

        return jsonify({'success': True, 'data': trends, 'source': 'naver'})

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        return jsonify({'success': False, 'error': f'HTTP {e.code}: {body}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
