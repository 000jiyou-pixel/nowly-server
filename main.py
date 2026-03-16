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
    rss_urls = [
        "https://news.naver.com/main/rss/allnews.nhn",
        "https://rss.etnews.com/Section901.xml",
        "https://www.yonhapnewstv.co.kr/browse/feed/",
    ]
    all_titles = []
    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=5)
            content = response.read().decode('utf-8', errors='ignore')
            titles = re.findall(r'<title>(.*?)</title>', content)
            all_titles.extend(titles[2:])
        except:
            continue
    words = []
    for title in all_titles:
        title = re.sub(r'<[^>]+>', '', title)
        found = re.findall(r'[가-힣]{2,8}', title)
        words.extend(found)
    stopwords = {'이번', '지난', '오늘', '내일', '올해', '지금', '우리', '이후', '이전',
                 '관련', '대한', '통해', '위해', '대해', '라고', '이라', '에서', '으로',
                 '에도', '에게', '부터', '까지', '에는', '이다', '있다', '했다', '한다',
                 '된다', '있는', '하는', '하고', '되고', '이고', '뉴스', '기자', '제공',
                 '저작', '무단', '재배', '금지', '서울', '전재', '복제'}
    words = [w for w in words if w not in stopwords and len(w) >= 2]
    counter = Counter(words)
    return counter.most_common(20)

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
        if not news_keywords:
            raise Exception("뉴스 키워드 추출 실패")
        top_keywords = [kw for kw, count in news_keywords[:10]]
        group1 = [{"groupName": kw, "keywords": [kw]} for kw in top_keywords[:5]]
        group2 = [{"groupName": kw, "keywords": [kw]} for kw in top_keywords[5:10]]
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
            news_count = next((count for kw, count in news_keywords if kw == item['title']), 0)
            score = int(ratio * 0.7 + min(news_count * 3, 30))
            trends.append({
                'rank': i + 1,
                'keyword': item['title'],
                'change': 'new' if i < 2 else 'up' if i < 5 else 'same',
                'heat': min(score, 100),
                'sources': ['네이버', '언론'],
                'news_count': news_count
            })
        return jsonify({
            'success': True,
            'data': trends,
            'source': 'naver+news',
            'updated_at': datetime.now().strftime('%H:%M')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
