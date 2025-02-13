from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import re
from typing import Dict, List, Optional
import time
import os

class VideoService:
    def __init__(self):
        self.max_retries = 3
        self.retry_delay = 2  # seconds between retries

    def get_transcript(self, video_url: str) -> Dict[str, any]:
        """Get transcript from YouTube video with retry logic"""
        video_id = self._extract_video_id(video_url)
        if not video_id:
            raise ValueError("Could not extract video ID from URL")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                if not transcript_list:
                    raise ValueError("No transcript available")

                # Process transcript
                full_text = ""
                timestamps = []
                current_segment = {"text": "", "start": 0}
                
                for i, entry in enumerate(transcript_list):
                    text = entry.get('text', '').strip()
                    if not text:
                        continue

                    # Add to full text with proper spacing
                    if full_text and not full_text.endswith(('.', '!', '?')):
                        full_text += " "
                    full_text += text

                    # Handle timestamp segments (every ~2 minutes or on major punctuation)
                    current_segment["text"] += f" {text}"
                    if (i > 0 and i % 12 == 0) or any(text.endswith(p) for p in ['.', '!', '?']):
                        if len(current_segment["text"].strip()) > 50:  # Minimum segment length
                            timestamps.append({
                                "text": current_segment["text"].strip(),
                                "start": current_segment["start"]
                            })
                            current_segment = {"text": "", "start": entry.get('start', 0)}

                # Add final segment if not empty
                if current_segment["text"].strip():
                    timestamps.append({
                        "text": current_segment["text"].strip(),
                        "start": current_segment["start"]
                    })

                return {
                    'success': True,
                    'video_id': video_id,
                    'full_text': full_text.strip(),
                    'timestamps': timestamps
                }

            except Exception as e:
                last_error = str(e)
                print(f"Attempt {attempt + 1} failed: {last_error}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                continue

        raise ValueError(f"Failed to get transcript after {self.max_retries} attempts: {last_error}")

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL with enhanced validation"""
        try:
            # Handle different URL formats
            if 'youtu.be' in url:
                return url.split('/')[-1].split('?')[0]
            
            parsed_url = urlparse(url)
            if 'youtube.com' in parsed_url.netloc:
                if '/watch' in url:
                    return parse_qs(parsed_url.query).get('v', [None])[0]
                elif '/embed/' in url:
                    return parsed_url.path.split('/')[-1]
                elif '/v/' in url:
                    return parsed_url.path.split('/')[-1]

            # Attempt direct ID extraction if it matches format
            if re.match(r'^[A-Za-z0-9_-]{11}$', url):
                return url

            return None

        except Exception as e:
            print(f"Error extracting video ID: {str(e)}")
            return None

    def validate_video_url(self, url: str) -> bool:
        """Validate YouTube URL format and accessibility"""
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return False

            # Try to fetch transcript to verify accessibility
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            return bool(transcript_list)

        except Exception as e:
            print(f"URL validation error: {str(e)}")
            return False

    def get_embed_url(self, url):
        """Convert YouTube URL to embed URL"""
        video_id = self._extract_video_id(url)
        return f'https://www.youtube.com/embed/{video_id}'

    def create_player_html(self, url):
        """Create responsive YouTube player HTML"""
        embed_url = self.get_embed_url(url)
        return f'''
        <div class="ratio ratio-16x9">
            <iframe src="{embed_url}" 
                    title="YouTube video player" 
                    frameborder="0" 
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                    allowfullscreen>
            </iframe>
        </div>
        '''