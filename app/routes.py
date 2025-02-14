from flask import render_template, request, redirect, url_for, flash, jsonify, abort, session, Response
from flask_login import login_user, login_required, logout_user, current_user
from app import db, login_manager
from app.models import (User, Admin, Subject, Quiz, Question, Score,
                     Lecture, LectureSummary, LectureFlashcard, LectureNote, LectureTimestamp)
from services.ai_service import LectureAIService
from services.video_service import VideoService
from services.quiz_service import QuizService
from services.flashcard_service import FlashcardService
from datetime import datetime, timedelta
import json
import queue
import threading
from functools import wraps
from flask import current_app as app
import re
from app.thread_monitor import thread_monitor

# Global queue for progress updates with thread safety
progress_queues = {}
progress_lock = threading.Lock()

def send_progress_update(lecture_id: int, component: str, progress: int):
    """Thread-safe progress update for AI content generation"""
    with progress_lock:
        if lecture_id in progress_queues:
            try:
                progress_queues[lecture_id].put({
                    'component': component,
                    'progress': progress
                })
            except Exception as e:
                print(f"Error sending progress update: {str(e)}")

def get_progress_queue(lecture_id: int) -> queue.Queue:
    """Thread-safe progress queue getter"""
    with progress_lock:
        if lecture_id not in progress_queues:
            progress_queues[lecture_id] = queue.Queue()
        return progress_queues[lecture_id]

def cleanup_progress_queue(lecture_id: int):
    """Thread-safe progress queue cleanup"""
    with progress_lock:
        if lecture_id in progress_queues:
            del progress_queues[lecture_id]

@app.route('/lecture/<int:lecture_id>/generation-progress')
def generation_progress(lecture_id):
    """SSE endpoint for progress updates with improved error handling"""
    def generate():
        keepalive_count = 0
        max_keepalive = 60  # Maximum number of keepalive messages before timing out
        
        try:
            q = get_progress_queue(lecture_id)
            
            while True:
                try:
                    # Use get with timeout to prevent infinite blocking
                    progress = q.get(timeout=10)  # 10 second timeout, more frequent checks
                    
                    # Reset keepalive counter on actual progress
                    keepalive_count = 0
                    
                    if progress.get('component') == 'error':
                        # Send error event with detailed info
                        error_data = {
                            'error': progress.get('progress'),
                            'status': 'error',
                            'component': progress.get('component')
                        }
                        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                        break
                        
                    elif progress.get('component') == 'complete':
                        # Send completion event
                        yield f"data: {json.dumps(progress)}\n\n"
                        break
                        
                    else:
                        # Send regular progress update
                        yield f"data: {json.dumps(progress)}\n\n"
                        
                except queue.Empty:
                    keepalive_count += 1
                    if keepalive_count >= max_keepalive:
                        # Send timeout error after no progress for too long
                        error_data = {
                            'error': 'Content generation timed out - no progress updates received',
                            'status': 'timeout',
                            'component': 'system'
                        }
                        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                        break
                    # Send keep-alive comment
                    yield ": keepalive\n\n"
                    
                except Exception as e:
                    # Log the error and send detailed error event
                    error_msg = f"Error in progress monitoring: {str(e)}"
                    print(error_msg)
                    error_data = {
                        'error': error_msg,
                        'status': 'error',
                        'component': 'system'
                    }
                    yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                    break
                    
        except Exception as outer_error:
            # Handle initialization errors
            error_msg = f"Failed to initialize progress monitoring: {str(outer_error)}"
            print(error_msg)
            error_data = {
                'error': error_msg,
                'status': 'error',
                'component': 'system'
            }
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            
        finally:
            # Always clean up
            cleanup_progress_queue(lecture_id)
            
            # If thread died unexpectedly, try to clean up the lecture
            if keepalive_count >= max_keepalive:
                try:
                    with app.app_context():
                        lecture = Lecture.query.get(lecture_id)
                        if lecture and not any([
                            LectureSummary.query.filter_by(lecture_id=lecture_id).first(),
                            LectureFlashcard.query.filter_by(lecture_id=lecture_id).first(),
                            LectureNote.query.filter_by(lecture_id=lecture_id).first(),
                            Quiz.query.filter_by(lecture_id=lecture_id).first()
                        ]):
                            # No content was generated, delete the lecture
                            db.session.delete(lecture)
                            db.session.commit()
                except Exception as cleanup_error:
                    print(f"Error during lecture cleanup: {str(cleanup_error)}")
    
    return Response(generate(), mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'Connection': 'keep-alive',
                       'X-Accel-Buffering': 'no'  # Disable proxy buffering
                   })

