from flask import Flask, render_template, jsonify, request
import threading
import json
import os
import main

app = Flask(__name__)

# Global variables to control the background thread
monitor_thread = None
stop_event = threading.Event()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    is_running = monitor_thread is not None and monitor_thread.is_alive()
    return jsonify({'running': is_running})

@app.route('/api/start', methods=['POST'])
def start():
    global monitor_thread, stop_event
    if monitor_thread is None or not monitor_thread.is_alive():
        stop_event.clear()
        monitor_thread = threading.Thread(target=main.start_monitoring, args=(stop_event,))
        monitor_thread.daemon = True
        monitor_thread.start()
        return jsonify({'status': 'started'})
    return jsonify({'status': 'already running'})

@app.route('/api/stop', methods=['POST'])
def stop():
    global stop_event
    if monitor_thread is not None and monitor_thread.is_alive():
        stop_event.set()
        return jsonify({'status': 'stopping'})
    return jsonify({'status': 'not running'})

@app.route('/api/summaries')
def get_summaries():
    summaries = []
    if os.path.exists(main.SUMMARIES_FILE):
        try:
            with open(main.SUMMARIES_FILE, 'r') as f:
                summaries = json.load(f)
        except Exception:
            pass
    return jsonify(summaries)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
