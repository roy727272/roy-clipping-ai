import os
import re
import json
import shutil
import subprocess
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

# Resolve FFmpeg and FFprobe binary paths
def get_ffmpeg_paths():
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    
    # Check winget packages directory if not found in PATH
    winget_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not ffmpeg_bin and winget_dir.exists():
        found = list(winget_dir.glob("**/ffmpeg.exe"))
        if found:
            ffmpeg_bin = str(found[0])
            probe = found[0].parent / "ffprobe.exe"
            if probe.exists():
                ffprobe_bin = str(probe)
                
    return ffmpeg_bin or "ffmpeg", ffprobe_bin or "ffprobe"

FFMPEG_PATH, FFPROBE_PATH = get_ffmpeg_paths()

# Ensure FFmpeg directory is added to system PATH so yt-dlp and child processes can find it
if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
    ffmpeg_dir = str(Path(FFMPEG_PATH).parent)
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir.lower() not in current_path.lower():
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path

# 6 Professional Subtitle Styles
SUBTITLE_STYLES = {
    "hormozi_yellow": {
        "name": "Alex Hormozi Yellow",
        "font": "Impact",
        "size": 66,
        "primary": "&H0000FFFF",  # Vibrant Bright Yellow
        "outline": "&H00000000",  # Pure Black Outline
        "border": 6,
        "shadow": 3,
        "bold": -1
    },
    "neon_cyan": {
        "name": "Neon Cyan Glow",
        "font": "Impact",
        "size": 64,
        "primary": "&H00FFFF00",  # Electric Cyan
        "outline": "&H00000000",
        "border": 6,
        "shadow": 4,
        "bold": -1
    },
    "mrbeast_green": {
        "name": "MrBeast Emerald",
        "font": "Impact",
        "size": 66,
        "primary": "&H0000FF55",  # Lime Emerald Green
        "outline": "&H00000000",
        "border": 7,
        "shadow": 4,
        "bold": -1
    },
    "clean_white": {
        "name": "Clean Minimal White",
        "font": "Arial Black",
        "size": 58,
        "primary": "&H00FFFFFF",  # Pure White
        "outline": "&H00202020",  # Charcoal Outline
        "border": 4,
        "shadow": 3,
        "bold": -1
    },
    "cyberpunk_pink": {
        "name": "Cyberpunk Hot Pink",
        "font": "Impact",
        "size": 64,
        "primary": "&H00D000FF",  # Magenta / Hot Pink
        "outline": "&H00000000",
        "border": 6,
        "shadow": 4,
        "bold": -1
    },
    "fire_orange": {
        "name": "Fiery Flame Orange",
        "font": "Impact",
        "size": 66,
        "primary": "&H000080FF",  # Sunset Flame Orange
        "outline": "&H00000000",
        "border": 6,
        "shadow": 4,
        "bold": -1
    }
}

