import datetime
import os
from datetime import date
from secrets import token_urlsafe
from urllib.parse import urlencode

import requests
from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from sqlalchemy import select
from werkzeug.exceptions import abort

from config import get_secret, get_oauth2_providers
from models import db, init_db, User, Entry, Tag

app = Flask(__name__)
app.config['SECRET_KEY'] = get_secret('FLASK_SECRET_KEY')
app.config['OAUTH2_PROVIDERS'] = get_oauth2_providers()
app.config['SQLALCHEMY_DATABASE_URI'] = get_secret('DATABASE_URL')
if app.config['SQLALCHEMY_DATABASE_URI'][:11] == 'postgres://':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://' + app.config['SQLALCHEMY_DATABASE_URI'][11:]
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
login_manager = LoginManager()
login_manager.init_app(app)
db.init_app(app)
if os.getenv('INIT_DB') is not None:
    init_db(app)


def get_entry(id: str) -> Entry:
    result = db.session.execute(select(Entry).where(Entry.id == id)).fetchone()
    if result is None or len(result) == 0 or result[0] is None or result[0].user_id != current_user.id:
        abort(404)
    return result[0]


def get_tag(id: str) -> Tag:
    result = db.session.execute(select(Tag).where(Tag.id == id)).fetchone()
    if result is None or len(result) == 0 or result[0] is None or result[0].user_id != current_user.id:
        abort(404)
    return result[0]


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
    db_entries_dict = {x.start: x for x in db_entries}
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
        entry = db_entries_dict[curr] if curr in db_entries_dict else None
        all_entries.append((curr, is_past, entry))  # adds sqlite3.Row objects if entry exists
        curr += datetime.timedelta(weeks=1)
    return all_entries


@app.route('/')
def index():
    if current_user.is_anonymous:
        return render_template('index_logged_out.html')
    else:
        # db_entries = db.session.execute(select(Entry).where(Entry.user_id == current_user.id)).fetchall()
        all_entries = generate_all_entries(db_entries=current_user.entries, birth=current_user.birth,
                                           exp_years=current_user.exp_years)
        return render_template('index.html', entries=all_entries,
                               birth=current_user.birth, exp_years=current_user.exp_years)


@app.route('/entry/<int:entry_id>')
@login_required
def entry(entry_id):
    return render_template('entry.html', entry=get_entry(entry_id))


@app.route('/entry/add', methods=('GET', 'POST'))
@login_required
def add_entry():
    if request.method == 'POST':
        start = request.form['start']
        tag_ids = request.form.getlist('tags')
        note = request.form['note']
        start_valid = valid_date(start, only_monday=True, name='Start date')
        tags, tags_valid = valid_entry_tags(tag_ids)  # Checks for >= 1 tags that match current_user
        if start_valid and tags_valid:
            db.session.add(
                Entry(user_id=current_user.id, start=date.fromisoformat(start), tags=tags, note=note))
            db.session.commit()
            return redirect(url_for('index'))
    return render_template('add.html', tags=current_user.tags)


@app.route('/entry/<int:entry_id>/edit', methods=('GET', 'POST'))
@login_required
def edit_entry(entry_id: int):
    entry = get_entry(entry_id)
    if request.method == 'POST':
        start = request.form['start']
        tag_ids = request.form.getlist('tags')
        note = request.form['note']
        start_valid = valid_date(start, only_monday=True, name='Start date')
        tags, tags_valid = valid_entry_tags(tag_ids)  # Checks for >= 1 tags that match current_user
        if start_valid and tags_valid:
            entry.start = date.fromisoformat(start)
            entry.tags = tags
            entry.note = note
            db.session.commit()
            return redirect(url_for('index'))
    return render_template('edit.html', entry=entry, tags=current_user.tags)


@app.route('/entry/<int:entry_id>/delete', methods=('POST',))
@login_required
def delete_entry(entry_id):
    entry = get_entry(entry_id)
    entry_start = entry.start
    db.session.delete_entry(entry)
    db.session.commit()
    flash(f'Entry starting on {entry_start} was successfully deleted!')
    return redirect(url_for('index'))


@app.route('/user/<int:user_id>/delete', methods=('POST',))
@login_required
def delete_user(user_id: int):
    if user_id != current_user.id:
        abort(404)
    Entry.query.filter(Entry.user_id == user_id).delete_entry()
    User.query.filter(User.id == user_id).delete_entry()
    db.session.commit()
    logout_user()
    flash(f'Account and all associated entries were successfully deleted!')
    return redirect(url_for('index'))


def valid_tag(name, color) -> bool:
    valid = True
    if request.form['name'] is None:
        flash('Tag name is required!')
        valid = False
    if request.form['color'] is None:
        flash('Color choice is required!')
        valid = False
    return valid


@app.route('/tags')
@login_required
def tags():
    return render_template('tags.html', tags=sorted(current_user.tags, key=lambda t: t.created))


@app.route('/tag/add', methods=('POST',))
@login_required
def add_tag():
    if valid_tag(request.form['name'], request.form['color']):
        db.session.add(Tag(user_id=current_user.id, name=request.form['name'], color=request.form['color']))
        db.session.commit()
    return redirect(url_for('tags'))


@app.route('/tag/<int:tag_id>/edit', methods=('POST',))
@login_required
def edit_tag(tag_id: int):
    tag = get_tag(tag_id)
    if valid_tag(request.form['name'], request.form['color']):
        tag.name = request.form['name']
        tag.color = request.form['color']
        db.session.commit()
    return redirect(url_for('tags'))


@app.route('/tag/<int:tag_id>/delete', methods=('POST',))
@login_required
def delete_tag(tag_id):
    tag = get_tag(tag_id)
    tag_name = tag.name
    db.session.delete(tag)
    db.session.commit()
    flash(f'Tag {tag_name} was successfully deleted!')
    return redirect(url_for('tags'))


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


def valid_entry_tags(tags: list) -> tuple[list[Tag], bool]:
    if len(tags) == 0:
        flash('At least one tag must be selected!')
        return [], False
    tags_db = [get_tag(t) for t in tags]
    for t in tags_db:
        if t.user_id != current_user.id:
            flash('Invalid tag choice!')
            return [], False
    return tags_db, True


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
