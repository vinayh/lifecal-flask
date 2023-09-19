from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.sql import func

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    oauth_id = db.Column(db.String(100), nullable=False)
    birth = db.Column(db.Date, nullable=False)
    exp_years = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(100), nullable=True)

class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    start = db.Column(db.Date, nullable=False)
    category = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String, nullable=True)