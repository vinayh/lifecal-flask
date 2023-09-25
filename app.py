import datetime
import json
import os
from datetime import date
from secrets import token_urlsafe
from typing import Optional
from urllib.parse import urlencode

import requests
from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_login import (
    LoginManager,
    current_user,
    login_user,
    logout_user,
    login_required,
)
from sqlalchemy import select
from werkzeug.exceptions import abort

from config import get_secret, get_oauth2_providers
from models import db, init_db, User, Entry, Tag

app = Flask(__name__)
app.config["SECRET_KEY"] = get_secret("FLASK_SECRET_KEY")
app.config["OAUTH2_PROVIDERS"] = get_oauth2_providers()
app.config["SQLALCHEMY_DATABASE_URI"] = get_secret("DATABASE_URL")
if app.config["SQLALCHEMY_DATABASE_URI"][:11] == "postgres://":
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "postgresql://" + app.config["SQLALCHEMY_DATABASE_URI"][11:]
    )
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
login_manager = LoginManager()
login_manager.init_app(app)
db.init_app(app)
if os.getenv("INIT_DB") is not None:
    init_db(app)


def get_by_id_helper(model: db.Model, id: str, check_user=True) -> db.Model:
    result = db.session.execute(select(model).where(model.id == id)).fetchone()
    if (
        result is None
        or len(result) == 0
        or result[0] is None
        or (check_user and result[0].user_id != current_user.id)
    ):
        abort(404)
    return result[0]


def get_entry_by_id(id: str) -> Entry:
    return get_by_id_helper(Entry, id)


def get_tag_by_id(id: str) -> Tag:
    return get_by_id_helper(Tag, id)


@login_manager.user_loader
def get_user_by_id(id: str) -> User:
    return get_by_id_helper(User, id, check_user=False)


def get_create_user_by_oauth_id(oauth_id: str) -> tuple[User, bool]:
    result = db.session.execute(
        select(User).where(User.oauth_id == oauth_id)
    ).fetchone()
    if result is None or len(result) == 0 or result[0] is None:
        db.session.add(
            User(
                oauth_id=oauth_id, birth=date.fromisoformat("2000-01-01"), exp_years=80
            )
        )
        db.session.commit()
        result = db.session.execute(
            select(User).where(User.oauth_id == oauth_id)
        ).fetchone()
        return result[0], True
    else:
        return result[0], False


def generate_all_entries(
    db_entries: list[Entry], birth: date, exp_years: int
) -> list[tuple[date, bool, Optional[Entry]]]:
    db_entries_dict = {x.start: x for x in db_entries}
    start = birth - datetime.timedelta(days=birth.weekday())
    if (
        start.month == 2 and start.day == 29
    ):  # If leap day but end year is not leap year
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
        all_entries.append(
            (curr, is_past, entry)
        )  # adds sqlite3.Row objects if entry exists
        curr += datetime.timedelta(weeks=1)
    return all_entries


@app.route("/")
def index() -> str:
    if current_user.is_anonymous:
        return render_template("index_logged_out.html")
    else:
        all_entries = generate_all_entries(
            db_entries=current_user.entries,
            birth=current_user.birth,
            exp_years=current_user.exp_years,
        )
        return render_template(
            "index.html",
            entries=all_entries,
            birth_readable=current_user.birth.strftime("%d %B, %Y"),
            exp_years=current_user.exp_years,
        )


@app.route("/entry/<int:entry_id>")
@login_required
def entry(entry_id: str) -> str:
    return render_template("entry.html", entry=get_entry_by_id(entry_id))


