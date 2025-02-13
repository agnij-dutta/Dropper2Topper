import os
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List, Dict, Optional
import re
import queue
from datetime import datetime, timedelta

class FlashcardService:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        self.api_key = os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self.min_content_length = 20
        self.max_retries = 2

    def generate_flashcards(self, content: str, max_cards: int = 10) -> Dict[str, any]:
        """Generate flashcards with validation and error handling"""
        if not content or len(content.strip()) < self.min_content_length:
            return {
                'success': False,
                'error': 'Content too short for flashcard generation'
            }

        for attempt in range(self.max_retries):
            try:
                # Clean content
                cleaned_content = self._clean_content(content)
                
                # Generate flashcards
                prompt = """Create educational flashcards from the content.
                Make exactly {num_cards} flashcards.
                Mix these types:
                1. Term/Definition
                2. Concept/Example
                3. Problem/Solution
                
                Format each card exactly as:
                Q: (question or concept)
                A: (answer or explanation)
                
                Keep answers clear and concise.
                
                Content: {content}""".format(
                    num_cards=max_cards,
                    content=cleaned_content
                )

                response = self.model.generate_content(prompt)
                if not response or not response.text:
                    continue

                # Parse and validate flashcards
                flashcards = self._parse_response(response.text)
                if not flashcards:
                    continue

                # Clean and validate each card
                valid_cards = []
                for card in flashcards:
                    if self._validate_flashcard(card):
                        cleaned = self._clean_flashcard(card)
                        if cleaned:
                            valid_cards.append(cleaned)

                # Ensure we have enough valid cards
                if len(valid_cards) >= max_cards * 0.8:  # Allow for some missing cards
                    return {
                        'success': True,
                        'flashcards': valid_cards[:max_cards]  # Limit to requested number
                    }

            except Exception as e:
                print(f"Error in flashcard generation attempt {attempt + 1}: {str(e)}")
                if attempt == self.max_retries - 1:
                    return {
                        'success': False,
                        'error': f'Flashcard generation failed: {str(e)}'
                    }

        return {
            'success': False,
            'error': 'Failed to generate enough valid flashcards'
        }

    def _clean_content(self, content: str) -> str:
        """Clean content for AI processing"""
        content = ' '.join(content.split())  # Normalize whitespace
        content = re.sub(r'[^\w\s.,!?-]', '', content)  # Remove special chars
        return content[:4000]  # Limit length for API

    def _parse_response(self, response: str) -> List[Dict]:
        """Parse the AI response into flashcard objects"""
        flashcards = []
        current_card = {}
        
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('Q:'):
                if current_card.get('front'):  # Save previous card
                    flashcards.append(current_card)
                    current_card = {}
                current_card['front'] = line[2:].strip()
            elif line.startswith('A:') and current_card.get('front'):
                current_card['back'] = line[2:].strip()
                
        # Add the last card if complete
        if current_card.get('front') and current_card.get('back'):
            flashcards.append(current_card)
            
        return flashcards

    def _validate_flashcard(self, card: Dict) -> bool:
        """Validate a single flashcard"""
        try:
            if not all(key in card for key in ['front', 'back']):
                return False

            front = str(card['front']).strip()
            back = str(card['back']).strip()

            if not front or not back:
                return False

            if len(front) < 5 or len(back) < 5:
                return False

            if len(front) > 200 or len(back) > 500:
                return False

            if front.lower() == back.lower():
                return False

            return True
        except Exception:
            return False

    def _clean_flashcard(self, card: Dict) -> Optional[Dict]:
        """Clean and format flashcard content"""
        try:
            front = re.sub(r'[*_`#]', '', card['front'])
            back = re.sub(r'[*_`#]', '', card['back'])

            front = ' '.join(front.split())
            back = ' '.join(back.split())

            front = front[0].upper() + front[1:] if front else front
            back = back[0].upper() + back[1:] if back else back

            if any(front.lower().startswith(w) for w in ['what', 'when', 'where', 'who', 'why', 'how']):
                if not front.endswith('?'):
                    front += '?'

            return {
                'front': front,
                'back': back
            }
        except Exception:
            return None

    def format_for_display(self, flashcards: List[Dict]) -> List[Dict]:
        """Format flashcards for template display"""
        formatted_cards = []
        for i, card in enumerate(flashcards, 1):
            formatted_cards.append({
                'id': i,
                'front': card['front'],
                'back': card['back']
            })
        return formatted_cards