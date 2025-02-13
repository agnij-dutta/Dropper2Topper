# Quiz Master - Technical Documentation

## Overview
Quiz Master is a sophisticated web-based quiz management system built with Flask, designed to facilitate exam preparation across multiple courses. The application implements a multi-user architecture with distinct roles for administrators and students, providing comprehensive quiz management and performance tracking capabilities.

## Technical Stack

### Backend
- **Framework**: Flask 3.0.0
- **Database ORM**: SQLAlchemy 2.0.25
- **Authentication**: Flask-Login 0.6.3
- **Database Migrations**: Flask-Migrate 4.0.5 with Alembic
- **Database**: SQLite (quiz_master.db)

### Frontend
- **Framework**: Bootstrap 5.3
- **Icons**: Font Awesome 6.0
- **JavaScript**: Vanilla JS with ES6+ features
- **CSS**: Custom styles with CSS variables for theming

## System Architecture

### Database Models

#### User Model
```python
class User(UserMixin, db.Model):
    - id: Primary Key
    - email: Unique email address
    - password_hash: Securely hashed password
    - full_name: User's full name
    - qualification: Educational qualification
    - dob: Date of birth
    - scores: Relationship with Score model
```

#### Admin Model
```python
class Admin(UserMixin, db.Model):
    - id: Primary Key
    - username: Unique username
    - password_hash: Securely hashed password
```

#### Subject Model
```python
class Subject(db.Model):
    - id: Primary Key
    - name: Subject name
    - description: Subject description
    - chapters: One-to-many relationship with Chapter
```

#### Chapter Model
```python
class Chapter(db.Model):
    - id: Primary Key
    - subject_id: Foreign Key to Subject
    - name: Chapter name
    - description: Chapter description
    - quizzes: One-to-many relationship with Quiz
```

#### Quiz Model
```python
class Quiz(db.Model):
    - id: Primary Key
    - chapter_id: Foreign Key to Chapter
    - date_of_quiz: Scheduled date and time
    - time_duration: Duration in minutes
    - remarks: Additional notes
    - questions: One-to-many relationship with Question
    - scores: One-to-many relationship with Score
```

#### Question Model
```python
class Question(db.Model):
    - id: Primary Key
    - quiz_id: Foreign Key to Quiz
    - question_statement: The question text
    - option1-4: Multiple choice options
    - correct_option: Integer indicating correct answer (1-4)
```

#### Score Model
```python
class Score(db.Model):
    - id: Primary Key
    - quiz_id: Foreign Key to Quiz
    - user_id: Foreign Key to User
    - total_scored: Number of correct answers
    - total_questions: Total number of questions
    - time_stamp_of_attempt: When the quiz was taken
    - time_taken: Time taken in minutes
```

## Core Features

### Authentication System
1. **User Registration**
   - Email validation
   - Password hashing using Werkzeug security
   - Profile information collection (name, qualification, DOB)

2. **Multiple Login Systems**
   - Separate login routes for admin and students
   - Session management using Flask-Login
   - Role-based access control using custom decorators

### Admin Features
1. **Subject Management**
   - CRUD operations for subjects
   - Subject description and organization

2. **Chapter Management**
   - CRUD operations for chapters within subjects
   - Chapter organization and sequencing

3. **Quiz Management**
   - Quiz creation with multiple choice questions
   - Scheduling with date and time
   - Duration setting
   - Question bank management
   - Real-time quiz editing capabilities

4. **Analytics Dashboard**
   - Overall statistics
   - Student rankings
   - Subject-wise performance metrics
   - Time-based analytics
   - Chapter-wise statistics

### Student Features
1. **Quiz Taking**
   - Real-time quiz interface
   - Timer functionality
   - Auto-submission
   - Progress saving
   - Multiple choice selection

2. **Performance Tracking**
   - Personal dashboard
   - Subject-wise performance analysis
   - Historical quiz attempts
   - Ranking information
   - Performance trends

## Security Features

1. **Authentication Security**
   - Password hashing using Werkzeug
   - Session management
   - CSRF protection
   - Role-based access control

2. **Quiz Security**
   - Time-based access control
   - Single attempt enforcement
   - Auto-submission on timeout
   - Session validation

## Data Analytics

### Student Analytics
- Overall performance metrics
- Subject-wise breakdown
- Time-based analysis
- Ranking system
- Percentile calculation

### Quiz Analytics
- Attempt distribution
- Time-taken analysis
- Success rate tracking
- Chapter-wise performance

## Frontend Architecture

### Template Structure
1. **Base Template (base.html)**
   - Common layout
   - Navigation
   - Footer
   - CSS/JS includes

2. **Dashboard Templates**
   - Admin dashboard
   - Student dashboard
   - Analytics views

3. **Quiz Templates**
   - Quiz creation/editing
   - Quiz taking interface
   - Results view

### UI Components
1. **Navigation**
   - Responsive navbar
   - Role-based menu items
   - Breadcrumb navigation

2. **Dashboard Cards**
   - Statistics cards
   - Performance indicators
   - Quick action buttons

3. **Forms**
   - Quiz creation forms
   - Question management
   - Registration/login forms

### Interactive Features
1. **Quiz Timer**
   - Real-time countdown
   - Auto-submission
   - Visual warnings

2. **Progress Tracking**
   - Progress bars
   - Score displays
   - Performance charts

## Deployment Requirements

### System Requirements
- Python 3.8+
- SQLite3
- Modern web browser with JavaScript enabled

### Installation Steps
1. Virtual environment setup
2. Dependencies installation
3. Database initialization
4. Environment configuration
5. Application startup

### Configuration
- Secret key configuration
- Database URI setting
- Debug mode control
- Admin credentials setup

## Future Enhancements

1. **Technical Improvements**
   - Redis caching integration
   - Async quiz submission
   - Real-time notifications
   - API endpoints for mobile apps

2. **Feature Additions**
   - Advanced analytics
   - PDF report generation
   - Bulk question import
   - Question categorization
   - Student groups/batches

3. **UI Enhancements**
   - Dark mode support
   - Custom themes
   - Mobile app development
   - Accessibility improvements

## Maintenance

### Database Maintenance
- Regular backups
- Migration management
- Performance optimization
- Data cleanup

### Security Updates
- Regular dependency updates
- Security patch application
- Access log monitoring
- Session management review

### Performance Monitoring
- Response time tracking
- Error logging
- User activity monitoring
- Resource usage optimization