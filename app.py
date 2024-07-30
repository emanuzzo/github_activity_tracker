### no shebang needed because I am working on windows
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import requests
import logging
import config

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///github_events.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    repo = db.Column(db.String(80))
    event_type = db.Column(db.String(80))
    event_time = db.Column(db.DateTime)

# Ensure database tables are created within the application context
with app.app_context():
    db.create_all()

def fetch_github_commits(repo):
    headers = {"Authorization": f"token {config.TOKEN}"}
    response = requests.get(f"{config.GITHUB_API_URL}/repos/{repo}/commits", headers=headers)
    response.raise_for_status()
    commits = response.json()
    logging.debug(f"Fetched commits for {repo}: {commits}")
    return commits

@app.route('/commits', methods=['GET'])
def get_commits():
    logging.debug("Fetching commits...")
    commits_data = {}
    for repo in config.REPOSITORIES:
        commits = fetch_github_commits(repo)
        commits_data[repo] = commits
        logging.debug(f"Commits for {repo}: {commits}")
    return jsonify(commits_data)

def fetch_github_events(repo):
    headers = {"Authorization": f"token {config.TOKEN}"}
    response = requests.get(f"{config.GITHUB_API_URL}/repos/{repo}/events", headers=headers)
    response.raise_for_status()
    events = response.json()
    logging.debug(f"Fetched events for {repo}: {events}")
    return events

def save_events(repo, events):
    for event in events:
        event_time = datetime.strptime(event['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        new_event = Event(repo=repo, event_type=event['type'], event_time=event_time)
        db.session.add(new_event)
        logging.debug(f"Saving event: {new_event}")
    db.session.commit()
    logging.debug("Events saved.")

@app.route('/update', methods=['POST'])
def update_events():
    logging.debug("Updating events...")
    for repo in config.REPOSITORIES:
        events = fetch_github_events(repo)
        logging.debug(f"Fetched events for {repo}: {events}")
        save_events(repo, events)
    return jsonify({"message": "Events updated"}), 201

def process_events(events, now):
    event_times = {}
    for event in events:
        event_type = event.event_type
        event_time = event.event_time
        if event_time > now - timedelta(days=7):
            if event_type not in event_times:
                event_times[event_type] = []
            event_times[event_type].append(event_time)
            logging.debug(f"Added event_time for {event_type}: {event_time}")
    
    avg_times = {}
    for event_type, times in event_times.items():
        logging.debug(f"Processing event_type {event_type} with times: {times}")
        if len(times) > 1:
            diffs = [(times[i-1] - times[i]).total_seconds() for i in range(1, len(times))]
            logging.debug(f"Time differences for {event_type}: {diffs}")
            avg_time = sum(diffs) / len(diffs)
            avg_times[event_type] = avg_time
            logging.debug(f"Average time for {event_type}: {avg_time}")
        else:
            avg_times[event_type] = 0.0  # Handle cases with only one event
            logging.debug(f"Only one event for {event_type}, setting average time to 0.0")
    
    return avg_times

@app.route('/stats', methods=['GET'])
def get_stats():
    logging.debug("Fetching stats...")
    stats = {}
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    for repo in config.REPOSITORIES:
        events = Event.query.filter(Event.repo == repo, Event.event_time > seven_days_ago).order_by(Event.event_time.desc()).limit(500).all()  # Limite di 500 eventi
        stats[repo] = process_events(events, now)
        logging.debug(f"Stats for {repo}: {stats[repo]}")
    
    # Format the stats for display
    formatted_stats = {repo: {event_type: f"{avg_time:.2f} seconds" for event_type, avg_time in repo_stats.items()} for repo, repo_stats in stats.items()}
    
    return jsonify(formatted_stats)

@app.route('/check_repos', methods=['GET'])
def check_repos():
    reachable_repos = {}
    headers = {"Authorization": f"token {config.TOKEN}"}
    for repo in config.REPOSITORIES:
        try:
            logging.debug(f"Checking repository: {repo}")
            response = requests.get(f"{config.GITHUB_API_URL}/repos/{repo}", headers=headers)
            response.raise_for_status()
            reachable_repos[repo] = {"accessible": True}
            logging.debug(f"Repository {repo} is accessible")
        except requests.exceptions.RequestException as e:
            reachable_repos[repo] = {"accessible": False, "error": str(e)}
            logging.error(f"Error accessing repository {repo}: {e}")
    return jsonify(reachable_repos)

@app.route('/list_events', methods=['GET'])
def list_events():
    events = Event.query.all()
    return jsonify([{
        'repo': event.repo,
        'event_type': event.event_type,
        'event_time': event.event_time.strftime('%Y-%m-%d %H:%M:%S')
    } for event in events])

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True)
