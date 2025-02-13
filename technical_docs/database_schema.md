# Database Schema Documentation

## Overview

This document provides a detailed explanation of the Quiz Master database schema, including table relationships, indexes, constraints, and query optimization strategies.

## Schema Diagram

```
User 1 --- * Score * --- 1 Quiz
Subject 1 --- * Chapter 1 --- * Quiz 1 --- * Question
Admin (standalone table)
```

## Table Specifications

### User Table
```sql
CREATE TABLE user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    qualification VARCHAR(100),
    dob DATETIME NOT NULL,
    CONSTRAINT email_format CHECK (email LIKE '%@%.%')
);

CREATE INDEX idx_user_email ON user(email);
```

**Constraints:**
- Primary key with auto-increment
- Unique email constraint
- Email format validation
- Non-null constraints on critical fields

### Admin Table
```sql
CREATE TABLE admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL
);

CREATE INDEX idx_admin_username ON admin(username);
```

**Security Considerations:**
- Separate table from regular users
- Unique username enforcement
- Password hashing with PBKDF2

### Subject Table
```sql
CREATE TABLE subject (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE UNIQUE INDEX idx_subject_name ON subject(name);
```

**Design Notes:**
- Simple structure for flexibility
- Optional description field
- Unique subject names enforced

### Chapter Table
```sql
CREATE TABLE chapter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    FOREIGN KEY (subject_id) REFERENCES subject(id) ON DELETE CASCADE,
    UNIQUE (subject_id, name)
);

CREATE INDEX idx_chapter_subject ON chapter(subject_id);
```

**Relationships:**
- Many-to-one with Subject
- Cascade deletion
- Compound uniqueness constraint

### Quiz Table
```sql
CREATE TABLE quiz (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    date_of_quiz DATETIME NOT NULL,
    time_duration INTEGER NOT NULL,
    remarks TEXT,
    FOREIGN KEY (chapter_id) REFERENCES chapter(id) ON DELETE CASCADE,
    CHECK (time_duration > 0)
);

CREATE INDEX idx_quiz_date ON quiz(date_of_quiz);
CREATE INDEX idx_quiz_chapter ON quiz(chapter_id);
```

**Constraints:**
- Positive duration check
- Future date validation in application code
- Composite index for common queries

### Question Table
```sql
CREATE TABLE question (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL,
    question_statement TEXT NOT NULL,
    option1 VARCHAR(200) NOT NULL,
    option2 VARCHAR(200) NOT NULL,
    option3 VARCHAR(200) NOT NULL,
    option4 VARCHAR(200) NOT NULL,
    correct_option INTEGER NOT NULL,
    FOREIGN KEY (quiz_id) REFERENCES quiz(id) ON DELETE CASCADE,
    CHECK (correct_option BETWEEN 1 AND 4)
);

CREATE INDEX idx_question_quiz ON question(quiz_id);
```

**Data Validation:**
- Valid option range check
- Non-null options requirement
- Cascading deletion with quiz

### Score Table
```sql
CREATE TABLE score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    total_scored INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    time_stamp_of_attempt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    time_taken INTEGER NOT NULL,
    FOREIGN KEY (quiz_id) REFERENCES quiz(id),
    FOREIGN KEY (user_id) REFERENCES user(id),
    UNIQUE (quiz_id, user_id),
    CHECK (total_scored <= total_questions),
    CHECK (time_taken > 0)
);

CREATE INDEX idx_score_user ON score(user_id);
CREATE INDEX idx_score_quiz ON score(quiz_id);
CREATE INDEX idx_score_timestamp ON score(time_stamp_of_attempt);
```

**Constraints:**
- One attempt per quiz per user
- Logical score validation
- Positive time taken check

## Query Optimization

### Common Queries

1. **User Dashboard Statistics**
```sql
SELECT 
    s.quiz_id,
    q.chapter_id,
    c.subject_id,
    s.total_scored,
    s.total_questions,
    s.time_taken
FROM score s
JOIN quiz q ON s.quiz_id = q.id
JOIN chapter c ON q.chapter_id = c.id
WHERE s.user_id = ?
ORDER BY s.time_stamp_of_attempt DESC;
```

