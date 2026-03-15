from flask import Flask, jsonify
from flask_cors import CORS
from pytrends.request import TrendReq
import json

app = Flask(__name__)
CORS(app)

@app.route('/trends', methods=['GET'])
def get_trends():
    try:
        pytrends = TrendReq(hl='ko', tz=540)
        trending = pytrends.trending_searches(pn='south_korea')
        trends = []
        for i, keyword in enumerate(trending[0].tolist()[:20]):
            trends.append({
                'rank': i + 1,
                'keyword': keyword,
                'change': 'up',
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