def format_timestamp(seconds: float) -> str:
    """Convert seconds to ASS/SRT timestamp format H:MM:SS.cs"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    csecs = int(round((seconds - int(seconds)) * 100))
    return f"{hrs}:{mins:02d}:{secs:02d}.{csecs:02d}"

def extract_video_id(url: str) -> Optional[str]:
    """Extract 11-character YouTube video ID from various URL formats"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def fetch_youtube_metadata(url: str) -> Dict[str, Any]:
    """Get video title, thumbnail, duration and channel info without full download"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ffmpeg_location': FFMPEG_PATH,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb'],
            }
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "id": info.get("id"),
                "title": info.get("title", "YouTube Video"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader", "Unknown Channel"),
                "view_count": info.get("view_count", 0)
            }
    except Exception as e:
        print(f"fetch_youtube_metadata notice: {e}")
        vid_id = extract_video_id(url)
        return {
            "id": vid_id,
            "title": f"YouTube Video ({vid_id})",
            "duration": 600,
            "thumbnail": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg" if vid_id else None,
            "uploader": "YouTube Creator",
            "view_count": 0
        }

def fetch_transcript(video_id: str, video_url: str, caption_lang: str = "en") -> List[Dict[str, Any]]:
    """Fetch timestamped transcript. Prioritizes requested language, but always returns speech lines."""
    if caption_lang == "en":
        target_langs = ['en', 'en-US', 'en-GB', 'en-orig', 'en-IN']
    else:
        target_langs = ['hi', 'hi-Latn', 'en', 'en-US']

    # 1. Try YouTubeTranscriptApi
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        transcript = None
        try:
            transcript = transcript_list.find_transcript(target_langs)
        except Exception:
            # If English not directly available, check if translatable to English
            if caption_lang == "en":
                for t in transcript_list:
                    if getattr(t, "is_translatable", False):
                        try:
                            transcript = t.translate('en')
                            break
                        except Exception:
                            pass
            if not transcript:
                for t in transcript_list:
                    transcript = t
                    break
                
        if transcript:
            data = transcript.fetch()
            cleaned = []
            for item in data:
                text = item.text.replace('\n', ' ').strip()
                if text and text not in ["[संगीत]", "[Music]", "[Applause]", "[हंसी]"]:
                    cleaned.append({
                        "start": float(item.start),
                        "duration": float(item.duration),
                        "end": float(item.start + item.duration),
                        "text": text
                    })
            if cleaned:
                return cleaned
    except Exception as e:
        print(f"YouTubeTranscriptApi notice: {e}. Trying yt-dlp...")

    # 2. Try yt-dlp auto subtitles (YouTube's auto-generated tracks)
    temp_dir = Path("downloads") / f"sub_{video_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    sub_langs = ['en', 'en-US', 'en-orig', 'hi']
    ydl_opts = {
        'skip_download': True,
        'writeautomaticsub': True,
        'subtitleslangs': sub_langs,
        'subtitlesformat': 'json3',
        'outtmpl': str(temp_dir / 'sub.%(ext)s'),
        'quiet': True,
        'ffmpeg_location': FFMPEG_PATH,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb'],
            }
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            
        json_subs = list(temp_dir.glob("*.json3"))
        if json_subs:
            chosen_sub = json_subs[0]
            for s in json_subs:
                if ".en." in s.name:
                    chosen_sub = s
                    break

            with open(chosen_sub, "r", encoding="utf-8") as f:
                raw = json.load(f)
            events = raw.get("events", [])
            cleaned = []
            for ev in events:
                t_start = ev.get("tStartMs", 0) / 1000.0
                d_time = ev.get("dDurationMs", 0) / 1000.0
                segs = ev.get("segs", [])
                text = "".join(s.get("utf8", "") for s in segs).strip()
                if text and text not in ["\n", "[संगीत]", "[Music]"]:
                    cleaned.append({
                        "start": t_start,
                        "duration": d_time,
                        "end": t_start + d_time,
                        "text": text
                    })
            if cleaned:
                return cleaned
    except Exception as e:
        print(f"yt-dlp subtitle fallback notice: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return []

def analyze_viral_moments_gemini(
    transcript: List[Dict[str, Any]], 
    video_title: str, 
    api_key: str, 
    clip_count: int = 3,
    video_duration: float = 0.0
) -> List[Dict[str, Any]]:
    """Use Gemini AI to analyze transcript and extract highest viral potential moments with English subtitles"""
    try:
        clip_count = max(1, int(clip_count))
        from google import genai
        client = genai.Client(api_key=api_key)

        # Skip intro/stream loading (first 120s) if the video is long
        usable_transcript = transcript
        if transcript and (video_duration > 240 or transcript[-1]["end"] > 240):
            filtered = [item for item in transcript if item["start"] >= 120.0]
            if len(filtered) >= 15:
                usable_transcript = filtered

        # If transcript is very large, sample it uniformly across the video to fit context
        if len(usable_transcript) > 700:
            step = max(1, len(usable_transcript) // 700)
            sampled = usable_transcript[::step]
        else:
            sampled = usable_transcript

        transcript_sample = []
        for item in sampled:
            transcript_sample.append(f"[{item['start']:.1f}s - {item['end']:.1f}s]: {item['text']}")
        transcript_text = "\n".join(transcript_sample)

        prompt = f"""