2. **Subject Performance Analysis**
```sql
SELECT 
    sub.name,
    COUNT(s.id) as attempts,
    AVG(s.total_scored * 100.0 / s.total_questions) as avg_score
FROM subject sub
JOIN chapter c ON c.subject_id = sub.id
JOIN quiz q ON q.chapter_id = c.id
JOIN score s ON s.quiz_id = q.id
WHERE s.user_id = ?
GROUP BY sub.id;
```

3. **Recent Quiz Attempts**
```sql
SELECT 
    q.id,
    ch.name as chapter_name,
    s.total_scored,
    s.total_questions,
    s.time_taken
FROM quiz q
JOIN chapter ch ON q.chapter_id = ch.id
LEFT JOIN score s ON s.quiz_id = q.id
WHERE q.date_of_quiz > DATETIME('now')
ORDER BY q.date_of_quiz ASC
LIMIT 10;
```

### Index Usage

1. **Composite Indexes**
```sql
-- For quiz scheduling queries
CREATE INDEX idx_quiz_chapter_date ON quiz(chapter_id, date_of_quiz);

-- For user performance analysis
CREATE INDEX idx_score_user_timestamp ON score(user_id, time_stamp_of_attempt);
```

2. **Covering Indexes**
```sql
-- For quick score lookups
CREATE INDEX idx_score_quiz_user_total ON score(quiz_id, user_id, total_scored, total_questions);
```

## Performance Considerations

### Query Optimization Strategies

1. **Eager Loading**
```python
# Efficient quiz loading with questions
Quiz.query.options(
    joinedload(Quiz.questions),
    joinedload(Quiz.chapter).joinedload(Chapter.subject)
).filter_by(id=quiz_id).first()
```

2. **Pagination**
```python
Score.query.filter_by(user_id=user_id)\
    .order_by(Score.time_stamp_of_attempt.desc())\
    .paginate(page=page, per_page=10)
```

### Data Access Patterns

1. **Common Access Paths**
- User → Scores → Quizzes
- Subject → Chapters → Quizzes
- Quiz → Questions

2. **Optimization Techniques**
- Strategic use of indexes
- Proper join order
- Result limiting
- Cursor-based pagination

## Maintenance Procedures

### Regular Maintenance

1. **Index Maintenance**
```sql
ANALYZE;
VACUUM;
```

2. **Statistics Update**
```sql
ANALYZE score;
ANALYZE quiz;
```

### Backup Procedures

1. **Database Backup**
```bash
sqlite3 quiz_master.db ".backup 'backup.db'"
```

2. **Selective Data Export**
```sql
.mode csv
.output quiz_data.csv
SELECT * FROM quiz;
```

## Migration Guidelines

### Adding New Fields

1. **Creating Migration**
```python
def upgrade():
    op.add_column('quiz', sa.Column('max_attempts', sa.Integer(), nullable=True))
    op.execute('UPDATE quiz SET max_attempts = 1')
    op.alter_column('quiz', 'max_attempts', nullable=False)
```

2. **Rollback Procedure**
```python
def downgrade():
    op.drop_column('quiz', 'max_attempts')
```

### Data Migration

1. **Safe Data Transfer**
```python
def migrate_data():
    connection = op.get_bind()
    # Perform data migration
    connection.execute(
        'UPDATE score SET time_taken = ? WHERE time_taken IS NULL',
        [default_time]
    )
```

## Monitoring and Optimization

### Performance Monitoring

1. **Query Analysis**
```sql
EXPLAIN QUERY PLAN
SELECT * FROM score WHERE user_id = ? ORDER BY time_stamp_of_attempt DESC;
```

2. **Index Usage Stats**
```sql
SELECT * FROM sqlite_stat1;
```

### Optimization Recommendations

1. **Index Selection**
- Create indexes based on WHERE, ORDER BY, and JOIN conditions
- Consider storage vs. query speed tradeoffs
- Monitor index usage patterns

2. **Query Optimization**
- Use appropriate joins
- Limit result sets
- Consider denormalization for heavy read operations