def generate_ai_content(app, lecture, options):
    """Generate AI content with progress updates and thread monitoring"""
    try:
        with app.app_context():
            ai_service = LectureAIService()
            video_service = VideoService()
            quiz_service = QuizService(ai_service)
            flashcard_service = FlashcardService()
            
            def safe_progress_update(lecture_id, component, progress):
                """Send progress update and notify thread monitor"""
                if lecture_id in progress_queues:
                    try:
                        progress_queues[lecture_id].put({
                            'component': component,
                            'progress': progress
                        })
                        # Update thread monitor
                        thread_monitor.update_progress(lecture_id)
                    except Exception as e:
                        print(f"Error sending progress update: {str(e)}")

            try:
                # Get transcript and send initial progress
                safe_progress_update(lecture.id, 'transcript', 0)
                transcript_data = video_service.get_transcript(lecture.video_url)
                transcript_text = transcript_data['full_text']
                safe_progress_update(lecture.id, 'transcript', 100)
                
                # Generate each type of content based on options
                if options.get('generate_summary'):
                    safe_progress_update(lecture.id, 'summary', 0)
                    summary_content = ai_service.generate_summary(transcript_text)
                    if summary_content:
                        summary = LectureSummary(lecture_id=lecture.id, content=summary_content)
                        db.session.add(summary)
                        safe_progress_update(lecture.id, 'summary', 100)
                    else:
                        raise ValueError('Summary generation failed')
                
                if options.get('generate_flashcards'):
                    safe_progress_update(lecture.id, 'flashcards', 0)
                    flashcard_result = flashcard_service.generate_flashcards(transcript_text)
                    if not flashcard_result.get('success'):
                        raise ValueError(f"Flashcard generation failed: {flashcard_result.get('error', 'Unknown error')}")
                    
                    flashcards = flashcard_result['flashcards']
                    total_cards = len(flashcards)
                    for i, card in enumerate(flashcards, 1):
                        flashcard = LectureFlashcard(
                            lecture_id=lecture.id,
                            front=card['front'],
                            back=card['back']
                        )
                        db.session.add(flashcard)
                        if i % 2 == 0:
                            safe_progress_update(lecture.id, 'flashcards', int((i/total_cards) * 100))
                    safe_progress_update(lecture.id, 'flashcards', 100)
                
                if options.get('generate_notes'):
                    safe_progress_update(lecture.id, 'notes', 0)
                    notes_content = ai_service.generate_notes(transcript_text)
                    if notes_content:
                        notes = LectureNote(lecture_id=lecture.id, content=notes_content)
                        db.session.add(notes)
                        safe_progress_update(lecture.id, 'notes', 100)
                    else:
                        raise ValueError('Notes generation failed')

                if options.get('generate_quiz'):
                    safe_progress_update(lecture.id, 'quiz', 0)
                    num_questions = options.get('num_questions', 10)
                    if 5 <= num_questions <= 50:
                        quiz_result = quiz_service.generate_quiz(transcript_text, num_questions)
                        
                        if not quiz_result.get('success'):
                            raise ValueError(f"Quiz generation failed: {quiz_result.get('error', 'Unknown error')}")
                        
                        questions = quiz_result['questions']
                        quiz = Quiz(
                            lecture_id=lecture.id,
                            date_of_quiz=datetime.now() + timedelta(days=1),
                            time_duration=30,
                            remarks=f'AI-generated quiz from lecture: {lecture.title}',
                            is_ai_generated=True
                        )
                        db.session.add(quiz)
                        db.session.flush()
                        
                        total_questions = len(questions)
                        for i, q in enumerate(questions, 1):
                            question = Question(
                                quiz_id=quiz.id,
                                question_statement=q['question_statement'],
                                option1=q['options'][0],
                                option2=q['options'][1],
                                option3=q['options'][2],
                                option4=q['options'][3],
                                correct_option=q['correct_option']
                            )
                            db.session.add(question)
                            safe_progress_update(lecture.id, 'quiz', int((i/total_questions) * 100))
                        safe_progress_update(lecture.id, 'quiz', 100)
                    else:
                        raise ValueError('Invalid number of questions')
                
                db.session.commit()
                safe_progress_update(lecture.id, 'complete', 100)
            
            except Exception as e:
                db.session.rollback()
                error_msg = str(e)
                print(f"Error in content generation: {error_msg}")
                safe_progress_update(lecture.id, 'error', error_msg)
                raise
    finally:
        # Clean up
        cleanup_progress_queue(lecture.id)
        thread_monitor.unregister_thread(lecture.id)

