# Authentication and Security Implementation Guide

## Authentication System Architecture

### User Authentication Flow

1. **Login Process**
```python
def authenticate_user(email, password):
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        login_user(user)
        return True
    return False
```

**Security Measures:**
- Timing attack prevention using constant-time comparison
- Rate limiting on login attempts
- Session fixation protection
- Secure password storage using PBKDF2

### Password Management

1. **Password Hashing Configuration**
```python
HASH_CONFIG = {
    'method': 'pbkdf2:sha256',
    'salt_length': 16,
    'iterations': 260000
}
```

2. **Password Validation Rules**
```python
def validate_password(password):
    return (
        len(password) >= 8 and        # Minimum length
        any(c.isupper() for c in password) and  # At least one uppercase
        any(c.islower() for c in password) and  # At least one lowercase
        any(c.isdigit() for c in password)      # At least one number
    )
```

## Session Management

### Session Configuration
```python
SESSION_CONFIG = {
    'PERMANENT_SESSION_LIFETIME': timedelta(hours=1),
    'SESSION_COOKIE_SECURE': True,
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
    'REMEMBER_COOKIE_DURATION': timedelta(days=30),
    'REMEMBER_COOKIE_SECURE': True,
    'REMEMBER_COOKIE_HTTPONLY': True
}
```

### Session Security Measures

1. **Session Validation**
```python
@app.before_request
def validate_session():
    if current_user.is_authenticated:
        # Check session age
        if 'last_active' not in session:
            logout_user()
            return redirect(url_for('login'))
        
        # Enforce maximum session age
        last_active = datetime.fromisoformat(session['last_active'])
        if datetime.now() - last_active > timedelta(hours=1):
            logout_user()
            return redirect(url_for('login'))
        
        # Update last active timestamp
        session['last_active'] = datetime.now().isoformat()
```

2. **Session Regeneration**
```python
def regenerate_session():
    # Store important session data
    temp_data = dict(session)
    
    # Clear session
    session.clear()
    
    # Generate new session
    session.regenerate()
    
    # Restore important data
    for key in ['_user_id', 'last_active']:
        if key in temp_data:
            session[key] = temp_data[key]
```

## Access Control

### Role-Based Access Control (RBAC)

1. **Role Definitions**
```python
class UserRole(enum.Enum):
    STUDENT = 'student'
    ADMIN = 'admin'

def get_user_permissions(role):
    permissions = {
        UserRole.STUDENT: [
            'take_quiz',
            'view_own_scores',
            'view_own_profile'
        ],
        UserRole.ADMIN: [
            'manage_quizzes',
            'manage_subjects',
            'view_all_scores',
            'manage_users'
        ]
    }
    return permissions.get(role, [])
```

2. **Permission Checking**
```python
def check_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
                
            user_perms = get_user_permissions(current_user.role)
            if permission not in user_perms:
                abort(403)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

## CSRF Protection

### Token Generation and Validation

1. **Token Generation**
```python
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']
```

2. **Token Validation**
```python
def validate_csrf_token(token):
    expected_token = session.pop('_csrf_token', None)
    if not expected_token:
        return False
    return hmac.compare_digest(expected_token, token)
```

### CSRF Middleware
```python
class CSRFProtection:
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        request = Request(environ)
        
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            token = request.form.get('_csrf_token')
            if not token or not validate_csrf_token(token):
                response = Response('CSRF token missing or invalid', status=403)
                return response(environ, start_response)
        
        return self.app(environ, start_response)
```

## XSS Prevention

### Input Sanitization

1. **HTML Sanitization**
```python
def sanitize_html(content):
    allowed_tags = ['p', 'b', 'i', 'u', 'em', 'strong']
    allowed_attrs = {}
    
    return bleach.clean(
        content,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True
    )
```

2. **Form Data Sanitization**
```python
def sanitize_form_data(form_data):
    sanitized = {}
    for key, value in form_data.items():
        if isinstance(value, str):
            # Remove potential script injections
            value = re.sub(r'<script.*?>.*?</script>', '', value, flags=re.I|re.S)
            # Remove potential inline JavaScript
            value = re.sub(r'javascript:', '', value, flags=re.I)
            # Remove potential base64 encoded content
            value = re.sub(r'data:', '', value, flags=re.I)
        sanitized[key] = value
    return sanitized
```

## SQL Injection Prevention

### Query Parameters

1. **Safe Query Construction**
```python
def get_user_scores(user_id):
    return db.session.execute(
        text('SELECT * FROM score WHERE user_id = :user_id'),
        {'user_id': user_id}
    )
```

2. **ORM Usage**
```python
def get_quiz_questions(quiz_id):
    return Question.query.filter_by(quiz_id=quiz_id).all()
```

## Security Headers

### Header Configuration
```python
SECURITY_HEADERS = {
    'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';",
    'X-Frame-Options': 'SAMEORIGIN',
    'X-Content-Type-Options': 'nosniff',
    'X-XSS-Protection': '1; mode=block',
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'Referrer-Policy': 'strict-origin-when-cross-origin'
}
```

### Header Middleware
```python
@app.after_request
def add_security_headers(response):
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response
```

## Error Handling and Logging

### Error Logging
```python
def setup_security_logging():
    logger = logging.getLogger('security')
    handler = RotatingFileHandler(
        'logs/security.log',
        maxBytes=10000000,
        backupCount=5
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
    return logger

def log_security_event(event_type, details, severity='INFO'):
    logger = logging.getLogger('security')
    log_data = {
        'event_type': event_type,
        'timestamp': datetime.now().isoformat(),
        'details': details,
        'user_id': current_user.id if current_user.is_authenticated else None,
        'ip_address': request.remote_addr
    }
    if severity == 'INFO':
        logger.info(json.dumps(log_data))
    elif severity == 'WARNING':
        logger.warning(json.dumps(log_data))
    elif severity == 'ERROR':
        logger.error(json.dumps(log_data))
```

## Security Monitoring

### Activity Monitoring
```python
def monitor_suspicious_activity():
    failed_attempts = cache.get('failed_login_attempts') or {}
    ip_address = request.remote_addr
    
    if ip_address in failed_attempts:
        if failed_attempts[ip_address]['count'] >= 5:
            if datetime.now() - failed_attempts[ip_address]['first_attempt'] < timedelta(minutes=15):
                return True  # Block access
    
    return False  # Allow access
```

### Audit Logging
```python
def audit_log(action, resource_type, resource_id, status):
    audit_entry = AuditLog(
        user_id=current_user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(audit_entry)
    db.session.commit()
```

This documentation provides a comprehensive overview of the security implementation in the Quiz Master application, covering authentication, session management, access control, and various security measures to protect against common web vulnerabilities.