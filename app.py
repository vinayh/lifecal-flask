import os
import datetime
import requests

from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from werkzeug.exceptions import abort
from urllib.parse import urlencode
from secrets import token_urlsafe
from sqlalchemy import select, update
from datetime import date
from pathlib import Path
from sys import exit

from models import db, User, Entry


SECRETS_TO_PATHS = {
    'FLASK_SECRET_KEY': Path('.secrets/flask_secret_key'),
    'GITHUB_CLIENT_ID': Path('.secrets/github_client_id'),
    'GITHUB_CLIENT_SECRET': Path('.secrets/github_client_secret'),
    'GOOGLE_CLIENT_ID': Path('.secrets/google_client_id'),
    'GOOGLE_CLIENT_SECRET': Path('.secrets/google_client_secret'),
}


def get_secret_file(path) -> str:
    try:
        with path.open("r") as f:
            return f.read()
    except:
        exit(f'Error getting secret {path}')


def get_secret(name: str):
    if os.getenv('LIFECAL_ENV') == 'RENDER':
        return get_secret_file(SECRETS_TO_PATHS[name].relative_to('.secrets'))
    elif os.getenv('LIFECAL_ENV') == 'FLY':
        if name in os.environ:
            return os.getenv(name)
        else:
            raise Exception
    else:
        return get_secret_file(SECRETS_TO_PATHS[name])


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
        'google': {
            'client_id': get_secret('GOOGLE_CLIENT_ID'),
            'client_secret': get_secret('GOOGLE_CLIENT_SECRET'),
            'authorize_url': 'https://accounts.google.com/o/oauth2/auth',
            'token_url': 'https://accounts.google.com/o/oauth2/token',
            'userinfo': {
                'url': 'https://www.googleapis.com/oauth2/v3/userinfo',
                'oauth_id': lambda r: 'go_' + str(r.json()['sub']),
            },
            'scopes': ['https://www.googleapis.com/auth/userinfo.profile'],
        },
    }


def init_db(app: Flask):
    db.init_app(app)
    user_1 = User(oauth_id='test_oauth_id', birth=date.fromisoformat('1995-03-06'), exp_years=80)
    entry_1 = Entry(user_id=1, start=date.fromisoformat('2023-09-04'), category='1',
                    note='Content of entry with category 1')
    entry_2 = Entry(user_id=1, start=date.fromisoformat('2023-09-11'), category='2',
                    note='Content of entry with category 2')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(user_1)
        db.session.commit()
        db.session.add(entry_1)
        db.session.add(entry_2)
        db.session.commit()


app = Flask(__name__)
app.config['SECRET_KEY'] = get_secret('FLASK_SECRET_KEY')
app.config['OAUTH2_PROVIDERS'] = get_oauth2_providers()
if os.getenv('LIFECAL_ENV') != 'FLY':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql' + os.getenv('DATABASE_URL')[8:]
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
login_manager = LoginManager()
login_manager.init_app(app)
init_db(app)


def get_entry(id: str) -> Entry:
    result = db.session.execute(select(Entry).where(Entry.id == id)).fetchone()
    if len(result) == 0 or result[0] is None:
        abort(404)
    return result[0]


# def get_user_parameters(conn) -> tuple[int, str, int]:
#     return conn.execute('SELECT id, birth, exp_years FROM users').fetchone()


@login_manager.user_loader
def get_user(id: str) -> User:
    result = db.session.execute(select(User).where(User.id == id)).fetchone()
    if result is None or len(result) == 0 or result[0] is None:
        abort(404)
    return result[0]


def get_or_add_user(oauth_id: str) -> tuple[User, bool]:
    result = db.session.execute(select(User).where(User.oauth_id == oauth_id)).fetchone()
    if result is None or len(result) == 0 or result[0] is None:
        db.session.add(User(oauth_id=oauth_id, birth=date.fromisoformat('2000-01-01'), exp_years=80))
        db.session.commit()
        result = db.session.execute(select(User).where(User.oauth_id == oauth_id)).fetchone()
        return result[0], True
    else:
        return result[0], False


def generate_all_entries(db_entries: list, birth: date, exp_years: int) -> list:
    db_entries_dict = {x[0].start: x for x in db_entries}
    start = birth - datetime.timedelta(days=birth.weekday())
    if start.month == 2 and start.day == 29:  # If leap day but end year is not leap year
        try:
            end = start.replace(year=start.year + exp_years)
        except ValueError:
            end = start.replace(year=start.year + exp_years, month=3, day=1)
    else:
        end = start.replace(year=start.year + exp_years)
    all_entries = []
    curr = start
    while curr <= end:
        is_past = curr < datetime.datetime.now().date()
        entry = db_entries_dict[curr][0] if curr in db_entries_dict else None
        all_entries.append((curr, is_past, entry))  # adds sqlite3.Row objects if entry exists
        curr += datetime.timedelta(weeks=1)
    return all_entries