@login_manager.user_loader
def load_user(user_id):
    # Check if it's an admin ID (prefixed with 'admin_')
    if user_id.startswith('admin_'):
        return Admin.query.get(int(user_id[6:]))  # Remove 'admin_' prefix
    else:
        return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Access denied. Admin privileges required.')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.is_admin():
            flash('Access denied. Student account required.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('user_dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        logout_user()  # Logout regular user if trying to access admin login
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and admin.check_password(password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin_login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        qualification = request.form.get('qualification')
        dob = datetime.strptime(request.form.get('dob'), '%Y-%m-%d')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
            
        user = User(email=email, full_name=full_name, 
                   qualification=qualification, dob=dob)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    subjects = Subject.query.all()
    quizzes = Quiz.query.all()
    lectures = Lecture.query.all()
    
    # Get all students
    students = User.query.all()
    
    # Overall statistics
    overall_stats = {
        'total_students': len(students),
        'total_quizzes': len(quizzes),
        'total_attempts': Score.query.count(),
        'avg_score': db.session.query(db.func.avg(Score.total_scored * 100.0 / Score.total_questions)).scalar() or 0,
        'avg_time_taken': db.session.query(db.func.avg(Score.time_taken)).scalar() or 0
    }
    
    # Get hourly attempt distribution
    hourly_attempts = db.session.query(
        db.func.extract('hour', Score.time_stamp_of_attempt).label('hour'),
        db.func.count().label('count')
    ).group_by('hour').all()
    
    # Get daily attempt distribution for last 7 days
    seven_days_ago = datetime.now() - timedelta(days=7)
    daily_attempts = db.session.query(
        db.func.date(Score.time_stamp_of_attempt).label('date'),
        db.func.count().label('count')
    ).filter(Score.time_stamp_of_attempt >= seven_days_ago)\
     .group_by('date').all()
    
    # Get quiz-wise average time taken
    quiz_time_stats = db.session.query(
        Quiz.id,
        Quiz.lecture_id,
        db.func.avg(Score.time_taken).label('avg_time')
    ).join(Score).group_by(Quiz.id).all()
    
    # Add time-based metrics to overall_stats
    overall_stats.update({
        'hourly_attempts': {str(hour): count for hour, count in hourly_attempts},
        'daily_attempts': {str(date): count for date, count in daily_attempts},
        'quiz_time_stats': {quiz_id: {'lecture_id': lecture_id, 'avg_time': float(avg_time)} 
                           for quiz_id, lecture_id, avg_time in quiz_time_stats}
    })
    
    # Student rankings
    student_rankings = []
    for student in students:
        scores = Score.query.filter_by(user_id=student.id).all()
        if scores:
            avg_score = sum(s.total_scored * 100.0 / s.total_questions for s in scores) / len(scores)
            total_attempts = len(scores)
            # Calculate subject-wise performance
            subject_performance = {}
            for subject in subjects:
                subject_quizzes = Quiz.query.join(Lecture).filter(Lecture.subject_id == subject.id).all()
                if subject_quizzes:
                    quiz_ids = [q.id for q in subject_quizzes]
                    subject_scores = [s for s in scores if s.quiz_id in quiz_ids]
                    if subject_scores:
                        subject_avg = sum(s.total_scored * 100.0 / s.total_questions for s in subject_scores) / len(subject_scores)
                        subject_performance[subject.name] = subject_avg
            
            student_rankings.append({
                'student': student,
                'avg_score': avg_score,
                'total_attempts': total_attempts,
                'subject_performance': subject_performance
            })
    
    # Sort by average score
    student_rankings.sort(key=lambda x: x['avg_score'], reverse=True)
    
    # Add rank to each student
    for i, ranking in enumerate(student_rankings, 1):
        ranking['rank'] = i
    
    # Subject-wise statistics
    subject_stats = []
    for subject in subjects:
        subject_quizzes = Quiz.query.join(Lecture).filter(Lecture.subject_id == subject.id).all()
        if subject_quizzes:
            quiz_ids = [q.id for q in subject_quizzes]
            scores = Score.query.filter(Score.quiz_id.in_(quiz_ids)).all()
            if scores:
                all_scores = [s.total_scored * 100.0 / s.total_questions for s in scores]
                avg_score = sum(all_scores) / len(all_scores)
                # Calculate median
                sorted_scores = sorted(all_scores)
                mid = len(sorted_scores) // 2
                median = sorted_scores[mid] if len(sorted_scores) % 2 else (sorted_scores[mid-1] + sorted_scores[mid]) / 2
                # Calculate mode
                from statistics import mode, multimode
                try:
                    score_mode = mode(all_scores)
                except:
                    score_mode = multimode(all_scores)[0]  # Take first mode if multiple exist
                
                subject_stats.append({
                    'subject': subject,
                    'avg_score': avg_score,
                    'median_score': median,
                    'mode_score': score_mode,
                    'total_attempts': len(scores),
                    'num_quizzes': len(subject_quizzes)
                })
    
    return render_template('admin_dashboard.html',
                         subjects=subjects,
                         quizzes=quizzes,
                         lectures=lectures,
                         overall_stats=overall_stats,
                         student_rankings=student_rankings,
                         subject_stats=subject_stats)

@app.route('/user/dashboard')
@login_required
@student_required
def user_dashboard():
    # Get available quizzes (future quizzes)
    available_quizzes = Quiz.query.filter(Quiz.date_of_quiz > datetime.now()).all()
    
    # Get user's quiz attempts
    user_scores = Score.query.filter_by(user_id=current_user.id).order_by(Score.time_stamp_of_attempt.desc()).all()
    
    # Get all subjects with their lectures
    subjects = Subject.query.order_by(Subject.name).all()
    
    # Calculate overall statistics
    total_attempts = len(user_scores)
    
    # Initialize stats with default values
    overall_stats = {
        'total_attempts': total_attempts,
        'total_questions': 0,
        'avg_score': 0,
        'avg_time_taken': 0,
        'personal_best': 0,
        'recent_avg': 0
    }
    
    if total_attempts > 0:
        # Calculate total questions answered
        total_questions = sum(score.total_questions for score in user_scores)
        overall_stats['total_questions'] = total_questions
        
        # Calculate average score
        total_score_percentage = sum(s.total_scored * 100.0 / s.total_questions for s in user_scores)
        overall_stats['avg_score'] = total_score_percentage / total_attempts
        
        # Calculate personal best
        overall_stats['personal_best'] = max(s.total_scored * 100.0 / s.total_questions for s in user_scores)
        
        # Calculate recent average (last 5 attempts)
        recent_scores = user_scores[:5]
        overall_stats['recent_avg'] = sum(s.total_scored * 100.0 / s.total_questions for s in recent_scores) / len(recent_scores)
        
        # Calculate average time taken
        overall_stats['avg_time_taken'] = sum(s.time_taken for s in user_scores) / total_attempts
    
    # Calculate user's ranking
    all_students = User.query.all()
    rankings = []
    for student in all_students:
        scores = Score.query.filter_by(user_id=student.id).all()
        if scores:
            student_avg = sum(s.total_scored * 100.0 / s.total_questions for s in scores) / len(scores)
            rankings.append((student.id, student_avg))
    
    # Sort by average score
    rankings.sort(key=lambda x: x[1], reverse=True)
    
    # Calculate ranking info with defaults
    ranking_info = {
        'rank': 'N/A',
        'total_students': len(rankings),
        'percentile': 0
    }
    
    # Update ranking if user has scores
    if rankings:
        try:
            user_rank = next((i for i, (student_id, _) in enumerate(rankings, 1) if student_id == current_user.id), None)
            if user_rank is not None:
                ranking_info.update({
                    'rank': user_rank,
                    'percentile': ((len(rankings) - user_rank + 1) / len(rankings)) * 100
                })
        except Exception as e:
            print(f"Error calculating rank: {str(e)}")
    
    # Calculate subject-wise performance
    subject_performance = []
    for subject in subjects:
        # Get all quizzes for this subject
        subject_quizzes = Quiz.query.join(Lecture).filter(Lecture.subject_id == subject.id).all()
        if subject_quizzes:
            quiz_ids = [q.id for q in subject_quizzes]
            subject_scores = [s for s in user_scores if s.quiz_id in quiz_ids]
            
            if subject_scores:
                total_subject_attempts = len(subject_scores)
                subject_avg = sum(s.total_scored * 100.0 / s.total_questions for s in subject_scores) / total_subject_attempts
                subject_best = max(s.total_scored * 100.0 / s.total_questions for s in subject_scores)
                
                subject_performance.append({
                    'subject': subject,
                    'avg_score': subject_avg,
                    'best_score': subject_best,
                    'total_attempts': total_subject_attempts
                })

    return render_template('user_dashboard.html',
                         subjects=subjects,  # Added subjects for lectures
                         available_quizzes=available_quizzes,
                         user_scores=user_scores,
                         total_attempts=total_attempts,
                         average_score=overall_stats['avg_score'],
                         personal_best=overall_stats['personal_best'],
                         recent_avg=overall_stats['recent_avg'],
                         overall_stats=overall_stats,
                         subject_performance=subject_performance,
                         ranking_info=ranking_info)

# Admin routes for managing subjects, chapters, and quizzes
@app.route('/admin/subject/add', methods=['POST'])
@login_required
@admin_required
def add_subject():
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Subject name is required')
        return redirect(url_for('admin_dashboard'))
        
    subject = Subject(name=name, description=description)
    db.session.add(subject)
    db.session.commit()
    
    flash('Subject added successfully')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/subject/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash('Subject deleted successfully')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/quiz/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_quiz():
    if request.method == 'POST':
        lecture_id = request.form.get('lecture_id')
        date_of_quiz = datetime.strptime(request.form.get('date_of_quiz'), '%Y-%m-%dT%H:%M')
        time_duration = int(request.form.get('time_duration'))
        remarks = request.form.get('remarks')
        
        if not all([lecture_id, date_of_quiz, time_duration]):
            flash('All fields are required')
            return redirect(url_for('create_quiz'))
            
        # Validate quiz date is in the future
        if date_of_quiz <= datetime.now():
            flash('Quiz date must be in the future')
            return redirect(url_for('create_quiz'))
            
        quiz = Quiz(
            lecture_id=lecture_id,
            date_of_quiz=date_of_quiz,
            time_duration=time_duration,
            remarks=remarks
        )
        db.session.add(quiz)
        db.session.commit()
        
        questions_data = parse_questions_from_form(request.form)
        if not questions_data:
            flash('At least one question is required')
            db.session.delete(quiz)
            db.session.commit()
            return redirect(url_for('create_quiz'))
        
        try:
            for q_data in questions_data:
                # Validate all question fields are present
                if not all([
                    q_data['statement'],
                    q_data['option1'],
                    q_data['option2'],
                    q_data['option3'],
                    q_data['option4'],
                    q_data['correct_option']
                ]):
                    flash('All question fields are required')
                    db.session.delete(quiz)
                    db.session.commit()
                    return redirect(url_for('create_quiz'))
                    
                question = Question(
                    quiz_id=quiz.id,
                    question_statement=q_data['statement'].strip(),
                    option1=q_data['option1'].strip(),
                    option2=q_data['option2'].strip(),
                    option3=q_data['option3'].strip(),
                    option4=q_data['option4'].strip(),
                    correct_option=int(q_data['correct_option'])
                )
                db.session.add(question)
            
            db.session.commit()
            flash('Quiz created successfully')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating quiz. Please try again.')
            return redirect(url_for('create_quiz'))
    
    lectures = Lecture.query.join(Subject).order_by(Subject.name, Lecture.title).all()
    return render_template('quiz_form.html', lectures=lectures)

@app.route('/admin/quiz/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if quiz has been attempted
    if Score.query.filter_by(quiz_id=quiz_id).first():
        flash('Cannot edit quiz that has been attempted')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        lecture_id = request.form.get('lecture_id')
        date_of_quiz = datetime.strptime(request.form.get('date_of_quiz'), '%Y-%m-%dT%H:%M')
        time_duration = int(request.form.get('time_duration'))
        remarks = request.form.get('remarks')
        
        if not all([lecture_id, date_of_quiz, time_duration]):
            flash('All fields are required')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
            
        # Validate quiz date is in the future
        if date_of_quiz <= datetime.now():
            flash('Quiz date must be in the future')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
            
        quiz.lecture_id = lecture_id
        quiz.date_of_quiz = date_of_quiz
        quiz.time_duration = time_duration
        quiz.remarks = remarks
        
        # Delete existing questions
        Question.query.filter_by(quiz_id=quiz.id).delete()
        
        try:
            # Add new questions
            questions_data = parse_questions_from_form(request.form)
            if not questions_data:
                flash('At least one question is required')
                return redirect(url_for('edit_quiz', quiz_id=quiz_id))
                
            for q_data in questions_data:
                # Validate all question fields are present
                if not all([
                    q_data['statement'],
                    q_data['option1'],
                    q_data['option2'],
                    q_data['option3'],
                    q_data['option4'],
                    q_data['correct_option']
                ]):
                    flash('All question fields are required')
                    return redirect(url_for('edit_quiz', quiz_id=quiz_id))
                    
                question = Question(
                    quiz_id=quiz.id,
                    question_statement=q_data['statement'].strip(),
                    option1=q_data['option1'].strip(),
                    option2=q_data['option2'].strip(),
                    option3=q_data['option3'].strip(),
                    option4=q_data['option4'].strip(),
                    correct_option=int(q_data['correct_option'])
                )
                db.session.add(question)
            
            db.session.commit()
            flash('Quiz updated successfully')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating quiz. Please try again.')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
    
    lectures = Lecture.query.join(Subject).order_by(Subject.name, Lecture.title).all()
    return render_template('quiz_form.html', quiz=quiz, lectures=lectures)

@app.route('/admin/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if quiz has been attempted
    if Score.query.filter_by(quiz_id=quiz_id).first():
        flash('Cannot delete quiz that has been attempted')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Delete all questions first
        Question.query.filter_by(quiz_id=quiz_id).delete()
        db.session.delete(quiz)
        db.session.commit()
        flash('Quiz deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting quiz. Please try again.')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/quiz/<int:quiz_id>/questions')
@login_required
@admin_required
def view_quiz_questions(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    return render_template('view_questions.html', quiz=quiz)

@app.route('/admin/quiz/<int:quiz_id>/question/add', methods=['POST'])
@login_required
@admin_required
def add_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    statement = request.form.get('statement')
    option1 = request.form.get('option1')
    option2 = request.form.get('option2')
    option3 = request.form.get('option3')
    option4 = request.form.get('option4')
    correct_option = request.form.get('correct_option')
    
    if not all([statement, option1, option2, option3, option4, correct_option]):
        flash('All fields are required')
        return redirect(url_for('view_quiz_questions', quiz_id=quiz_id))
    
    question = Question(
        quiz_id=quiz_id,
        question_statement=statement.strip(),
        option1=option1.strip(),
        option2=option2.strip(),
        option3=option3.strip(),
        option4=option4.strip(),
        correct_option=int(correct_option)
    )
    db.session.add(question)
    db.session.commit()
    
    flash('Question added successfully')
    return redirect(url_for('view_quiz_questions', quiz_id=quiz_id))

@app.route('/admin/question/<int:question_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    
    question.question_statement = request.form.get('statement').strip()
    question.option1 = request.form.get('option1').strip()
    question.option2 = request.form.get('option2').strip()
    question.option3 = request.form.get('option3').strip()
    question.option4 = request.form.get('option4').strip()
    question.correct_option = int(request.form.get('correct_option'))
    
    db.session.commit()
    flash('Question updated successfully')
    return redirect(url_for('view_quiz_questions', quiz_id=question.quiz_id))

@app.route('/admin/question/<int:question_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    quiz_id = question.quiz_id
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted successfully')
    return redirect(url_for('view_quiz_questions', quiz_id=quiz_id))

@app.route('/quiz/<int:quiz_id>/start')
@login_required
@student_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    now = datetime.now()
    
    # Check if quiz has ended
    quiz_end_time = quiz.date_of_quiz + timedelta(minutes=quiz.time_duration)
    if now > quiz_end_time:
        flash('This quiz has ended')
        return redirect(url_for('user_dashboard'))
    
    # Check if user has already attempted
    if Score.query.filter_by(quiz_id=quiz_id, user_id=current_user.id).first():
        flash('You have already attempted this quiz')
        return redirect(url_for('user_dashboard'))
    
    # Check if quiz has questions
    if not quiz.questions:
        flash('This quiz has no questions')
        return redirect(url_for('user_dashboard'))
    
    # Calculate quiz duration based on time remaining until quiz end
    remaining_time = min(
        quiz.time_duration,
        int((quiz_end_time - now).total_seconds() / 60)
    )
    
    if remaining_time <= 0:
        flash('This quiz has ended')
        return redirect(url_for('user_dashboard'))
    
    # Store quiz timing in session
    quiz_start = now
    quiz_end = quiz_start + timedelta(minutes=remaining_time)
    
    session['quiz_start_time'] = quiz_start.timestamp()
    session['quiz_end_time'] = quiz_end.timestamp()
    session['quiz_id'] = quiz_id  # Store quiz ID to prevent session reuse
    
    return render_template('take_quiz.html',
                         quiz=quiz,
                         remaining_time=remaining_time,
                         now=now,
                         quiz_end_time=quiz_end)

@app.route('/quiz/<int:quiz_id>/submit', methods=['POST'])
@login_required
@student_required
def submit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    now = datetime.now()
    
    # Verify quiz session
    session_quiz_id = session.get('quiz_id')
    quiz_start_time = session.get('quiz_start_time')
    quiz_end_time = session.get('quiz_end_time')
    
    if not all([session_quiz_id, quiz_start_time, quiz_end_time]) or session_quiz_id != quiz_id:
        flash('Invalid quiz session')
        return redirect(url_for('user_dashboard'))
    
    quiz_start_time = datetime.fromtimestamp(quiz_start_time)
    quiz_end_time = datetime.fromtimestamp(quiz_end_time)
    
    # Check if quiz time has expired
    if now > quiz_end_time:
        flash('Quiz time has expired')
        return redirect(url_for('user_dashboard'))
    
    # Check if user has already attempted
    if Score.query.filter_by(quiz_id=quiz_id, user_id=current_user.id).first():
        flash('You have already attempted this quiz')
        return redirect(url_for('user_dashboard'))
    
    # Get quiz questions and submitted answers
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    submitted_answers = []
    correct_answers = []
    
    for question in questions:
        submitted_answer = request.form.get(f'answer_{question.id}')
        if not submitted_answer:
            flash('Please answer all questions')
            return redirect(url_for('take_quiz', quiz_id=quiz_id))
        
        submitted_answers.append(int(submitted_answer))
        correct_answers.append({
            'correct_option': question.correct_option,
            'options': [
                question.option1,
                question.option2,
                question.option3,
                question.option4
            ]
        })
    
    # Use QuizService to grade the quiz
    quiz_service = QuizService()
    result = quiz_service.grade_quiz(submitted_answers, correct_answers)
    
    if not result['success']:
        flash('Error grading quiz')
        return redirect(url_for('user_dashboard'))
    
    # Calculate time taken in minutes
    time_taken = int((now - quiz_start_time).total_seconds() / 60)
    
    # Save score with detailed feedback
    score = Score(
        quiz_id=quiz_id,
        user_id=current_user.id,
        total_scored=result['correct_count'],
        total_questions=result['total_questions'],
        time_stamp_of_attempt=now,
        time_taken=time_taken,
        feedback=json.dumps(result['feedback'])  # Store detailed feedback
    )
    db.session.add(score)
    db.session.commit()
    
    # Clear quiz session
    session.pop('quiz_start_time', None)
    session.pop('quiz_end_time', None)
    session.pop('quiz_id', None)
    
    flash(f'Quiz submitted successfully. You scored {result["correct_count"]} out of {result["total_questions"]}')
    return redirect(url_for('view_attempt', attempt_id=score.id))

@app.route('/attempt/<int:attempt_id>')
@login_required
def view_attempt(attempt_id):
    score = Score.query.get_or_404(attempt_id)
    
    # Only allow the user who took the quiz or an admin to view the attempt
    if score.user_id != current_user.id and not current_user.is_admin():
        flash('Access denied')
        return redirect(url_for('user_dashboard'))
    
    # Use QuizService to format questions for display
    quiz_service = QuizService()
    questions = Question.query.filter_by(quiz_id=score.quiz_id).all()
    formatted_questions = quiz_service.format_quiz_for_display([{
        'question_statement': q.question_statement,
        'options': [q.option1, q.option2, q.option3, q.option4],
        'correct_option': q.correct_option
    } for q in questions])
    
    # Get detailed feedback
    feedback = json.loads(score.feedback) if hasattr(score, 'feedback') and score.feedback else None
    
    return render_template('view_attempt.html',
                         score=score,
                         questions=formatted_questions,
                         feedback=feedback)

def parse_questions_from_form(form):
    questions = []
    i = 0
    while True:
        statement = form.get(f'questions[{i}][statement]')
        if not statement:
            break
            
        questions.append({
            'statement': statement,
            'option1': form.get(f'questions[{i}][option1]'),
            'option2': form.get(f'questions[{i}][option2]'),
            'option3': form.get(f'questions[{i}][option3]'),
            'option4': form.get(f'questions[{i}][option4]'),
            'correct_option': form.get(f'questions[{i}][correct_option]')
        })
        i += 1
    return questions

@app.route('/admin/lecture/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_lecture():
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        title = request.form.get('title')
        video_url = request.form.get('video_url')
        
        if not all([subject_id, title, video_url]):
            flash('Title, video URL and subject are required')
            return redirect(url_for('create_lecture'))
            
        lecture = Lecture(
            subject_id=subject_id,
            title=title,
            video_url=video_url
        )
        db.session.add(lecture)
        db.session.commit()
        
        if 'generate_ai_content' in request.form:
            try:
                options = {
                    'generate_summary': 'generate_summary' in request.form,
                    'generate_flashcards': 'generate_flashcards' in request.form,
                    'generate_notes': 'generate_notes' in request.form,
                    'generate_quiz': 'generate_quiz' in request.form,
                    'num_questions': int(request.form.get('num_questions', 10))
                }
                
                # Start AI content generation in a background thread
                thread = threading.Thread(
                    target=generate_ai_content,
                    args=(app, lecture, options)
                )
                thread.start()
                
                flash('Lecture created. AI content is being generated...')
                return redirect(url_for('view_lecture', lecture_id=lecture.id))
            except Exception as e:
                db.session.rollback()
                flash('Error starting AI content generation: ' + str(e))
                return redirect(url_for('admin_dashboard'))
        
        flash('Lecture created successfully')
        return redirect(url_for('admin_dashboard'))
    
    subjects = Subject.query.order_by(Subject.name).all()
    return render_template('lecture_form.html', subjects=subjects)

@app.route('/admin/lecture/<int:lecture_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_lecture(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)
    
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        title = request.form.get('title')
        video_url = request.form.get('video_url')
        
        if not all([subject_id, title, video_url]):
            flash('Title, video URL and subject are required')
            return redirect(url_for('edit_lecture', lecture_id=lecture_id))
            
        lecture.subject_id = subject_id
        lecture.title = title
        lecture.video_url = video_url
        
        # Regenerate AI content if requested
        if 'generate_ai_content' in request.form:
            try:
                ai_service = LectureAIService()
                video_service = VideoService()
                transcript_data = video_service.get_transcript(video_url)
                
                # Clear existing AI content based on selection
                if 'generate_summary' in request.form:
                    LectureSummary.query.filter_by(lecture_id=lecture_id).delete()
                if 'generate_flashcards' in request.form:
                    LectureFlashcard.query.filter_by(lecture_id=lecture_id).delete()
                if 'generate_notes' in request.form:
                    LectureNote.query.filter_by(lecture_id=lecture_id).delete()
                LectureTimestamp.query.filter_by(lecture_id=lecture_id).delete()
                
                # Generate new content based on selection
                if 'generate_summary' in request.form:
                    summary_content = ai_service.generate_summary(transcript_data['full_text'])
                    summary = LectureSummary(lecture_id=lecture.id, content=summary_content)
                    db.session.add(summary)
                
                if 'generate_flashcards' in request.form:
                    flashcards = ai_service.generate_flashcards(transcript_data['full_text'])
                    for card in flashcards:
                        flashcard = LectureFlashcard(
                            lecture_id=lecture.id,
                            front=card['front'],
                            back=card['back']
                        )
                        db.session.add(flashcard)
                
                if 'generate_notes' in request.form:
                    notes_content = ai_service.generate_notes(transcript_data['full_text'])
                    notes = LectureNote(lecture_id=lecture.id, content=notes_content)
                    db.session.add(notes)
                
                # Use timestamps from transcript directly
                for ts in transcript_data['timestamps']:
                    timestamp = LectureTimestamp(
                        lecture_id=lecture.id,
                        title=ts['text'],
                        timestamp=int(ts['start'])
                    )
                    db.session.add(timestamp)
                
                if 'generate_quiz' in request.form:
                    num_questions = int(request.form.get('num_questions', 10))
                    if 5 <= num_questions <= 50:
                        questions = ai_service.generate_quiz(transcript_data['full_text'], num_questions)
                        
                        quiz = Quiz(
                            lecture_id=lecture.id,
                            date_of_quiz=datetime.now() + timedelta(days=1),
                            time_duration=30,
                            remarks='AI-generated quiz from lecture: ' + title,
                            is_ai_generated=True
                        )
                        db.session.add(quiz)
                        db.session.flush()
                        
                        for q in questions:
                            question = Question(
                                quiz_id=quiz.id,
                                question_statement=q['question_statement'],
                                option1=q['options'][0],
                                option2=q['options'][1],
                                option3=q['options'][2],
                                option4=q['options'][3],
                                correct_option=q['correct_option']
                            )
                            db.session.add(question)
                
                db.session.commit()
                flash('Lecture and selected AI content updated successfully')
            except Exception as e:
                db.session.rollback()
                flash('Error regenerating AI content: ' + str(e))
                return redirect(url_for('admin_dashboard'))
        else:
            db.session.commit()
            flash('Lecture updated successfully')
        return redirect(url_for('admin_dashboard'))
    
    subjects = Subject.query.order_by(Subject.name).all()
    return render_template('lecture_form.html', lecture=lecture, subjects=subjects)

@app.route('/admin/lecture/<int:lecture_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_lecture(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)
    
    try:
        db.session.delete(lecture)
        db.session.commit()
        flash('Lecture deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting lecture: ' + str(e))
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/lecture/<int:lecture_id>/generate_quiz', methods=['POST'])
@login_required
@admin_required
def generate_lecture_quiz(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)
    num_questions = int(request.form.get('num_questions', 10))
    
    try:
        ai_service = LectureAIService()
        video_service = VideoService()
        quiz_service = QuizService(ai_service)
        
        # Get transcript from video
        transcript_data = video_service.get_transcript(lecture.video_url)
        transcript_text = transcript_data['full_text']
        
        # Generate quiz questions from transcript
        quiz_result = quiz_service.generate_quiz(transcript_text, num_questions)
        
        if not quiz_result.get('success'):
            raise ValueError(quiz_result.get('error', 'Failed to generate quiz questions'))
            
        questions = quiz_result['questions']
        
        quiz = Quiz(
            lecture_id=lecture.id,
            date_of_quiz=datetime.now() + timedelta(days=1),  # Schedule for tomorrow
            time_duration=30,  # 30 minutes default
            remarks='AI-generated quiz from lecture: ' + lecture.title,
            is_ai_generated=True
        )
        db.session.add(quiz)
        db.session.flush()
        
        for q in questions:
            question = Question(
                quiz_id=quiz.id,
                question_statement=q['question_statement'],
                option1=q['options'][0],
                option2=q['options'][1],
                option3=q['options'][2],
                option4=q['options'][3],
                correct_option=q['correct_option']
            )
            db.session.add(question)
        
        db.session.commit()
        flash('Quiz generated successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error generating quiz: ' + str(e))
    
    return redirect(url_for('view_lecture', lecture_id=lecture_id))

@app.route('/lecture/<int:lecture_id>')
@login_required
def view_lecture(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)
    return render_template('view_lecture.html', lecture=lecture)

@app.route('/admin/lecture/<int:lecture_id>/regenerate/<content_type>', methods=['POST'])
@login_required
@admin_required
def regenerate_lecture_content(lecture_id, content_type):
    lecture = Lecture.query.get_or_404(lecture_id)
    ai_service = LectureAIService()
    video_service = VideoService()
    
    try:
        # Get transcript from video
        transcript_data = video_service.get_transcript(lecture.video_url)
        transcript_text = transcript_data['full_text']
        
        if content_type == 'summary':
            LectureSummary.query.filter_by(lecture_id=lecture_id).delete()
            summary_content = ai_service.generate_summary(transcript_text)
            summary = LectureSummary(lecture_id=lecture.id, content=summary_content)
            db.session.add(summary)
            
        elif content_type == 'flashcards':
            LectureFlashcard.query.filter_by(lecture_id=lecture_id).delete()
            flashcards = ai_service.generate_flashcards(transcript_text)
            for card in flashcards:
                flashcard = LectureFlashcard(
                    lecture_id=lecture.id,
                    front=card['front'],
                    back=card['back']
                )
                db.session.add(flashcard)
                
        elif content_type == 'notes':
            LectureNote.query.filter_by(lecture_id=lecture_id).delete()
            notes_content = ai_service.generate_notes(transcript_text)
            notes = LectureNote(lecture_id=lecture.id, content=notes_content)
            db.session.add(notes)
            
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

def is_valid_youtube_url(url):
    """Validate YouTube URL format"""
    youtube_regex = r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})$'
    return re.match(youtube_regex, url) is not None

@app.route('/admin/lecture/process', methods=['POST'])
@login_required
@admin_required
def process_video():
    """Process video and generate AI content"""
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        # Create lecture
        subject_id = request.json.get('subject_id')
        title = request.json.get('title')

        if not all([subject_id, title]):
            return jsonify({'error': 'Subject ID and title are required'}), 400

        try:
            lecture = Lecture(
                subject_id=subject_id,
                title=title,
                video_url=url
            )
            db.session.add(lecture)
            db.session.commit()
        except Exception as db_error:
            db.session.rollback()
            return jsonify({'error': f'Database error: {str(db_error)}'}), 500

        # Define the options for AI content generation
        options = {
            'generate_summary': request.json.get('generate_summary', True),
            'generate_flashcards': request.json.get('generate_flashcards', True),
            'generate_notes': request.json.get('generate_notes', True),
            'generate_quiz': request.json.get('generate_quiz', False),
            'num_questions': request.json.get('num_questions', 10)
        }

        try:
            # Initialize progress queue with thread safety
            with progress_lock:
                progress_queues[lecture.id] = queue.Queue()

            # Start background processing
            thread = threading.Thread(
                target=generate_ai_content,
                args=(app._get_current_object(), lecture, options),
                name=f'AI_Content_Gen_{lecture.id}'
            )
            thread.daemon = True
            
            # Register thread with monitor before starting
            thread_monitor.register_thread(lecture.id, thread)
            thread.start()

            return jsonify({
                'success': True,
                'lecture_id': lecture.id,
                'message': 'Lecture created and content generation started'
            })

        except Exception as thread_error:
            cleanup_progress_queue(lecture.id)
            thread_monitor.unregister_thread(lecture.id)
            db.session.delete(lecture)
            db.session.commit()
            return jsonify({'error': f'Failed to start content generation: {str(thread_error)}'}), 500

    except Exception as e:
        print(f"[ERROR] An error occurred: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.template_filter('to_letter')
def to_letter(number):
    """Convert a number to corresponding uppercase letter (1=A, 2=B, etc.)"""
    return chr(64 + number)
