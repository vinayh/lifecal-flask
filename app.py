import sqlite3
import datetime
import requests

from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_login import LoginManager, current_user, login_user, logout_user, login_required, UserMixin
from werkzeug.exceptions import abort
from urllib.parse import urlencode
from secrets import token_urlsafe
from typing import Optional
from pathlib import Path
from sys import exit


class User(UserMixin):
    def __init__(self, id: int, oauth_id: str, birth: str, exp_years: int, email: str = None):
        super().__init__()
        self.id = id
        self.oauth_id = oauth_id
        self.birth = birth
        self.exp_years = exp_years
        self.email = email


SECRETS_TO_PATHS = {
    'FLASK_SECRET_KEY': Path('.secrets/flask_secret_key'),
    'GITHUB_CLIENT_ID': Path('.secrets/github_client_id'),
    'GITHUB_CLIENT_SECRET': Path('.secrets/github_client_secret')
}


def get_secret(name: str):
    try:
        path = SECRETS_TO_PATHS[name]
        with path.open("r") as f:
            return f.read()
    except:
        exit()


def get_oauth2_providers():
    return {
        'github': {
            'client_id': get_secret('GITHUB_CLIENT_ID'),
            'client_secret': get_secret('GITHUB_CLIENT_SECRET'),
            'authorize_url': 'https://github.com/login/oauth/authorize',
            'token_url': 'https://github.com/login/oauth/access_token',
            'userinfo': {
                'url': 'https://api.github.com/user',
                'oauth_id': lambda r: 'gh_' + str(r.json()['id']),
            },
            'scopes': ['read:user'],
        },
    }


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


def get_entry(entry_id: int):
    conn = get_db_connection()
    entry = conn.execute('SELECT * FROM entries WHERE id = ?', (entry_id,)).fetchone()
    conn.close()
    if entry is None:
        abort(404)
    return entry


def get_user_parameters(conn) -> tuple[int, str, int]:
    return conn.execute('SELECT id, birth, exp_years FROM users').fetchone()


def get_or_add_user(oauth_id: str) -> Optional[User]:
    conn = get_db_connection()
    response = conn.execute('SELECT id, birth, exp_years FROM users WHERE oauth_id = ?', (oauth_id,)).fetchone()
    if response is None:
        conn.execute('INSERT INTO users (oauth_id, birth, exp_years) VALUES (?, ?, ?)', (oauth_id, '2000-01-01', 80))
        conn.commit()
        id, birth, exp_years = conn.execute('SELECT id, birth, exp_years FROM users WHERE oauth_id = ?',
                                            (oauth_id,)).fetchone()
    else:
        id, birth, exp_years = response
    conn.close()
    return User(id=id, oauth_id=oauth_id, birth=birth, exp_years=exp_years)


def generate_all_entries(db_entries: list, birth: str, exp_years: int) -> list:
    db_entries_dict = {}
    for x in db_entries:
        x_start_date = datetime.datetime.strptime(x['start'], '%Y-%m-%d')
        db_entries_dict[x_start_date] = x
    start_exact = datetime.datetime.strptime(birth, '%Y-%m-%d')
    start = start_exact - datetime.timedelta(days=start_exact.weekday())
    if start.month == 2 and start.day == 29:
        end = start.replace(year=start.year + exp_years, month=3, day=1)
    else:
        end = start.replace(year=start.year + exp_years)
    curr = start
    all_entries = []
    while curr <= end:
        past = curr < datetime.datetime.now()
        if curr in db_entries_dict:
            all_entries.append((db_entries_dict[curr], past))  # adds sqlite3.Row objects, not dicts as in 'else'
        else:
            all_entries.append(({'start': curr.strftime('%Y-%m-%d')}, past))
        curr += datetime.timedelta(weeks=1)
    return all_entries


app = Flask(__name__)
app.config['SECRET_KEY'] = get_secret('FLASK_SECRET_KEY')
app.config['OAUTH2_PROVIDERS'] = get_oauth2_providers()
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(id: str) -> User:
    conn = get_db_connection()
    response = conn.execute('SELECT id, oauth_id, email, birth, exp_years FROM users WHERE id = ?', (id,)).fetchone()
    conn.close()
    if response is not None:
        id, oauth_id, email, birth, exp_years = response
        return User(id=id, oauth_id=oauth_id, email=email, birth=birth, exp_years=exp_years)
    else:
        abort(401)


@app.route('/')
def index():
    if current_user.is_anonymous:
        return render_template('index_logged_out.html')
    else:
        conn = get_db_connection()
        db_entries = conn.execute('SELECT * FROM entries').fetchall()
        all_entries = generate_all_entries(db_entries, birth=current_user.birth, exp_years=current_user.exp_years)
        conn.close()
        return render_template('index.html', entries=all_entries,
                               birth=current_user.birth, exp_years=current_user.exp_years)