You are an elite viral Shorts, Reels, and TikTok video editor (like Opus Clip / Neon Clipping AI).
Analyze this transcript from the video "{video_title}" and extract exactly {clip_count} TOP VIRAL short clips (each between 30 and 55 seconds duration).

CRITICAL RULES:
1. NEVER select segments from the starting intro, countdown, silence, stream waiting screen, or mic setup (the first 2-3 minutes are strictly excluded).
2. Find the highest-energy moments: hilarious reactions, intense clutch moments, shocking statements, heated arguments, surprising gameplay, or epic punchlines.
3. Distribute the clips across different key highlights of the video.
4. For EACH clip, generate:
   - "start": exact float start timestamp in seconds
   - "end": exact float end timestamp in seconds (duration between 30 and 55 seconds)
   - "title": punchy, high-CTR short title in English (max 7 words)
   - "virality_score": integer between 85 and 99 based on hook and retention strength
   - "viral_probability": integer between 85 and 99 (same as virality score)
   - "hook_score": integer between 88 and 99
   - "retention_score": integer between 80 and 97
   - "hook": the opening 1-sentence hook line in English that immediately grabs attention
   - "reason": why this clip has high viral potential on social media
   - "hashtags": array of 4-5 trending tags (e.g. ["#Shorts", "#Viral", "#Gaming", "#Trending"])
   - "best_time_to_post": peak posting time recommendation (e.g. "6:00 PM - 9:00 PM (Peak Traffic)")
   - "subtitles": array of 4 to 8 dialogue lines in punchy uppercase English with "start", "end", and "text" covering this clip. If the audio is in Hindi, translate and adapt into clean, modern, exciting English captions (e.g. "WHAT JUST HAPPENED?!", "BRO HE IS FLANKING FROM BEHIND!").

Transcript:
{transcript_text}

