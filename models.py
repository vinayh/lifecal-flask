from datetime import date
from typing import List

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum, ForeignKey
from sqlalchemy.sql import func

from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship

db = SQLAlchemy()

entry_tag = db.Table('entry_tag',
                     db.Column('entry_id', db.Integer, db.ForeignKey('entries.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True),
                     db.Column('tag_id', db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True))
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    oauth_id = db.Column(db.String(100), nullable=False)
    birth = db.Column(db.Date, nullable=False)
    exp_years = db.Column(db.Integer, nullable=False)
    tags: Mapped[List["Tag"]] = relationship(back_populates="user")
    entries: Mapped[List["Entry"]] = relationship(back_populates="user")
    email = db.Column(db.String(100), nullable=True)


class Entry(db.Model):
    __tablename__ = 'entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user: Mapped["User"] = relationship(back_populates="entries")
    tags: Mapped[List["Tag"]] = relationship(secondary=entry_tag, back_populates="entries")
    start = db.Column(db.Date, nullable=False)
    # tag = db.Column(db.Integer, db.ForeignKey('tags.id'), nullable=False)
    note = db.Column(db.String, nullable=True)  # Optional


class Tag(db.Model):
    __tablename__ = 'tags'
    id: Mapped[int] = mapped_column(primary_key=True)
    created = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="tags")
    entries: Mapped[List["Entry"]] = relationship(secondary=entry_tag, back_populates="tags")
    name = db.Column(db.String, nullable=False)
    color = db.Column(db.String, nullable=False)
    type = db.Column(Enum('entry', 'goal', name='tag_types'), nullable=True)  #  TODO: Optional for now
    category = db.Column(db.Integer, nullable=True)  # Optional, to use for showing/hiding layers of tags


def init_db(app):
    print('Wiping database and initializing new data!')
    user_1 = User(oauth_id='test_oauth_id', birth=date.fromisoformat('1995-03-06'), exp_years=80)
    tag_1 = Tag(user_id=1, name='Tag 1', color='Color 1')
    tag_2 = Tag(user_id=1, name='Tag 2', color='Color 2')
    entry_1 = Entry(user_id=1, start=date.fromisoformat('2023-09-04'), tags=[tag_1],  # TODO: fix these entries to create and use tags
                    note='Content of entry with tag 1')
    entry_2 = Entry(user_id=1, start=date.fromisoformat('2023-09-11'), tags=[tag_1, tag_2],
                    note='Content of entry with tag 2')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(user_1)
        # db.session.commit()
        db.session.add(tag_1)
        db.session.add(tag_2)
        # db.session.commit()
        db.session.add(entry_1)
        db.session.add(entry_2)
        db.session.commit()