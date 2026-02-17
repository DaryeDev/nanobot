"""Voice transcription provider using Groq and Google (Chromium)."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


class GroqTranscriptionProvider:
    """
    Voice transcription provider using Groq's Whisper API.
    
    Groq offers extremely fast transcription with a generous free tier.
    """
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    async def transcribe(self, file_path: str | Path) -> str:
        """
        Transcribe an audio file using Groq.
        
        Args:
            file_path: Path to the audio file.
            
        Returns:
            Transcribed text.
        """
        if not self.api_key:
            logger.warning("Groq API key not configured for transcription")
            return ""
        
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return ""
        
        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, "whisper-large-v3"),
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                    }
                    
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        files=files,
                        timeout=60.0
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")
                    
        except Exception as e:
            logger.error(f"Groq transcription error: {e}")
            return ""


class GoogleTranscriptionProvider:
    """
    Voice transcription provider using Google's Speech API (Chromium endpoint).
    """
    
    def __init__(self, lang: str = "es-ES"):
        # Default key from the script if not provided
        self.api_key = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
        self.lang = lang
        self.max_duration = 15
        self.overlap = 2
        self.api_url = "https://www.google.com/speech-api/v2/recognize"

    async def _get_duration(self, audio_path: str | Path) -> float:
        try:
            # Run ffprobe in a subprocess
            process = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                return 0.0
            return float(stdout.decode().strip())
        except Exception as e:
            logger.error(f"Error getting duration: {e}")
            return 0.0

    async def _convert_to_pcm(self, input_path: str | Path, output_path: str | Path):
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', str(input_path),
            '-f', 's16le', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode != 0:
            raise Exception("FFmpeg conversion failed")

    async def _extract_segment(self, input_path: str | Path, output_path: str | Path, start: float, duration: float):
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-ss', str(start), '-t', str(duration),
            '-i', str(input_path), '-c', 'copy', str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode != 0:
            raise Exception("FFmpeg segment extraction failed")

    async def _transcribe_file_content(self, audio_path: str | Path) -> str:
        pcm_path = str(audio_path) + ".raw"
        try:
            await self._convert_to_pcm(audio_path, pcm_path)
            
            if not os.path.exists(pcm_path):
                return ""

            async with httpx.AsyncClient() as client:
                with open(pcm_path, "rb") as f:
                    audio_data = f.read()

                url = f"{self.api_url}?client=chromium&lang={self.lang}&key={self.api_key}"
                headers = {'Content-Type': 'audio/l16; rate=16000'}
                
                response = await client.post(url, content=audio_data, headers=headers, timeout=30.0)
                
                # Google API returns multiple JSON objects separated by newlines
                text_result = ""
                for line in response.text.split('\n'):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if "result" in data and len(data["result"]) > 0:
                            # Take the first alternative
                            text_result = data["result"][0]["alternative"][0]["transcript"]
                            if text_result:
                                return text_result
                    except json.JSONDecodeError:
                        continue
                return ""

        except Exception as e:
            logger.error(f"Google transcription error: {e}")
            return ""
        finally:
            if os.path.exists(pcm_path):
                try:
                    os.remove(pcm_path)
                except Exception:
                    pass

    async def transcribe(self, file_path: str | Path) -> str:
        """
        Transcribe an audio file using Google Speech API.
        Handles long files by splitting them into chunks.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return ""

        duration = await self._get_duration(path)
        
        if duration <= self.max_duration:
            return await self._transcribe_file_content(path)
        
        # Long audio logic
        full_transcript = []
        start = 0.0
        
        while start < duration:
            seg_duration = self.max_duration
            
            temp_segment = path.parent / f"{path.stem}_seg_{start}.ogg"
            try:
                await self._extract_segment(path, temp_segment, start, seg_duration)
                text = await self._transcribe_file_content(temp_segment)
                if text:
                    full_transcript.append(text)
            except Exception as e:
                logger.error(f"Error transcribing segment at {start}: {e}")
            finally:
                if temp_segment.exists():
                    try:
                        temp_segment.unlink()
                    except Exception:
                        pass
            
            start += (self.max_duration - self.overlap)
            
        return " ".join(full_transcript)
