from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'profile_user'          # <-- prefixed table name
    id = db.Column(db.Integer, primary_key=True)
    profile_image = db.Column(db.String(200), nullable=True)  # filename of profile picture
    documents = db.relationship('Document', backref='owner', lazy=True, cascade='all, delete-orphan')

class Document(db.Model):
    __tablename__ = 'profile_document'       # <-- prefixed table name
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)       # original name
    stored_name = db.Column(db.String(200), nullable=False, unique=True)  # unique name on disk
    file_type = db.Column(db.String(50), nullable=False)       # 'cv', 'transcript', 'qualification', 'other'
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('profile_user.id'), nullable=False)  # foreign key must match the table name

    def __repr__(self):
        return f'<Document {self.filename}>'