Respond STRICTLY with a valid JSON array of {clip_count} objects. No markdown code blocks, no other text.
"""
        models_to_try = ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"]
        raw_text = None
        last_err = None
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                raw_text = response.text.strip()
                break
            except Exception as e:
                last_err = e
                continue

        if not raw_text:
            raise RuntimeError(f"All Gemini models failed: {last_err}")

        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        clips = json.loads(raw_text)
        if not isinstance(clips, list):
            raise ValueError("Gemini did not return a JSON list")

        for idx, c in enumerate(clips, 1):
            c["seo_rank"] = idx
            if "viral_probability" not in c:
                c["viral_probability"] = c.get("virality_score", 90)
            if "hook_score" not in c:
                c["hook_score"] = min(99, c.get("virality_score", 90) + 2)
            if "retention_score" not in c:
                c["retention_score"] = max(80, c.get("virality_score", 90) - 3)
            if "hashtags" not in c or not c["hashtags"]:
                c["hashtags"] = ["#Shorts", "#Viral", "#Trending", "#RoyClipping", "#Reels"]
            if "best_time_to_post" not in c:
                c["best_time_to_post"] = "6:00 PM - 9:00 PM (Peak Traffic)"
            
        # If Gemini returned fewer clips than requested, supplement with heuristic
        if len(clips) < clip_count:
            extra = analyze_viral_moments_heuristic(transcript, clip_count - len(clips), video_duration)
            for ex in extra:
                overlap = any(not (ex["end"] <= c["start"] or ex["start"] >= c["end"]) for c in clips)
                if not overlap:
                    ex["seo_rank"] = len(clips) + 1
                    clips.append(ex)
                if len(clips) >= clip_count:
                    break

        return clips[:clip_count]
    except Exception as e:
        print(f"Gemini API analysis notice: {e}. Falling back to heuristic engine.")
        return analyze_viral_moments_heuristic(transcript, clip_count, video_duration)

def analyze_viral_moments_heuristic(
    transcript: List[Dict[str, Any]], 
    clip_count: int = 3,
    video_duration: float = 0.0
) -> List[Dict[str, Any]]:
    """Heuristic viral moment extractor that distributes clips across video, skipping intro fluff"""
    try:
        clip_count = max(1, int(clip_count))
    except Exception:
        clip_count = 3

    # Fallback duration if not provided
    if video_duration <= 0.0:
        if transcript:
            video_duration = transcript[-1]["end"]
        else:
            video_duration = 600.0

    # CASE 1: No transcript available (Video without captions)
    if not transcript:
        clips = []
        # Skip initial intro (first 120s if long video, else 10s)
        intro_offset = min(120.0, video_duration * 0.15) if video_duration > 180 else 5.0
        usable_span = max(60.0, (video_duration * 0.95) - intro_offset)
        step = usable_span / max(1, clip_count)

        for i in range(clip_count):
            start_t = intro_offset + (i * step) + (step * 0.1)
            duration = min(40.0, max(28.0, step * 0.7))
            end_t = min(video_duration, start_t + duration)
            if end_t <= start_t:
                end_t = start_t + 30.0

            score = max(82, 97 - (i * 2))
            clips.append({
                "start": round(start_t, 1),
                "end": round(end_t, 1),
                "title": f"Viral Highlight #{i+1}: Best Moment",
                "virality_score": score,
                "seo_rank": i + 1,
                "viral_probability": score,
                "hook_score": min(99, score + 2),
                "retention_score": max(80, score - 3),
                "hook": "Watch this insane moment right here!",
                "reason": "High-interest video segment with active audience pacing.",
                "hashtags": ["#Shorts", "#Viral", "#Trending", "#RoyClipping", "#Reels"],
                "best_time_to_post": "6:00 PM - 9:00 PM (Peak Traffic)"
            })
        return clips

    # CASE 2: Transcript is available
    viral_triggers = [
        "secret", "never", "why", "shocking", "best", "truth", "important",
        "remember", "wait", "money", "mistake", "hack", "problem", "solution",
        "bhai", "kya", "kaise", "kyun", "dekho", "sach", "raaz", "galti", "dhyan",
        "omg", "insane", "kill", "clutch", "headshot", "loot", "win", "lost", "fail"
    ]

    # Filter out intro items (first 100 seconds) if video has enough length
    usable_items = [x for x in transcript if x["start"] >= 100.0] if video_duration > 200 else transcript
    if not usable_items:
        usable_items = transcript

    candidates = []
    total_len = len(usable_items)
    step = max(1, total_len // (clip_count * 5))

    for i in range(0, total_len, step):
        start_item = usable_items[i]
        start_time = start_item["start"]
        
        segment_text = []
        end_time = start_time
        for j in range(i, total_len):
            item = usable_items[j]
            segment_text.append(item["text"])
            end_time = item["end"]
            duration = end_time - start_time
            if duration >= 35.0:
                break
                
        duration = end_time - start_time
        if 25.0 <= duration <= 60.0:
            full_text = " ".join(segment_text).lower()
            score = 78
            score += sum(3 for trigger in viral_triggers if trigger in full_text)
            score += full_text.count("?") * 4
            score += full_text.count("!") * 3
            score = min(98, score)
            
            first_sentence = segment_text[0] if segment_text else "Watch this moment..."
            candidates.append({
                "start": round(start_time, 1),
                "end": round(end_time, 1),
                "title": f"Highlight: {first_sentence[:32]}...",
                "virality_score": score,
                "hook": first_sentence[:60],
                "reason": "Dynamic speech tempo with viral engagement triggers.",
                "viral_probability": score,
                "hook_score": min(99, score + 2),
                "retention_score": max(80, score - 3),
                "hashtags": ["#Shorts", "#Viral", "#Trending", "#RoyClipping", "#Reels"],
                "best_time_to_post": "6:00 PM - 9:00 PM (Peak Traffic)"
            })
            
    candidates.sort(key=lambda x: x["virality_score"], reverse=True)
    selected = []
    for cand in candidates:
        overlap = any(not (cand["end"] <= s["start"] or cand["start"] >= s["end"]) for s in selected)
        if not overlap:
            selected.append(cand)
            if len(selected) >= clip_count:
                break
                
    if len(selected) < clip_count:
        for cand in candidates:
            if cand not in selected:
                selected.append(cand)
                if len(selected) >= clip_count:
                    break

    for idx, c in enumerate(selected, 1):
        c["seo_rank"] = idx
        if "viral_probability" not in c:
            c["viral_probability"] = c.get("virality_score", 88)
        if "hook_score" not in c:
            c["hook_score"] = min(99, c.get("virality_score", 88) + 2)
        if "retention_score" not in c:
            c["retention_score"] = max(80, c.get("virality_score", 88) - 3)
        if "hashtags" not in c or not c["hashtags"]:
            c["hashtags"] = ["#Shorts", "#Viral", "#Trending", "#RoyClipping", "#Reels"]
        if "best_time_to_post" not in c:
            c["best_time_to_post"] = "6:00 PM - 9:00 PM (Peak Traffic)"
        
    return selected[:clip_count]

def generate_neon_ass_subtitle(
    transcript: List[Dict[str, Any]], 
    clip_start: float, 
    clip_end: float, 
    output_path: str,
    style_name: str = "hormozi_yellow",
    clip_subtitles: Optional[List[Dict[str, Any]]] = None
):
    """
    Generate an ASS subtitle file styled with customizable text formats.
    Supports AI-generated English subtitles or source transcript lines.
    """
    style_cfg = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["hormozi_yellow"])
    
    font_name = style_cfg["font"]
    font_size = style_cfg["size"]
    primary_col = style_cfg["primary"]
    outline_col = style_cfg["outline"]
    border_width = style_cfg["border"]
    shadow_depth = style_cfg["shadow"]
    
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CustomMain,{font_name},{font_size},{primary_col},&H00FFFFFF,{outline_col},&H80000000,-1,0,0,0,100,100,2,0,1,{border_width},{shadow_depth},2,60,60,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    items_to_use = clip_subtitles if (clip_subtitles and len(clip_subtitles) > 0) else transcript
    clip_dur = max(1.0, clip_end - clip_start)

    for item in items_to_use:
        try:
            s_val = float(item["start"])
            e_val = float(item["end"])
        except Exception:
            continue

        # Detect if timestamps are relative (0 to duration) or absolute in video
        if e_val <= clip_dur and s_val >= 0.0 and clip_start > 25.0:
            rel_start = s_val
            rel_end = e_val
        else:
            if e_val < clip_start or s_val > clip_end:
                continue
            rel_start = max(0.0, s_val - clip_start)
            rel_end = min(clip_dur, e_val - clip_start)

        if rel_end - rel_start < 0.2:
            continue

        ass_start = format_timestamp(rel_start)
        ass_end = format_timestamp(rel_end)

        raw_text = str(item.get("text", "")).strip().upper()
        if not raw_text or raw_text in ["[MUSIC]", "[संगीत]"]:
            continue

        # Format into punchy 4-6 word lines for high-impact mobile reels
        words = raw_text.split()
        if len(words) > 6:
            mid = len(words) // 2
            text = " ".join(words[:mid]) + r"\N" + " ".join(words[mid:])
        else:
            text = " ".join(words)

        styled_text = f"{{\\an2\\bord{border_width}\\shad{shadow_depth}}}" + text
        events.append(f"Dialogue: 0,{ass_start},{ass_end},CustomMain,,0,0,0,,{styled_text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))

def download_video_segment(video_url: str, output_path: str, max_height: int = 1080) -> str:
    """Download video stream with yt-dlp using multiple player client fallbacks to bypass cloud blocks"""
    client_combos = [
        ['android', 'ios'],
        ['ios'],
        ['mweb'],
        ['web_creator']
    ]
    last_err = None
    for clients in client_combos:
        try:
            ydl_opts = {
                'format': f'bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_PATH,
                'extractor_args': {
                    'youtube': {
                        'player_client': clients,
                    }
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception as e:
            last_err = e
            continue

    # Fallback to standard yt-dlp
    ydl_opts_fallback = {
        'format': 'best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_PATH
    }
    with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
        ydl.download([video_url])
    return output_path

def detect_streamer_facecam_ai(
    source_video_path: str,
    api_key: Optional[str] = None,
    sample_timestamp: float = 240.0
) -> Dict[str, Any]:
    """
    Extracts a frame from the video and uses Gemini 3.5 Flash Lite Vision to automatically
    detect the streamer's face/webcam coordinates, perfectly centering the facecam for 9:16 vertical shorts.
    """
    default_result = {
        "has_facecam": True,
        "position": "bottom_center_left",
        "crop_filter": "crop=iw*0.25:ih*0.40:iw*0.22:ih*0.60",
        "description": "Standard Streamer Facecam (Auto-Centered)"
    }

    if not os.path.exists(source_video_path):
        return default_result

    cache_dir = Path("downloads") / "cache_frames"
    cache_dir.mkdir(parents=True, exist_ok=True)
    frame_path = cache_dir / f"frame_{Path(source_video_path).stem}.jpg"

    try:
        # Extract 1 clean frame from video
        cmd = [
            FFMPEG_PATH, "-y",
            "-ss", str(sample_timestamp),
            "-i", source_video_path,
            "-frames:v", "1",
            "-q:v", "2",
            str(frame_path)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

        if not frame_path.exists() or frame_path.stat().st_size == 0:
            return default_result

        if api_key and len(api_key.strip()) > 10:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key.strip())
            with open(frame_path, "rb") as f:
                img_bytes = f.read()

            prompt = """