def entry_helper(edit: bool, entry: Optional[Entry] = None):
    if request.method == "POST":
        start = request.form["start"]
        tag_names = request.form.getlist("tags[]")
        note = request.form["note"]
        if len(tag_names) == 0:
            flash("At least one tag must be selected!", category="danger")
            tags = None
        else:
            tags = get_add_tags(
                tag_names
            )  # Gets tags by name or adds new tags if not existing
        start_valid = valid_date(start, only_monday=True, name="Start date")
        if start_valid and tags:
            if not edit:  # Check if adding an entry with a date that already exists
                result = db.session.execute(
                    select(Entry).where(
                        (Entry.user_id == current_user.id) & (Entry.start == start)
                    )
                ).fetchone()
                if result is not None and len(result) > 0:  # Entry with date exists
                    entry = result[0]
                    edit = True
                    flash(
                        f"Entry with specified date already exists. Edited existing entry for {start}!",
                        category="warning",
                    )
            if edit:
                entry.start = date.fromisoformat(start)
                entry.tags = tags
                entry.note = note
                flash(f"Successfully edited entry for {start}", category="success")
            else:  # Add new entry
                db.session.add(
                    Entry(
                        user_id=current_user.id,
                        start=date.fromisoformat(start),
                        tags=tags,
                        note=note,
                    )
                )
                flash(f"Successfully added entry for {start}", category="success")
            db.session.commit()
            return redirect(url_for("index"))
    if edit:
        existing_entry_dates = json.dumps(
            [
                x.start.isoformat()
                for x in current_user.entries
                if x.start != entry.start
            ]
        )
        return render_template(
            "edit.html",
            tags=current_user.tags,
            disabled_dates=existing_entry_dates,
            entry=entry,
        )
    else:  # Add new entry
        existing_entry_dates = json.dumps(
            [x.start.isoformat() for x in current_user.entries]
        )
        date_today = datetime.datetime.now().date()
        return render_template(
            "add.html",
            tags=current_user.tags,
            disabled_dates=existing_entry_dates,
            default_date=date_today - datetime.timedelta(days=date_today.weekday()),
        )


@app.route("/entry/add", methods=("GET", "POST"))
@login_required
def add_entry():
    return entry_helper(edit=False)


@app.route("/entry/<int:entry_id>/edit", methods=("GET", "POST"))
@login_required
def edit_entry(entry_id: str):
    return entry_helper(edit=True, entry=get_entry_by_id(entry_id))


@app.route("/entry/<int:entry_id>/delete", methods=("POST",))
@login_required
def delete_entry(entry_id: str):
    entry = get_entry_by_id(entry_id)
    entry_start = entry.start
    db.session.delete(entry)
    db.session.commit()
    flash(
        f"Entry starting on {entry_start} was successfully deleted!", category="success"
    )
    return redirect(url_for("index"))


@app.route("/user/<int:user_id>/delete", methods=("POST",))
@login_required
def delete_user(user_id: str):
    if user_id != current_user.id:
        abort(404)
    User.query.filter(User.id == user_id).delete()
    db.session.commit()
    logout_user()
    flash(
        f"Account and all associated entries were successfully deleted!",
        category="success",
    )
    return redirect(url_for("index"))


def valid_tag_name_color(name: str, color: str) -> bool:
    valid = True
    if name is None:
        flash("Tag name is required!", category="danger")
        valid = False
    if color is None:
        flash("Color choice is required!", category="danger")
        valid = False
    return valid


@app.route("/tags")
@login_required
def tags() -> str:
    return render_template(
        "tags.html", tags=sorted(current_user.tags, key=lambda t: t.created)
    )


def add_tag_helper(name: str, color: str = "0000FFFF", return_tag=False):
    valid = valid_tag_name_color(name, color)
    if (
        db.session.execute(
            select(Tag.id).where((Tag.name == name) & (Tag.user_id == current_user.id))
        ).fetchone()
        is not None
    ):
        flash(
            f"Existing tag with name {name} already exists; cannot add duplicate tag!",
            category="danger",
        )
        valid = False
    if valid:
        new_tag = Tag(
            user_id=current_user.id,
            name=name,
            color=color,
        )
        db.session.add(new_tag)
        db.session.commit()
        flash(f"Added tag f{name}!", category="success")
        if return_tag:
            db.session.refresh(new_tag)
            return new_tag


@app.route("/tag/add", methods=("POST",))
@login_required
def add_tag():
    add_tag_helper(request.form["name"], request.form["color"], return_tag=False)
    return redirect(url_for("tags"))


@app.route("/tag/<int:tag_id>/edit", methods=("POST",))
@login_required
def edit_tag(tag_id: str):
    tag = get_tag_by_id(tag_id)
    valid = valid_tag_name_color(request.form["name"], request.form["color"])
    if (
        db.session.execute(
            select(Tag.id).where(
                (Tag.name == request.form["name"])
                & (Tag.user_id == current_user.id)
                & (Tag.id != tag.id)
            )
        ).fetchone()
        is not None
    ):
        flash(
            f"Existing tag with name {request.form['name']} already exists; cannot edit tag!",
            category="danger",
        )
        valid = False
    if valid:
        tag.name = request.form["name"]
        tag.color = request.form["color"]
        db.session.commit()
    return redirect(url_for("tags"))


@app.route("/tag/<int:tag_id>/delete", methods=("POST",))
@login_required
def delete_tag(tag_id: str):
    tag = get_tag_by_id(tag_id)
    tag_name = tag.name
    db.session.delete(tag)
    db.session.commit()
    flash(f"Tag {tag_name} was successfully deleted!", category="success")
    return redirect(url_for("tags"))


