import os
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Dict, List, Optional
import re
import html
import markdown
from .video_service import VideoService

class LectureAIService:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        self.api_key = os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        self.video_service = VideoService()
        self._error_counts = {
            'quiz': 0,
            'summary': 0,
            'flashcards': 0,
            'notes': 0
        }
        self._max_retries = 3
        
    def _log_error(self, component: str, error: str):
        """Log errors for monitoring"""
        print(f"[AI Service Error] {component}: {error}")
        self._error_counts[component] = self._error_counts.get(component, 0) + 1
        
    def _should_retry(self, component: str) -> bool:
        """Determine if we should retry based on error count"""
        return self._error_counts.get(component, 0) < self._max_retries

    def _clean_content(self, content: str) -> str:
        """Clean and prepare content for AI processing"""
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)
        # Remove special characters but keep basic punctuation
        content = re.sub(r'[^\w\s.,!?-]', '', content)
        # Truncate to avoid token limits while preserving meaning
        return content[:4000]

    def _format_markdown(self, content: str) -> str:
        """Convert markdown to HTML for better display"""
        # Convert markdown to HTML
        html_content = markdown.markdown(content)
        # Sanitize HTML to prevent XSS
        html_content = html.escape(html_content)
        # Convert escaped HTML tags back to actual tags
        html_content = re.sub(r'&lt;([/]?(?:p|h[1-6]|ul|ol|li|strong|em|code|pre))&gt;', r'<\1>', html_content)
        return html_content

    def process_video_content(self, video_url: str) -> Dict[str, any]:
        """Process a YouTube video URL and generate AI content from its transcript"""
        # Get transcript using VideoService
        transcript_data = self.video_service.get_transcript(video_url)
        transcript_text = transcript_data['full_text']
        
        # Generate all content types
        return {
            'summary': self.generate_summary(transcript_text),
            'flashcards': self.generate_flashcards(transcript_text),
            'notes': self.generate_notes(transcript_text),
            'quiz': self.generate_quiz(transcript_text),
            'video_id': transcript_data['video_id'],
            'timestamps': transcript_data['timestamps']  # Use timestamps from transcript
        }

    def generate_summary(self, content: str) -> str:
        cleaned_content = self._clean_content(content)
        prompt = """Create a comprehensive yet concise summary of this content.
        Use markdown formatting for better organization.
        Include:
        # Main Topic
        - Key points and core ideas
        - Important relationships

        ## Key Concepts
        - Definitions and explanations
        - Examples where relevant

        ## Applications
        - Real-world examples
        - Practical use cases

        Keep it informative but easy to understand.
        
        Content: {content}"""
        
        try:
            response = self.model.generate_content(prompt.format(content=cleaned_content))
            return self._format_markdown(response.text)
        except Exception as e:
            print(f"Error generating summary: {str(e)}")
            return "Error generating summary. Please try again."

    def generate_flashcards(self, content: str) -> List[Dict[str, str]]:
        cleaned_content = self._clean_content(content)
        prompt = """Create educational flashcards covering key concepts.
        Mix these types of cards:
        1. Term/Definition
        2. Concept/Example
        3. Problem/Solution
        4. Compare/Contrast
        5. Cause/Effect
        
        Format each as:
        CARD:
        Front: (clear question/concept)
        Back: (comprehensive answer/explanation)
        
        Create 10 varied cards that progress from basic to complex.
        
        Content: {content}"""
        
        try:
            response = self.model.generate_content(prompt.format(content=cleaned_content))
            flashcards = []
            current_card = {}
            
            for line in response.text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('Front:'):
                    if current_card.get('front'):
                        flashcards.append(current_card)
                        current_card = {}
                    current_card['front'] = self._format_markdown(line[6:].strip())
                elif line.startswith('Back:'):
                    current_card['back'] = self._format_markdown(line[5:].strip())
                    
            if current_card.get('front') and current_card.get('back'):
                flashcards.append(current_card)
                
            return flashcards
        except Exception as e:
            print(f"Error generating flashcards: {str(e)}")
            return []

    def generate_timestamps(self, content: str) -> List[Dict[str, any]]:
        cleaned_content = self._clean_content(content)
        prompt = """Create logical video timestamps for this content.
        For each major topic or section:
        - Create a clear, descriptive title
        - Estimate appropriate timestamp in minutes
        
        Format as:
        TIMESTAMP:
        Title: (clear section title)
        Time: (minutes into video)
        
        Space timestamps naturally throughout content.
        Start from 0 and increment logically.
        
        Content: {content}"""
        
        try:
            response = self.model.generate_content(prompt.format(content=cleaned_content))
            timestamps = []
            current_timestamp = {}
            
            for line in response.text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('Title:'):
                    current_timestamp['title'] = line[6:].strip()
                elif line.startswith('Time:'):
                    try:
                        minutes = int(line[5:].strip().split()[0])
                        current_timestamp['timestamp'] = minutes * 60
                        if 'title' in current_timestamp:
                            timestamps.append(current_timestamp.copy())
                            current_timestamp = {}
                    except (ValueError, IndexError):
                        continue
            
            return timestamps
        except Exception as e:
            print(f"Error generating timestamps: {str(e)}")
            return []

    def generate_notes(self, content: str) -> str:
        cleaned_content = self._clean_content(content)
        prompt = """Create detailed study notes using markdown formatting.
        Structure as:
        # Overview
        - Main topic introduction
        - Learning objectives
        
        ## Key Concepts
        - Each concept with definition
        - Examples and explanations
        
        ## Important Relationships
        - How concepts connect
        - Cause and effect
        
        ## Applications
        - Real-world examples
        - Practice scenarios
        
        ## Summary
        - Key takeaways
        - Review points
        
        Use proper markdown for:
        - Headers (# ## ###)
        - Lists (- or 1.)
        - Emphasis (*italic* or **bold**)
        - Code blocks (```)
        
        Content: {content}"""
        
        try:
            response = self.model.generate_content(prompt.format(content=cleaned_content))
            return self._format_markdown(response.text)
        except Exception as e:
            print(f"Error generating notes: {str(e)}")
            return "Error generating study notes. Please try again."

    def generate_quiz(self, content: str, num_questions: int = 10) -> List[Dict[str, any]]:
        """Generate quiz questions with improved error handling and retries"""
        self._error_counts['quiz'] = 0  # Reset error count for new attempt
        
        while self._should_retry('quiz'):
            try:
                cleaned_content = self._clean_content(content)
                if not cleaned_content:
                    self._log_error('quiz', "Content cleaning failed")
                    return []

                prompt = f"""Based on this content, generate {num_questions} multiple-choice questions.
                Each question must:
                - Test understanding of key concepts
                - Have exactly 4 unique answer options
                - Have one clear correct answer
                - Use simple, clear language
                
                Format each question exactly like this:
                
                Q1. [Clear question text]
                A) [First option]
                B) [Second option]
                C) [Third option]
                D) [Fourth option]
                Correct Answer: [A/B/C/D]

                [Leave a blank line between questions]
                
                Content to generate questions about:
                {cleaned_content}"""

                try:
                    response = self.model.generate_content(prompt)
                    if not response or not response.text:
                        self._log_error('quiz', "No response from model")
                        continue

                    questions = self._parse_quiz_response(response.text)
                    if not questions:
                        self._log_error('quiz', "Failed to parse questions")
                        continue

                    # Validate each question
                    validated_questions = []
                    for q in questions:
                        if self._validate_quiz_question(q):
                            validated_questions.append(q)
                        else:
                            self._log_error('quiz', f"Invalid question format: {q}")

                    # Check if we have enough valid questions
                    if len(validated_questions) >= num_questions:
                        return validated_questions[:num_questions]
                    else:
                        self._log_error('quiz', f"Only generated {len(validated_questions)} valid questions, needed {num_questions}")
                        continue

                except Exception as parse_error:
                    self._log_error('quiz', f"Parse error: {str(parse_error)}")
                    continue

            except Exception as e:
                self._log_error('quiz', f"Generation error: {str(e)}")
                if not self._should_retry('quiz'):
                    break
                continue

        print(f"[AI Service] Quiz generation failed after {self._error_counts['quiz']} attempts")
        return []

    def _validate_quiz_question(self, question: Dict) -> bool:
        """Validate quiz question with detailed error logging"""
        try:
            if not isinstance(question, dict):
                self._log_error('quiz', "Question is not a dictionary")
                return False

            # Check required fields
            required_fields = ['question_statement', 'options', 'correct_option']
            missing_fields = [field for field in required_fields if field not in question]
            if missing_fields:
                self._log_error('quiz', f"Missing fields: {missing_fields}")
                return False

            # Validate question statement
            if not isinstance(question['question_statement'], str):
                self._log_error('quiz', "Question statement is not a string")
                return False
            
            if len(question['question_statement'].strip()) < 10:
                self._log_error('quiz', "Question statement too short")
                return False

            # Validate options
            if not isinstance(question['options'], list):
                self._log_error('quiz', "Options is not a list")
                return False
            
            if len(question['options']) != 4:
                self._log_error('quiz', f"Wrong number of options: {len(question['options'])}")
                return False

            # Check for duplicate options
            option_set = set()
            for i, opt in enumerate(question['options']):
                if not isinstance(opt, str) or len(opt.strip()) < 1:
                    self._log_error('quiz', f"Invalid option {i+1}")
                    return False
                
                clean_opt = opt.strip().lower()
                if clean_opt in option_set:
                    self._log_error('quiz', f"Duplicate option: {opt}")
                    return False
                option_set.add(clean_opt)

            # Validate correct_option
            if not isinstance(question['correct_option'], int):
                self._log_error('quiz', "Correct option is not an integer")
                return False
            
            if not 1 <= question['correct_option'] <= 4:
                self._log_error('quiz', f"Invalid correct option value: {question['correct_option']}")
                return False

            return True

        except Exception as e:
            self._log_error('quiz', f"Validation error: {str(e)}")
            return False

    def _parse_quiz_response(self, response: str) -> List[Dict[str, any]]:
        """Parse quiz questions with improved pattern matching"""
        try:
            questions = []
            current_question = None
            
            # Split into lines and clean up
            lines = [line.strip() for line in response.split('\n') if line.strip()]
            
            for line in lines:
                # Match question patterns
                q_match = re.match(r'^(?:Q(?:uestion)?\s*)?(\d+)[\.:)\s]\s*(.+)', line, re.IGNORECASE)
                if q_match:
                    # Save previous question if complete
                    if current_question and len(current_question['options']) == 4 and current_question['correct_option']:
                        questions.append(current_question)
                    
                    current_question = {
                        'question_statement': q_match.group(2).strip(),
                        'options': [],
                        'correct_option': None
                    }
                    continue

                # Match option patterns
                opt_match = re.match(r'^[(\s]*([A-D])[\.:)\s]\s*(.+)', line, re.IGNORECASE)
                if current_question and opt_match:
                    option_letter = opt_match.group(1).upper()
                    option_text = opt_match.group(2).strip()
                    
                    # Map A-D to positions 0-3
                    option_index = ord(option_letter) - ord('A')
                    
                    # Extend list if needed
                    while len(current_question['options']) <= option_index:
                        current_question['options'].append('')
                    
                    current_question['options'][option_index] = option_text
                    continue

                # Match correct answer patterns
                ans_patterns = [
                    r'(?:correct\s*(?:answer|option)|answer|correct|solution)\s*:\s*([A-D])',
                    r'^([A-D])\s*(?:is\s*(?:correct|the\s*answer))$',
                    r'^\(([A-D])\)\s*(?:is\s*(?:correct|the\s*answer))$'
                ]
                
                for pattern in ans_patterns:
                    ans_match = re.search(pattern, line, re.IGNORECASE)
                    if current_question and ans_match:
                        answer_letter = ans_match.group(1).upper()
                        current_question['correct_option'] = ord(answer_letter) - ord('A') + 1
                        break

            # Add the last question if complete
            if current_question and len(current_question['options']) == 4 and current_question['correct_option']:
                questions.append(current_question)

            # Post-process and validate questions
            processed_questions = []
            for q in questions:
                # Clean question and options
                q['question_statement'] = self._clean_question_text(q['question_statement'])
                q['options'] = [self._clean_option_text(opt) for opt in q['options']]
                
                # Skip questions with empty/missing options
                if '' in q['options']:
                    self._log_error('quiz', f"Missing options in question: {q['question_statement']}")
                    continue

                # Verify no duplicate options after cleaning
                if len(set(q['options'])) == 4:
                    processed_questions.append(q)
                else:
                    self._log_error('quiz', f"Duplicate options after cleaning: {q['options']}")

            return processed_questions

        except Exception as e:
            self._log_error('quiz', f"Parse error: {str(e)}")
            return []

    def _clean_question_text(self, text: str) -> str:
        """Clean up question text"""
        # Remove any leading question markers
        text = re.sub(r'^Q(?:uestion)?\s*\d+[\.:\)]\s*', '', text)
        # Remove any markdown or extra formatting
        text = re.sub(r'[*_`]', '', text)
        # Ensure it ends with a question mark if it doesn't
        if not text.strip().endswith('?'):
            text = text.strip() + '?'
        return text.strip()

    def _clean_option_text(self, text: str) -> str:
        """Clean up option text"""
        # Remove any option markers
        text = re.sub(r'^[A-D][\.:\)]\s*', '', text)
        # Remove any markdown or extra formatting
        text = re.sub(r'[*_`]', '', text)
        return text.strip()