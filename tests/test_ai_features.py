import unittest
from app import create_app, db
from app.models import Lecture, LectureSummary, LectureFlashcard, LectureNote
from services.ai_service import LectureAIService
import os
import tempfile

class TestAIFeatures(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app()
        self.app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
    
    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_summary_generation(self):
        with self.app.app_context():
            ai_service = LectureAIService()
            content = "Test lecture content about Python programming. Python is a high-level programming language."
            summary = ai_service.generate_summary(content)
            self.assertIsNotNone(summary)
            self.assertIsInstance(summary, str)
            self.assertTrue(len(summary) > 0)
    
    def test_flashcard_generation(self):
        with self.app.app_context():
            ai_service = LectureAIService()
            content = "Python is a programming language. It uses indentation for code blocks."
            flashcards = ai_service.generate_flashcards(content)
            self.assertIsNotNone(flashcards)
            self.assertIsInstance(flashcards, list)
            self.assertTrue(len(flashcards) > 0)
            for card in flashcards:
                self.assertIn('front', card)
                self.assertIn('back', card)
    
    def test_notes_generation(self):
        with self.app.app_context():
            ai_service = LectureAIService()
            content = "Python functions are defined using the def keyword. Functions can take parameters."
            notes = ai_service.generate_notes(content)
            self.assertIsNotNone(notes)
            self.assertIsInstance(notes, str)
            self.assertTrue(len(notes) > 0)
    
    def test_quiz_generation(self):
        with self.app.app_context():
            ai_service = LectureAIService()
            content = "Python has several data types including strings, integers, and lists."
            questions = ai_service.generate_quiz(content, num_questions=5)
            self.assertIsNotNone(questions)
            self.assertIsInstance(questions, list)
            self.assertEqual(len(questions), 5)
            for q in questions:
                self.assertIn('question_statement', q)
                self.assertIn('options', q)
                self.assertEqual(len(q['options']), 4)
                self.assertIn('correct_option', q)
    
    def test_content_regeneration(self):
        with self.app.app_context():
            lecture = Lecture(
                subject_id=1,
                title="Test Lecture",
                content="Test content for regeneration"
            )
            db.session.add(lecture)
            db.session.commit()
            
            # Test summary regeneration
            ai_service = LectureAIService()
            summary_content = ai_service.generate_summary(lecture.content)
            summary = LectureSummary(lecture_id=lecture.id, content=summary_content)
            db.session.add(summary)
            db.session.commit()
            
            self.assertIsNotNone(LectureSummary.query.filter_by(lecture_id=lecture.id).first())
            
            # Test flashcard regeneration
            flashcards = ai_service.generate_flashcards(lecture.content)
            for card in flashcards:
                flashcard = LectureFlashcard(
                    lecture_id=lecture.id,
                    front=card['front'],
                    back=card['back']
                )
                db.session.add(flashcard)
            db.session.commit()
            
            self.assertTrue(len(LectureFlashcard.query.filter_by(lecture_id=lecture.id).all()) > 0)
    
    def test_markdown_formatting(self):
        with self.app.app_context():
            ai_service = LectureAIService()
            content = "# Test Header\n## Subheader\n- List item 1\n- List item 2"
            formatted_content = ai_service._format_markdown(content)
            self.assertIn('<h1>', formatted_content)
            self.assertIn('<h2>', formatted_content)
            self.assertIn('<ul>', formatted_content)
            self.assertIn('<li>', formatted_content)

if __name__ == '__main__':
    unittest.main()