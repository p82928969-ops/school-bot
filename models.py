from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(128), default="")

    mode = db.Column(db.String(16), default="student")  # student/parent/teacher

    teacher_code = db.Column(db.String(8), unique=True)
    student_code = db.Column(db.String(8), unique=True)

    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship("School", foreign_keys=[school_id], backref="members")
    user_class = db.relationship("Class", foreign_keys=[class_id])

    def set_password(self, pwd: str):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd: str) -> bool:
        return check_password_hash(self.password_hash, pwd)

    def is_director(self) -> bool:
        return School.query.filter_by(director_id=self.id).first() is not None


class School(db.Model):
    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(8), unique=True, nullable=False)
    director_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    director = db.relationship("User", foreign_keys=[director_id])
    classes = db.relationship("Class", backref="school", cascade="all, delete-orphan")


class Class(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)

    __table_args__ = (db.UniqueConstraint("school_id", "name"),)


class TeacherStudent(db.Model):
    __tablename__ = "teacher_students"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    __table_args__ = (db.UniqueConstraint("teacher_id", "student_id"),)


class StudentParent(db.Model):
    __tablename__ = "student_parents"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    __table_args__ = (db.UniqueConstraint("student_id", "parent_id"),)


class Schedule(db.Model):
    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "day"),)


class Homework(db.Model):
    __tablename__ = "homework"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    subject = db.Column(db.String(64), nullable=False)
    text = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class_ = db.relationship("Class")
    author = db.relationship("User")


class Grade(db.Model):
    __tablename__ = "grades"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject = db.Column(db.String(64), nullable=False)
    value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Reminder(db.Model):
    __tablename__ = "reminders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    when = db.Column(db.DateTime, nullable=False)
    notified = db.Column(db.Boolean, default=False)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # user/assistant
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