Look at this 16:9 video stream frame.
Locate the STREAMER (the real human face/person with webcam/headphones).
Return the precise center coordinates and size to crop and center the streamer's head and chest.

Respond strictly in JSON:
{
  "has_streamer": true,
  "center_x_percent": 34.0,
  "center_y_percent": 85.0,
  "crop_width_percent": 25.0,
  "crop_height_percent": 40.0
}
Where center_x_percent and center_y_percent are the exact center point (0.0 to 100.0%) of the streamer's face.
Respond ONLY with JSON. No markdown code blocks.
"""
            res = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    prompt
                ]
            )

            raw = res.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)

            data = json.loads(raw)
            cx = float(data.get("center_x_percent", 34.0)) / 100.0
            cy = float(data.get("center_y_percent", 85.0)) / 100.0
            cw = float(data.get("crop_width_percent", 25.0)) / 100.0
            ch = float(data.get("crop_height_percent", 40.0)) / 100.0

            x = max(0.0, min(1.0 - cw, cx - (cw / 2.0)))
            y = max(0.0, min(1.0 - ch, cy - (ch / 2.0)))

            crop_filter = f"crop=iw*{cw:.2f}:ih*{ch:.2f}:iw*{x:.2f}:ih*{y:.2f}"
            print(f"AI Auto-detected streamer facecam: center=({cx:.2f}, {cy:.2f}) -> {crop_filter}")

            return {
                "has_facecam": True,
                "position": "ai_detected",
                "crop_filter": crop_filter,
                "description": f"AI Centered Streamer Face at ({int(cx*100)}%, {int(cy*100)}%)"
            }

    except Exception as e:
        print(f"AI facecam detection notice: {e}. Using smart default.")

    return default_result

def get_facecam_crop_filter(pos: str, custom_crop: Optional[str] = None) -> str:
    """Return FFmpeg crop filter for streamer facecam based on position or AI auto-detection"""
    if custom_crop and custom_crop.startswith("crop="):
        return custom_crop

    pos = str(pos).lower().strip()
    if pos in ["auto", "ai_detected"]:
        return "crop=iw*0.25:ih*0.40:iw*0.22:ih*0.60"
    elif pos == "top_left":
        return "crop=iw*0.35:ih*0.5:0:0"
    elif pos == "top_right":
        return "crop=iw*0.35:ih*0.5:iw*0.65:0"
    elif pos == "bottom_right":
        return "crop=iw*0.35:ih*0.5:iw*0.65:ih*0.5"
    elif pos == "center":
        return "crop=iw*0.45:ih*0.7:iw*0.275:ih*0.15"
    else:  # default bottom_left / bottom_center_left
        return "crop=iw*0.25:ih*0.40:iw*0.22:ih*0.60"

def render_vertical_clip(
    source_video: str,
    clip_info: Dict[str, Any],
    output_clip_path: str,
    subtitle_ass_path: Optional[str] = None,
    layout: str = "split_streamer_top",
    facecam_pos: str = "auto",
    custom_face_crop: Optional[str] = None
) -> str:
    """
    Renders 9:16 vertical video using FFmpeg.
    Layout options:
      - 'split_streamer_top' (User Paint Layout): Streamer Facecam Centered Top (Top 37.5%, 720px) 
                                                 + Divider Line + Gameplay Bottom (62.5%, 1200px)
      - 'stacked_bottom': Gameplay Top (62%) + Streamer Facecam Bottom (38%)
      - 'pip': Picture-in-Picture (Main Video 9:16 + Streamer Facecam in floating overlay box)
      - 'blur': Cinematic Blur (Opus Clip style, centered video + blurred 9:16 backdrop)
      - 'crop': Full 9:16 Center Action Crop
    """
    start_sec = clip_info["start"]
    duration = clip_info["end"] - clip_info["start"]
    
    # Escape subtitle path for ffmpeg filter graph on Windows
    sub_post = ""
    if subtitle_ass_path and os.path.exists(subtitle_ass_path):
        clean_sub_path = Path(subtitle_ass_path).resolve().as_posix()
        clean_sub_path = clean_sub_path.replace(":", r"\:")
        sub_post = f",ass='{clean_sub_path}'"

    face_crop = get_facecam_crop_filter(facecam_pos, custom_face_crop)

    if layout in ["split_streamer_top", "stacked_top"]:
        # Exact User Shape: Streamer Facecam Centered Top + Divider Line + Gameplay Bottom
        filter_complex = (
            f"[0:v]split=2[f_in][g_in];"
            f"[f_in]{face_crop},scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720[face_pane];"
            f"[g_in]scale=1080:1200:force_original_aspect_ratio=increase,crop=1080:1200[game_pane];"
            f"[face_pane][game_pane]vstack,drawbox=y=717:h=6:color=black:t=fill{sub_post}[outv]"
        )
    elif layout == "stacked_bottom":
        # Gameplay Top + Streamer Facecam Bottom
        filter_complex = (
            f"[0:v]split=2[f_in][g_in];"
            f"[g_in]scale=1080:1200:force_original_aspect_ratio=increase,crop=1080:1200[game_pane];"
            f"[f_in]{face_crop},scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720[face_pane];"
            f"[game_pane][face_pane]vstack,drawbox=y=1197:h=6:color=black:t=fill{sub_post}[outv]"
        )
    elif layout == "pip":
        # Picture-in-Picture: 9:16 Gameplay with floating Streamer Facecam box
        filter_complex = (
            f"[0:v]split=2[bg_in][f_in];"
            f"[bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg];"
            f"[f_in]{face_crop},scale=440:330,drawbox=x=0:y=0:w=iw:h=ih:color=0x00f0ff@1:t=4[cam];"
            f"[bg][cam]overlay=(W-w)/2:120{sub_post}[outv]"
        )
    elif layout == "crop":
        # Full 9:16 Center Crop
        filter_complex = f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920{sub_post}[outv]"
    else:
        # Default 'blur': Blurred background with sharp centered video (Opus Clip style)
        filter_complex = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bgblur];"
            f"[fg]scale=1080:-1[fgscaled];"
            f"[bgblur][fgscaled]overlay=(W-w)/2:(H-h)/2{sub_post}[outv]"
        )

    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-i", source_video,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        output_clip_path
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print(f"FFmpeg render error: {proc.stderr[-500:]}")
        raise RuntimeError(f"FFmpeg failed: {proc.stderr[-300:]}")

    return output_clip_path
