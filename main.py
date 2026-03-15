from flask import Flask, jsonify
from flask_cors import CORS
import urllib.request
import json
import re

app = Flask(__name__)
CORS(app)

@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        content = response.read().decode('utf-8')
        
        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
        titles = [t for t in titles if t != 'Daily Search Trends']
        
        trends = []
        for i, keyword in enumerate(titles[:20]):
            trends.append({
                'rank': i + 1,
                'keyword': keyword,
                'change': 'up' if i < 5 else 'same',
                'heat': max(10, 100 - (i * 4)),
                'sources': ['구글']
            })
        
        return jsonify({'success': True, 'data': trends})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