@app.route('/<int:entry_id>')
@login_required
def entry(entry_id):
    entry = get_entry(entry_id)
    if entry['user_id'] != current_user.id:
        abort(404)
    return render_template('entry.html', entry=entry)


@app.route('/add', methods=('GET', 'POST'))
@login_required
def add():
    if request.method == 'POST':
        start = request.form['start']
        category = request.form['category']
        note = request.form['note']
        if not start:
            flash('Start date is required!')
        if not category:
            flash('Category is required!')
        if start and category:
            conn = get_db_connection()
            conn.execute('INSERT INTO entries (user_id, start, category, note) VALUES (?, ?, ?, ?)',
                         (current_user.id, start, category, note))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('add.html')


@app.route('/<int:entry_id>/edit', methods=('GET', 'POST'))
@login_required
def edit(entry_id: int):
    entry = get_entry(entry_id)
    print(entry['user_id'], current_user.id)
    if entry['user_id'] != current_user.id:
        abort(404)
    if request.method == 'POST':
        start = request.form['start']
        category = request.form['category']
        note = request.form['note']
        if not start:
            flash('Start date is required!')
        if not category:
            flash('Category is required!')
        if start and category:
            conn = get_db_connection()
            conn.execute('UPDATE entries SET start = ?, category = ?, note = ? WHERE id = ?',
                         (start, category, note, entry_id))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('edit.html', entry=entry)


@app.route('/<int:entry_id>/delete', methods=('POST',))
@login_required
def delete(entry_id):
    entry = get_entry(entry_id)
    if entry['user_id'] != current_user.id:
        abort(404)
    conn = get_db_connection()
    conn.execute('DELETE FROM entries WHERE id = ?', (entry_id,))
    conn.commit()
    conn.close()
    flash(f'Entry starting on {entry["start"]} was successfully deleted!')
    return redirect(url_for('index'))


@app.route('/settings', methods=('GET', 'POST'))
@login_required
def settings():
    conn = get_db_connection()
    if request.method == 'POST':
        birth = request.form['birth']
        exp_years = request.form['exp_years']
        if not birth:
            flash('Date of birth is required!')
        if not exp_years:
            flash('Life expectancy is required!')
        if birth and exp_years:
            conn = get_db_connection()
            conn.execute('UPDATE users SET birth = ?, exp_years = ? WHERE id = ?',
                         (birth, exp_years, current_user.id))
            conn.commit()
            conn.close()
            flash('Settings were successfully updated!')
            return redirect(url_for('settings'))

    return render_template('settings.html', birth=current_user.birth, exp_years=current_user.exp_years)


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Successfully logged out!')
    return redirect(url_for('index'))


@app.route('/authorize/<provider>')
def oauth2_authorize(provider):
    if not current_user.is_anonymous:
        return redirect(url_for('index'))
    if provider not in app.config['OAUTH2_PROVIDERS']:
        abort(404)
    else:
        provider_info = app.config['OAUTH2_PROVIDERS'][provider]
    session['oauth2_state'] = token_urlsafe(16)
    query = urlencode({
        'client_id': provider_info['client_id'],
        'redirect_uri': url_for('oauth2_callback', provider=provider, _external=True),
        'response_type': 'code',
        'scope': ' '.join(provider_info['scopes']),
        'state': session['oauth2_state'],
    })
    return redirect(provider_info['authorize_url'] + '?' + query)


@app.route('/callback/<provider>')
def oauth2_callback(provider):
    if not current_user.is_anonymous:
        return redirect(url_for('index'))
    if provider not in app.config['OAUTH2_PROVIDERS']:
        abort(404)
    else:
        provider_info = app.config['OAUTH2_PROVIDERS'][provider]
    if 'error' in request.args:
        flash(request.args.items())
        return redirect(url_for('index'))
    if request.args['state'] != session.get('oauth2_state'):
        abort(401)
    if 'code' not in request.args:
        abort(401)
    response = requests.post(provider_info['token_url'], data={
        'client_id': provider_info['client_id'],
        'client_secret': provider_info['client_secret'],
        'code': request.args['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': url_for('oauth2_callback', provider=provider, _external=True),
    }, headers={'Accept': 'application/json'})
    if response.status_code != 200:
        abort(401)
    oauth2_token = response.json()['access_token']
    if not oauth2_token:
        abort(401)
    response = requests.get(provider_info['userinfo']['url'], headers={
        'Authorization': 'Bearer ' + oauth2_token,
        'Accept': 'application/json',
    })
    if response.status_code != 200:
        abort(401)
    # Get or add user
    oauth_id = provider_info['userinfo']['oauth_id'](response)
    user = get_or_add_user(oauth_id)
    login_user(user)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run()
