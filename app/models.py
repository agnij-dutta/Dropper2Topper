from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    if (user_id.startswith('admin_')):
        return Admin.query.get(int(user_id[5:]))
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(100), nullable=False)
    qualification = db.Column(db.String(100))
    dob = db.Column(db.DateTime, nullable=False)
    scores = db.relationship('Score', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return False

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        return f'admin_{self.id}'
    
    def is_admin(self):
        return True

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    lectures = db.relationship('Lecture', backref='subject', lazy=True,
                             cascade='all, delete-orphan')

class Lecture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)  # Making video_url required since it's our content source
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Related content
    quizzes = db.relationship('Quiz', backref='lecture', lazy=True,
                            cascade='all, delete-orphan')
    summary = db.relationship('LectureSummary', backref='lecture', uselist=False, 
                            cascade='all, delete-orphan')
    flashcards = db.relationship('LectureFlashcard', backref='lecture', lazy=True, 
                               cascade='all, delete-orphan')
    notes = db.relationship('LectureNote', backref='lecture', lazy=True, 
                          cascade='all, delete-orphan')
    timestamps = db.relationship('LectureTimestamp', backref='lecture', lazy=True, 
                               cascade='all, delete-orphan')

class LectureSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LectureFlashcard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    front = db.Column(db.Text, nullable=False)
    back = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LectureNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LectureTimestamp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)  # timestamp in seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    date_of_quiz = db.Column(db.DateTime, nullable=False)
    time_duration = db.Column(db.Integer, nullable=False)  # in minutes
    remarks = db.Column(db.Text)
    is_ai_generated = db.Column(db.Boolean, default=False)
    questions = db.relationship('Question', backref='quiz', lazy=True,
                              cascade='all, delete-orphan')
    scores = db.relationship('Score', backref='quiz', lazy=True,
                           cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    question_statement = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(200), nullable=False)
    option2 = db.Column(db.String(200), nullable=False)
    option3 = db.Column(db.String(200), nullable=False)
    option4 = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.Integer, nullable=False)  # 1, 2, 3, or 4

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_scored = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    time_stamp_of_attempt = db.Column(db.DateTime, nullable=False,
                                    default=datetime.utcnow)
    time_taken = db.Column(db.Integer, nullable=False)  # time taken in minutes
    feedback = db.Column(db.Text)  # JSON string containing detailed question feedback
