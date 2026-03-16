from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import urllib.error
import json
import os
import re
from datetime import datetime, timedelta
from collections import Counter

app = Flask(__name__)
CORS(app)

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')

def get_news_keywords():
    urls = [
        "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/topics/CAAqIQgKIhtDQkFTRGdvSUwyMHZNRFZxYUdjU0FtdHZLQUFQAQ?hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZxYUdjU0FtdHZHZ0pMVWlnQVAB?hl=ko&gl=KR&ceid=KR:ko",
    ]
    all_titles = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response = urllib.request.urlopen(req, timeout=10)
            content = response.read().decode('utf-8', errors='ignore')
            titles = re.findall(r'<title>(.*?)</title>', content, re.DOTALL)
            clean = [re.sub(r'<[^>]+>|\[CDATA\[|\]\]', '', t).strip() for t in titles[1:40]]
            all_titles.extend(clean)
        except Exception as e:
            continue

    words = []
    for title in all_titles:
        found = re.findall(r'[가-힣]{2,8}', title)
        words.extend(found)

    stopwords = {
        '이번', '지난', '오늘', '내일', '올해', '지금', '우리', '이후', '이전',
        '관련', '대한', '통해', '위해', '대해', '라고', '이라', '에서', '으로',
        '에도', '에게', '부터', '까지', '에는', '이다', '있다', '했다', '한다',
        '된다', '있는', '하는', '하고', '되고', '이고', '뉴스', '기자', '제공',
        '저작', '무단', '재배', '금지', '서울', '전재', '복제', '속보', '단독',
        '긴급', '종합', '특보', '이라며', '하며', '으며', '라며', '한편', '또한',
        '하지만', '그러나', '따라서', '결국', '이에', '이를', '이와', '이가',
        '구글', '네이버', '카카오', '삼성', '현대', '기아', '포스코'
    }
    words = [w for w in words if w not in stopwords and len(w) >= 2]
    counter = Counter(words)
    top = counter.most_common(30)
    return top

def fetch_naver_trends(keyword_groups):
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
        news_keywords = get_news_keywords()

        if news_keywords:
            top_keywords = [kw for kw, count in news_keywords[:10]]
            group1 = [{"groupName": kw, "keywords": [kw]} for kw in top_keywords[:5]]
            group2 = [{"groupName": kw, "keywords": [kw]} for kw in top_keywords[5:10]]
            source = 'google_news+naver'
        else:
            group1 = [
                {"groupName": "날씨", "keywords": ["날씨"]},
                {"groupName": "비트코인", "keywords": ["비트코인"]},
                {"groupName": "환율", "keywords": ["환율"]},
                {"groupName": "손흥민", "keywords": ["손흥민"]},
                {"groupName": "이재명", "keywords": ["이재명"]},
            ]
            group2 = [
                {"groupName": "삼성전자", "keywords": ["삼성전자"]},
                {"groupName": "아이유", "keywords": ["아이유"]},
                {"groupName": "뉴진스", "keywords": ["뉴진스"]},
                {"groupName": "GPT", "keywords": ["GPT"]},
                {"groupName": "넷플릭스", "keywords": ["넷플릭스"]},
            ]
            source = 'naver_only'

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
            news_count = next((count for kw, count in news_keywords if kw == item['title']), 0) if news_keywords else 0
            score = int(ratio * 0.7 + min(news_count * 3, 30))
            trends.append({
                'rank': i + 1,
                'keyword': item['title'],
                'change': 'new' if i < 2 else 'up' if i < 5 else 'same',
                'heat': min(max(score, int(ratio)), 100),
                'sources': ['구글뉴스', '네이버'] if news_keywords else ['네이버'],
                'news_count': news_count
            })

        return jsonify({
            'success': True,
            'data': trends,
            'source': source,
            'updated_at': datetime.now().strftime('%H:%M')
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/news_keywords', methods=['GET'])
def news_keywords_debug():
    keywords = get_news_keywords()
    return jsonify({'keywords': keywords})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

완료되면 1~2분 후 이 주소로 먼저 테스트해주세요!
```
https://nowly-server-production.up.railway.app/news_keywords
