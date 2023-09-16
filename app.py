import sqlite3
import sys
from pathlib import Path
from flask import Flask, render_template, request, url_for, flash, redirect
from werkzeug.exceptions import abort


def get_secret_key():
    FLASK_SECRET_PATH = Path(".flask_secret")
    try:
        with FLASK_SECRET_PATH.open("r") as flask_secret_file:
            return flask_secret_file.read()
    except:
        sys.exit()


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


app = Flask(__name__)
app.config['SECRET_KEY'] = get_secret_key()


@app.route('/')
def index():
    conn = get_db_connection()
    entries = conn.execute('SELECT * FROM entries').fetchall()
    conn.close()
    return render_template('index.html', entries=entries)


@app.route('/<int:entry_id>')
def entry(entry_id):
    entry = get_entry(entry_id)
    return render_template('entry.html', entry=entry)


@app.route('/add', methods=('GET', 'POST'))
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
            conn.execute('INSERT INTO entries (start, category, note) VALUES (?, ?, ?)',
                         (start, category, note))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('add.html')


@app.route('/<int:entry_id>/edit', methods=('GET', 'POST'))
def edit(entry_id):
    entry = get_entry(entry_id)
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
def delete(entry_id):
    entry = get_entry(entry_id)
    conn = get_db_connection()
    conn.execute('DELETE FROM entries WHERE id = ?', (entry_id,))
    conn.commit()
    conn.close()
    flash(f'Entry starting on {entry["start"]} was successfully deleted!')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run()