@app.route('/')
def index():
    if current_user.is_anonymous:
        return render_template('index_logged_out.html')
    else:
        db_entries = db.session.execute(select(Entry).where(Entry.user_id == current_user.id)).fetchall()
        all_entries = generate_all_entries(db_entries, birth=current_user.birth, exp_years=current_user.exp_years)
        return render_template('index.html', entries=all_entries,
                               birth=current_user.birth, exp_years=current_user.exp_years)


@app.route('/<int:entry_id>')
@login_required
def entry(entry_id):
    entry = get_entry(entry_id)
    if entry.user_id != current_user.id:
        abort(404)
    return render_template('entry.html', entry=entry)


@app.route('/add', methods=('GET', 'POST'))
@login_required
def add():
    if request.method == 'POST':
        start = request.form['start']
        category = request.form['category']
        note = request.form['note']
        start_valid = valid_date(start, only_monday=True, name='Start date')
        if not category:
            flash('Category is required!')
        if start_valid and category:
            db.session.add(Entry(user_id=current_user.id, start=date.fromisoformat(start), category=category, note=note))
            db.session.commit()
            return redirect(url_for('index'))

    return render_template('add.html')


@app.route('/<int:entry_id>/edit', methods=('GET', 'POST'))
@login_required
def edit(entry_id: int):
    entry = get_entry(entry_id)
    if entry.user_id != current_user.id:
        abort(404)
    if request.method == 'POST':
        start = request.form['start']
        category = request.form['category']
        note = request.form['note']
        start_valid = valid_date(start, only_monday=True, name='Start date')
        if not category:
            flash('Category is required!')
        if start_valid and category:
            db.session.execute(update(Entry).where(Entry.id == entry_id).values(start=date.fromisoformat(start), category=category, note=note))
            db.session.commit()
            return redirect(url_for('index'))

    return render_template('edit.html', entry=entry)


@app.route('/<int:entry_id>/delete', methods=('POST',))
@login_required
def delete(entry_id):
    entry = get_entry(entry_id)
    if entry.user_id != current_user.id:
        abort(404)
    entry_start = entry.start
    db.session.delete(entry)
    db.session.commit()
    flash(f'Entry starting on {entry_start} was successfully deleted!')
    return redirect(url_for('index'))


@app.route('/delete_user/<int:user_id>', methods=('POST',))
@login_required
def delete_user(user_id: int):
    if user_id != current_user.id:
        abort(404)
    Entry.query.filter(Entry.user_id == user_id).delete()
    # db.session.execute(Entry.delete().where(Entry.user_id == user_id))
    User.query.filter(User.id == user_id).delete()
    # db.session.execute(User.delete().where(User.id == user_id))
    db.session.commit()
    flash(f'Account and all associated entries were successfully deleted!')
    logout_user()
    return redirect(url_for('index'))


def valid_date(date: str, only_monday=False, name='Date') -> bool:
    if not date:
        flash(f'{name} is required!')
        return False
    try:
        date = datetime.datetime.fromisoformat(date)
        if only_monday and date.weekday() != 0:
            flash(f'{name} must be a Monday (start of week)')
            return False
        else:
            return True
    except:
        flash(f'{name} is required to be in YYYY-MM-DD format')
        return False


def valid_exp_years(exp_years: str) -> bool:
    if not exp_years:
        flash('Life expectancy is required!')
        return False
    if not exp_years.isdigit():
        flash('Life expectancy is required to be a non-negative integer value')
        return False
    return True


@app.route('/settings', methods=('GET', 'POST'))
@login_required
def settings():
    if request.method == 'POST':
        birth = request.form['birth']
        exp_years = request.form['exp_years']
        valid_birth, valid_years = valid_date(birth, name='Date of birth'), valid_exp_years(exp_years)
        if valid_birth and valid_years:
            user = db.session.execute(select(User).where(User.id == current_user.id)).fetchone()[0]
            user.birth = date.fromisoformat(birth)
            user.exp_years = exp_years
            db.session.commit()
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
    flash('Successfully signed out!')
    return redirect(url_for('index'))


@app.route('/authorize/<provider>')
def oauth2_authorize(provider):
    if current_user.is_authenticated:
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
    if current_user.is_authenticated:
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
    user, is_new_user = get_or_add_user(oauth_id)
    login_user(user)
    if is_new_user:
        flash('Welcome to your new account. Please set your date of birth and life expectancy here.')
        return redirect(url_for('settings'))
    else:
        flash('You have been signed in. Welcome back!')
        return redirect(url_for('index'))


if __name__ == '__main__':
    app.run()
