import os
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Dict, List, Optional

class QuizService:
    def __init__(self, ai_service=None):
        # Load environment variables from .env file
        load_dotenv()
        self.api_key = os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self.ai_service = ai_service

    def generate_quiz(self, content: str, num_questions: int = 10) -> dict:
        """Generate a quiz with the given number of questions"""
        try:
            if not self.ai_service:
                return {
                    'success': False,
                    'error': 'AI service not configured'
                }

            if not content or not content.strip():
                return {
                    'success': False,
                    'error': 'No content provided for quiz generation'
                }

            if not 5 <= num_questions <= 50:
                return {
                    'success': False,
                    'error': 'Number of questions must be between 5 and 50'
                }

            # Use AI service with retries
            max_retries = 2
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    questions = self.ai_service.generate_quiz(content, num_questions)
                    if questions and len(questions) == num_questions:
                        # Validate each question's format
                        valid_questions = []
                        for q in questions:
                            if self._validate_question(q):
                                valid_questions.append({
                                    'question_statement': q['question_statement'],
                                    'options': q['options'],
                                    'correct_option': q['correct_option']
                                })

                        if len(valid_questions) == num_questions:
                            return {
                                'success': True,
                                'questions': valid_questions
                            }

                    last_error = f"Generated {len(questions)} valid questions, expected {num_questions}"
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        continue
                    break

            return {
                'success': False,
                'error': f'Failed to generate valid quiz after {max_retries} attempts: {last_error}'
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Quiz generation error: {str(e)}'
            }

    def _validate_question(self, question: dict) -> bool:
        """Validate a single question format"""
        try:
            # Check required fields
            if not all(key in question for key in ['question_statement', 'options', 'correct_option']):
                return False

            # Validate question statement
            if not isinstance(question['question_statement'], str) or len(question['question_statement'].strip()) < 10:
                return False

            # Validate options
            if not isinstance(question['options'], list) or len(question['options']) != 4:
                return False

            # Validate each option is unique and non-empty
            options_set = set()
            for opt in question['options']:
                if not isinstance(opt, str) or len(opt.strip()) < 1:
                    return False
                opt_clean = opt.strip().lower()
                if opt_clean in options_set:
                    return False
                options_set.add(opt_clean)

            # Validate correct_option
            if not isinstance(question['correct_option'], int) or not 1 <= question['correct_option'] <= 4:
                return False

            return True

        except Exception:
            return False

    def grade_quiz(self, submitted_answers: list, correct_answers: list) -> dict:
        """Grade a quiz submission"""
        if len(submitted_answers) != len(correct_answers):
            return {
                'success': False,
                'error': 'Number of submitted answers does not match number of questions'
            }

        correct_count = 0
        feedback = []

        for i, (submitted, correct) in enumerate(zip(submitted_answers, correct_answers)):
            is_correct = submitted == correct['correct_option']
            if is_correct:
                correct_count += 1

            feedback.append({
                'question_number': i + 1,
                'is_correct': is_correct,
                'submitted_answer': submitted,
                'correct_answer': correct['correct_option'],
                'correct_option_text': correct['options'][correct['correct_option'] - 1]
            })

        return {
            'success': True,
            'total_questions': len(submitted_answers),
            'correct_count': correct_count,
            'feedback': feedback
        }

    def format_quiz_for_display(self, questions: list) -> list:
        """Format questions for display in templates"""
        formatted_questions = []
        for i, q in enumerate(questions, 1):
            formatted_questions.append({
                'number': i,
                'statement': q['question_statement'],
                'options': [
                    {'number': j + 1, 'text': opt}
                    for j, opt in enumerate(q['options'])
                ],
                'correct_option': q['correct_option']
            })
        return formatted_questions