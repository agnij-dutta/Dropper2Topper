from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
from datetime import datetime
from app.thread_monitor import thread_monitor

db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_object=None):
    # Load environment variables first
    load_dotenv()
    
    app = Flask(__name__, template_folder='../templates')
    
    # Configure app
    if config_object:
        app.config.from_object(config_object)
    else:
        # Default configuration
        app.config['SECRET_KEY'] = os.urandom(24)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz_master.db'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    
    @app.template_filter('strftime')
    def strftime_filter(date, fmt='%Y-%m-%d'):
        if date is None:
            return ''
        return date.strftime(fmt)

    with app.app_context():
        from app import routes, models
        db.create_all()
        
        # Create default admin if it doesn't exist
        from app.models import Admin
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
        
        # Start thread monitor
        thread_monitor.start_monitoring()
        
        # Register cleanup on app shutdown
        @app.teardown_appcontext
        def shutdown_thread_monitor(exception=None):
            thread_monitor.stop_monitoring()
    
    return app