def valid_date(date: str, only_monday=False, name="Date") -> bool:
    if not date:
        flash(f"{name} is required!", category="danger")
        return False
    try:
        date = datetime.datetime.fromisoformat(date)
        if only_monday and date.weekday() != 0:
            flash(f"{name} must be a Monday (start of week)", category="danger")
            return False
        else:
            return True
    except:
        flash(f"{name} is required to be in YYYY-MM-DD format", category="danger")
        return False


def get_add_tags(tag_names: list[str]) -> list[Tag]:
    tags_db = []
    for t in tag_names:
        result = db.session.execute(
            select(Tag).where((Tag.name == t) & (Tag.user_id == current_user.id))
        ).fetchone()
        if result is not None:
            tags_db.append(result[0])
        else:
            tags_db.append(add_tag_helper(t, return_tag=True))
    return tags_db


def valid_exp_years(exp_years: str) -> bool:
    if not exp_years:
        flash("Life expectancy is required!", category="danger")
        return False
    if not exp_years.isdigit():
        flash(
            "Life expectancy is required to be a non-negative integer value",
            category="danger",
        )
        return False
    return True


@app.route("/settings", methods=("GET", "POST"))
@login_required
def settings():
    if request.method == "POST":
        birth = request.form["birth"]
        exp_years = request.form["exp_years"]
        valid_birth, valid_years = valid_date(
            birth, name="Date of birth"
        ), valid_exp_years(exp_years)
        if valid_birth and valid_years:
            user = db.session.execute(
                select(User).where(User.id == current_user.id)
            ).fetchone()[0]
            user.birth = date.fromisoformat(birth)
            user.exp_years = exp_years
            db.session.commit()
            flash("Settings were successfully updated!", category="success")
            return redirect(url_for("settings"))
    return render_template(
        "settings.html", birth=current_user.birth, exp_years=current_user.exp_years
    )


@app.route("/login")
def login() -> str:
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Successfully signed out!", category="success")
    return redirect(url_for("index"))


@app.route("/authorize/<provider>")
def oauth2_authorize(provider):
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if provider not in app.config["OAUTH2_PROVIDERS"]:
        abort(404)
    else:
        provider_info = app.config["OAUTH2_PROVIDERS"][provider]
    session["oauth2_state"] = token_urlsafe(16)
    query = urlencode(
        {
            "client_id": provider_info["client_id"],
            "redirect_uri": url_for(
                "oauth2_callback", provider=provider, _external=True
            ),
            "response_type": "code",
            "scope": " ".join(provider_info["scopes"]),
            "state": session["oauth2_state"],
        }
    )
    return redirect(provider_info["authorize_url"] + "?" + query)


@app.route("/callback/<provider>")
def oauth2_callback(provider):
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if provider not in app.config["OAUTH2_PROVIDERS"]:
        abort(404)
    else:
        provider_info = app.config["OAUTH2_PROVIDERS"][provider]
    if "error" in request.args:
        flash(request.args.items(), category="danger")
        return redirect(url_for("index"))
    if request.args["state"] != session.get("oauth2_state"):
        abort(401)
    if "code" not in request.args:
        abort(401)
    response = requests.post(
        provider_info["token_url"],
        data={
            "client_id": provider_info["client_id"],
            "client_secret": provider_info["client_secret"],
            "code": request.args["code"],
            "grant_type": "authorization_code",
            "redirect_uri": url_for(
                "oauth2_callback", provider=provider, _external=True
            ),
        },
        headers={"Accept": "application/json"},
    )
    if response.status_code != 200:
        abort(401)
    oauth2_token = response.json()["access_token"]
    if not oauth2_token:
        abort(401)
    response = requests.get(
        provider_info["userinfo"]["url"],
        headers={
            "Authorization": "Bearer " + oauth2_token,
            "Accept": "application/json",
        },
    )
    if response.status_code != 200:
        abort(401)
    # Get or add user
    oauth_id = provider_info["userinfo"]["oauth_id"](response)
    user, is_new_user = get_create_user_by_oauth_id(oauth_id)
    login_user(user)
    if is_new_user:
        flash(
            "Welcome to your new account. Please set your date of birth and life expectancy here.",
            category="primary",
        )
        return redirect(url_for("settings"))
    else:
        flash("You have been signed in. Welcome back!", category="success")
        return redirect(url_for("index"))


if __name__ == "__main__":
    app.run()
