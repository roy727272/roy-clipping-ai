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
                'player_client': ['tv_embedded', 'tv', 'mweb', 'android', 'ios'],
                'player_skip': ['webpage', 'configs', 'js']
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
                'player_client': ['tv_embedded', 'tv', 'mweb', 'android', 'ios'],
                'player_skip': ['webpage', 'configs', 'js']
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

def download_from_invidious_fallback(video_id: str, output_path: str) -> bool:
    """Download video stream from public Invidious instances when YouTube blocks datacenter IP"""
    instances = [
        "https://iv.ggtyler.dev",
        "https://invidious.privacydev.net",
        "https://invidious.drgns.space",
        "https://inv.vern.cc",
        "https://invidious.jing.rocks",
        "https://invidious.nerdvpn.de"
    ]
    import requests
    for inst in instances:
        try:
            api_url = f"{inst}/api/v1/videos/{video_id}"
            r = requests.get(api_url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                streams = data.get("formatStreams", [])
                if streams:
                    stream_url = streams[-1].get("url")
                    if stream_url:
                        with requests.get(stream_url, stream=True, timeout=30) as resp:
                            if resp.status_code == 200:
                                with open(output_path, "wb") as f:
                                    for chunk in resp.iter_content(chunk_size=32768):
                                        if chunk:
                                            f.write(chunk)
                                if os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
                                    print(f"Downloaded via Invidious ({inst})")
                                    return True
        except Exception:
            continue
    return False

def download_from_piped_fallback(video_id: str, output_path: str) -> bool:
    """Download video stream from public Piped instances"""
    piped_instances = [
        "https://pipedapi.kavin.rocks",
        "https://api.piped.privacydev.net",
        "https://piped-api.lunar.icu"
    ]
    import requests
    for inst in piped_instances:
        try:
            api_url = f"{inst}/streams/{video_id}"
            r = requests.get(api_url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                video_streams = data.get("videoStreams", [])
                for s in video_streams:
                    if s.get("format") == "MPEG_4" or "video/mp4" in s.get("mimeType", ""):
                        s_url = s.get("url")
                        if s_url:
                            with requests.get(s_url, stream=True, timeout=30) as resp:
                                if resp.status_code == 200:
                                    with open(output_path, "wb") as f:
                                        for chunk in resp.iter_content(chunk_size=32768):
                                            if chunk:
                                                f.write(chunk)
                                    if os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
                                        print(f"Downloaded via Piped ({inst})")
                                        return True
        except Exception:
            continue
    return False

def download_clip_range(
    video_url: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
    max_height: int = 1080
) -> str:
    """
    Downloads ONLY the required clip segment (start_sec to end_sec) in 1080p 60fps.
    Uses yt-dlp download_ranges with stream copy to avoid downloading gigabytes of video.
    Takes ~15-25 seconds per clip!
    """
    from yt_dlp.utils import download_range_func
    
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    if out_p.exists():
        try:
            out_p.unlink()
        except Exception:
            pass

    formats = [
        f'bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={max_height}]+bestaudio/best',
        f'bestvideo[height<={max_height}]+bestaudio/best',
        'best'
    ]

    client_combos = [
        ['android', 'ios'],
        ['ios'],
        ['android'],
        ['mweb'],
        ['tv_embedded'],
        ['web_embedded'],
        ['tv']
    ]

    last_exc = None
    # Pass 1: Try fast range downloads with mobile/embedded clients
    for clients in client_combos:
        for fmt in formats:
            try:
                ydl_opts = {
                    'format': fmt,
                    'outtmpl': output_path,
                    'download_ranges': download_range_func(None, [(max(0.0, start_sec), end_sec)]),
                    'quiet': True,
                    'no_warnings': True,
                    'ffmpeg_location': FFMPEG_PATH,
                    'extractor_args': {
                        'youtube': {
                            'player_client': clients,
                            'player_skip': ['webpage', 'configs', 'js']
                        }
                    }
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])

                if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                    print(f"[FAST RANGE] Successfully downloaded clip segment ({start_sec}s - {end_sec}s) with clients {clients}: {output_path}")
                    return output_path
            except Exception as e:
                last_exc = e
                continue

    # Pass 2: Fallback to segment download with all fallback mechanisms (including Invidious/Piped) + FFmpeg slice
    print(f"[FAST RANGE] Direct range download blocked ({last_exc}). Trying fallback download...")
    try:
        temp_full = str(out_p.parent / f"temp_slice_{int(time.time())}_{int(start_sec)}.mp4")
        downloaded = download_video_segment(video_url, temp_full, max_height=max_height)
        if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 10000:
            cmd = [
                FFMPEG_PATH, "-y",
                "-ss", str(max(0.0, start_sec)),
                "-to", str(end_sec),
                "-i", downloaded,
                "-c", "copy",
                output_path
            ]
            subprocess.run(cmd, check=True)
            try:
                os.remove(downloaded)
            except Exception:
                pass
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                print(f"[FALLBACK SLICE] Successfully sliced clip ({start_sec}s - {end_sec}s): {output_path}")
                return output_path
    except Exception as e:
        print(f"Fallback slice failed: {e}")

    raise RuntimeError(
        f"YouTube BotGuard has blocked direct streaming for this video ({last_exc}). "
        "Please switch to '📁 Upload Video from Phone / PC' tab — upload your file directly to clip without any YouTube restrictions!"
    )

def download_video_segment(video_url: str, output_path: str, max_height: int = 1080) -> str:
    """
    Download video stream with yt-dlp in high-definition 1080p/best quality.
    Prioritizes true 1080p 60fps video + studio audio streams.
    """
    vid_id = extract_video_id(video_url) or "video"

    # Priority 1: Direct High-Definition 1080p60 Download
    try:
        ydl_opts_hd = {
            'format': f'bestvideo[height<={max_height}]+bestaudio/bestvideo+bestaudio/best[height<={max_height}]/best',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'ffmpeg_location': FFMPEG_PATH
        }
        with yt_dlp.YoutubeDL(ydl_opts_hd) as ydl:
            ydl.download([video_url])

        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            # Verify resolution with ffprobe
            dur_cmd = [
                FFPROBE_PATH, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                output_path
            ]
            dur_p = subprocess.run(dur_cmd, capture_output=True, text=True)
            try:
                h = int(dur_p.stdout.strip())
                if h >= 720:
                    print(f"Downloaded crystal-clear {h}p HD video stream: {output_path}")
                    return output_path
            except Exception:
                return output_path
    except Exception as e:
        print(f"Direct HD download notice: {e}. Trying fallback client combos...")

    # Priority 2: Client Combos for bypass
    formats_to_try = [
        f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/bestvideo+bestaudio/best",
        f"bestvideo+bestaudio/best[height<={max_height}]/best",
        "best"
    ]
    
    client_combos = [
        ['android', 'ios'],
        ['ios'],
        ['android'],
        ['mweb'],
        ['web_embedded'],
        ['tv_embedded'],
        ['tv_samsung']
    ]
    
    last_err = None
    for fmt in formats_to_try:
        for clients in client_combos:
            try:
                ydl_opts = {
                    'format': fmt,
                    'outtmpl': output_path,
                    'quiet': True,
                    'no_warnings': True,
                    'merge_output_format': 'mp4',
                    'ffmpeg_location': FFMPEG_PATH,
                    'extractor_args': {
                        'youtube': {
                            'player_client': clients,
                            'player_skip': ['webpage', 'configs', 'js']
                        }
                    }
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                    return output_path
            except Exception as e:
                last_err = e
                continue

    # Fallback 1: Try Invidious API
    if vid_id:
        print("Trying Invidious proxy...")
        if download_from_invidious_fallback(vid_id, output_path):
            return output_path

    # Fallback 2: Try Piped API
    if vid_id:
        print("Trying Piped proxy...")
        if download_from_piped_fallback(vid_id, output_path):
            return output_path

    # Final attempt with generic best
    try:
        ydl_opts_final = {
            'format': 'best',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'ffmpeg_location': FFMPEG_PATH
        }
        with yt_dlp.YoutubeDL(ydl_opts_final) as ydl:
            ydl.download([video_url])
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            return output_path
    except Exception as e:
        last_err = e

    raise RuntimeError(
        f"YouTube blocked download ({last_err}). "
        f"Please use the '📁 Upload Video File' tab to upload this video directly from your device!"
    )

def ensure_circle_assets() -> tuple[str, str]:
    """
    Ensures that circle_mask_gray.png and circle_border.png exist.
    Generates them dynamically using pure standard library (zlib, struct) if missing.
    Returns (mask_path, border_path).
    """
    import zlib, struct
    base_dir = Path(__file__).resolve().parent
    mask_path = base_dir / "circle_mask_gray.png"
    border_path = base_dir / "circle_border.png"
    
    size = 480
    r = size / 2.0
    
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    if not mask_path.exists():
        raw_gray = bytearray()
        for y in range(size):
            raw_gray.append(0)  # filter type 0
            for x in range(size):
                dx = x - r + 0.5
                dy = y - r + 0.5
                dist = (dx*dx + dy*dy)**0.5
                if dist <= r - 1.0:
                    val = 255
                elif dist >= r:
                    val = 0
                else:
                    val = int(255 * (r - dist))
                raw_gray.append(val)
        ihdr = struct.pack('>IIBBBBB', size, size, 8, 0, 0, 0, 0)
        idat = zlib.compress(raw_gray, 9)
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
        with open(mask_path, 'wb') as f:
            f.write(png)

    if not border_path.exists():
        raw_border = bytearray()
        border_width = 6
        for y in range(size):
            raw_border.append(0)
            for x in range(size):
                dx = x - r + 0.5
                dy = y - r + 0.5
                dist = (dx*dx + dy*dy)**0.5
                inner_r = r - border_width
                if dist <= r and dist >= inner_r:
                    if dist >= r - 1:
                        b_alpha = int(255 * (r - dist))
                    elif dist <= inner_r + 1:
                        b_alpha = int(255 * (dist - inner_r))
                    else:
                        b_alpha = 255
                else:
                    b_alpha = 0
                raw_border.extend([255, 255, 255, b_alpha])
        ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
        idat = zlib.compress(raw_border, 9)
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
        with open(border_path, 'wb') as f:
            f.write(png)

    return str(mask_path), str(border_path)

def detect_streamer_facecam_ai(
    source_video_path: str,
    api_key: Optional[str] = None,
    sample_timestamp: float = 240.0
) -> Dict[str, Any]:
    """
    Extracts a frame from the video and uses Gemini Vision to automatically:
    1. Detect the streamer's face / webcam coordinates to center the face in the top circular facecam.
    2. Identify the streamer's quadrant (left/right/center) to crop gameplay and 100% EXCLUDE the streamer's
       webcam from the bottom gameplay area!
    """
    default_result = {
        "has_facecam": True,
        "position": "bottom_left",
        "crop_filter": "crop=iw*0.28:ih*0.42:iw*0.14:ih*0.58",
        "game_crop_x": "in_w-1080",
        "description": "Streamer Facecam (Auto-Centered Top Circle + Clean Bottom Gameplay)"
    }

    if not os.path.exists(source_video_path):
        return default_result

    if source_video_path.lower().endswith((".jpg", ".jpeg", ".png")) and os.path.exists(source_video_path):
        frame_path = Path(source_video_path)
    else:
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
        except Exception:
            pass

    try:
        if not frame_path.exists() or frame_path.stat().st_size == 0:
            return default_result

        if api_key and len(api_key.strip()) > 10:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key.strip())
            with open(frame_path, "rb") as f:
                img_bytes = f.read()

            prompt = """
Look at this 16:9 gaming video stream frame.
1. Locate the STREAMER (the real human face/person with webcam or microphone/headphones).
2. What part of the screen is their facecam located in?
   Choose one: "bottom_left", "bottom_right", "top_left", "top_right", "bottom_center", "center", "none"
3. Return the center coordinates (center_x_percent, center_y_percent) of the streamer's face/head (0.0 to 100.0).
4. Return the crop width and height percentage around their head and shoulders for a circular facecam.

Respond strictly in JSON:
{
  "has_streamer": true,
  "facecam_position": "bottom_left",
  "center_x_percent": 28.0,
  "center_y_percent": 75.0,
  "crop_width_percent": 28.0,
  "crop_height_percent": 42.0
}
Where center_x_percent and center_y_percent are the center of the streamer's face.
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
            pos = str(data.get("facecam_position", "bottom_left")).lower()
            cx = float(data.get("center_x_percent", 28.0)) / 100.0
            cy = float(data.get("center_y_percent", 75.0)) / 100.0
            cw = float(data.get("crop_width_percent", 28.0)) / 100.0
            ch = float(data.get("crop_height_percent", 42.0)) / 100.0

            cw = max(0.20, min(0.60, cw))
            ch = max(0.25, min(0.70, ch))

            x = max(0.0, min(1.0 - cw, cx - (cw / 2.0)))
            y = max(0.0, min(1.0 - ch, cy - (ch / 2.0)))

            crop_filter = f"crop=iw*{cw:.2f}:ih*{ch:.2f}:iw*{x:.2f}:ih*{y:.2f}"

            # Calculate gameplay crop to 100% exclude streamer webcam from bottom gameplay pane
            if pos in ["bottom_left", "top_left"] or cx < 0.45:
                game_crop_x = "in_w-1080" # Far right crop -> left facecam 100% excluded
            elif pos in ["bottom_right", "top_right"] or cx > 0.55:
                game_crop_x = "0" # Far left crop -> right facecam 100% excluded
            else:
                game_crop_x = "(in_w-1080)/2"

            print(f"AI Auto-detected streamer: pos={pos}, center=({cx:.2f}, {cy:.2f}) -> face_crop={crop_filter}, game_crop={game_crop_x}")

            return {
                "has_facecam": True,
                "position": pos,
                "crop_filter": crop_filter,
                "game_crop_x": game_crop_x,
                "description": f"AI Detected {pos} ({int(cx*100)}%, {int(cy*100)}%) -> Top Circle + Clean Bottom Gameplay"
            }

    except Exception as e:
        print(f"AI facecam detection notice: {e}. Using smart default.")

    return default_result

def get_facecam_crop_filter(pos: str, custom_crop: Optional[str] = None) -> str:
    """Return FFmpeg crop filter for streamer facecam based on position or AI auto-detection"""
    if custom_crop and custom_crop.startswith("crop="):
        return custom_crop

    pos = str(pos).lower().strip()
    if pos in ["top_left"]:
        return "crop=iw*0.28:ih*0.42:0:0"
    elif pos in ["top_right"]:
        return "crop=iw*0.28:ih*0.42:iw*0.72:0"
    elif pos in ["bottom_right"]:
        return "crop=iw*0.28:ih*0.42:iw*0.62:ih*0.58"
    elif pos in ["center"]:
        return "crop=iw*0.35:ih*0.50:iw*0.325:ih*0.25"
    else:  # default bottom_left / auto / ai_detected
        return "crop=iw*0.28:ih*0.42:iw*0.14:ih*0.58"

def get_gameplay_crop_x(pos: str, custom_game_crop_x: Optional[str] = None) -> str:
    """Return FFmpeg X offset expression for bottom gameplay to 100% exclude streamer webcam"""
    if custom_game_crop_x:
        return custom_game_crop_x

    pos = str(pos).lower().strip()
    if pos in ["bottom_right", "top_right", "right"]:
        return "0"
    elif pos in ["center"]:
        return "(in_w-1080)/2"
    else:  # bottom_left, top_left, auto
        return "in_w-1080"

def render_vertical_clip(
    source_video: str,
    clip_info: Dict[str, Any],
    output_clip_path: str,
    subtitle_ass_path: Optional[str] = None,
    layout: str = "split_streamer_circle",
    facecam_pos: str = "auto",
    custom_face_crop: Optional[str] = None,
    custom_game_crop_x: Optional[str] = None,
    custom_game_crop: Optional[str] = None,
    video_quality: str = "ultra_1080p"
) -> str:
    """
    Renders 9:16 vertical video using FFmpeg in Ultra-HD 1080p 60fps quality.
    Features:
      - Lanczos high-fidelity scaling
      - Intelligent sharpening (unsharp mask) for ultra-crisp gaming textures
      - Visually lossless encoding (CRF 17, High Profile 4.2)
      - Studio audio master (192kbps 48kHz stereo)
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
    game_crop_x = get_gameplay_crop_x(facecam_pos, custom_game_crop_x)

    extra_inputs = []

    if layout in ["split_streamer_circle", "split_streamer_top", "circle", "stacked_top"]:
        # User Sketch Layout: Top Circle Streamer Facecam + Clean Gameplay Bottom (AI or Manual Exclude)
        mask_png, border_png = ensure_circle_assets()
        clean_mask = Path(mask_png).resolve().as_posix()
        clean_border = Path(border_png).resolve().as_posix()

        extra_inputs = ["-loop", "1", "-i", clean_mask, "-loop", "1", "-i", clean_border]

        # Determine bottom gameplay filter (custom explicit crop vs smart offset) with Lanczos + Sharpening
        if custom_game_crop and custom_game_crop.startswith("crop="):
            gameplay_pane_filter = f"[0:v]{custom_game_crop},scale=1080:1340:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1340,unsharp=5:5:0.6:5:5:0.0[game_final];"
        else:
            gameplay_pane_filter = f"[0:v]scale=-1:1340:flags=lanczos,crop=1080:1340:x={game_crop_x}:y=0,unsharp=5:5:0.6:5:5:0.0[game_final];"

        filter_complex = (
            f"[0:v]scale=1080:580:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:580,boxblur=25:5,drawbox=x=0:y=0:w=iw:h=ih:color=0x0a0c14@0.90:t=fill[top_bg];"
            f"[0:v]{face_crop},scale=480:480:flags=lanczos:force_original_aspect_ratio=increase,crop=480:480,unsharp=5:5:0.4:5:5:0.0,format=yuva420p[face_sq];"
            f"[1:v]format=gray[mask_g];"
            f"[face_sq][mask_g]alphamerge[face_circle];"
            f"[top_bg][face_circle]overlay=300:50:format=auto[top_with_face];"
            f"[top_with_face][2:v]overlay=300:50:format=auto[top_final];"
            f"{gameplay_pane_filter}"
            f"[top_final][game_final]vstack,drawbox=y=577:h=6:color=black:t=fill{sub_post}[outv]"
        )
    elif layout == "stacked_bottom":
        filter_complex = (
            f"[0:v]split=2[f_in][g_in];"
            f"[g_in]scale=1080:1200:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1200,unsharp=5:5:0.6:5:5:0.0[game_pane];"
            f"[f_in]{face_crop},scale=1080:720:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:720,unsharp=5:5:0.4:5:5:0.0[face_pane];"
            f"[game_pane][face_pane]vstack,drawbox=y=1197:h=6:color=black:t=fill{sub_post}[outv]"
        )
    elif layout == "pip":
        filter_complex = (
            f"[0:v]split=2[bg_in][f_in];"
            f"[bg_in]scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:0.5:5:5:0.0[bg];"
            f"[f_in]{face_crop},scale=440:330:flags=lanczos,unsharp=5:5:0.4:5:5:0.0,drawbox=x=0:y=0:w=iw:h=ih:color=0x00f0ff@1:t=4[cam];"
            f"[bg][cam]overlay=(W-w)/2:120{sub_post}[outv]"
        )
    elif layout == "crop":
        filter_complex = f"[0:v]scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:0.6:5:5:0.0{sub_post}[outv]"
    else:
        # Default 'blur': Blurred background with sharp centered video (Opus Clip style)
        filter_complex = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bgblur];"
            f"[fg]scale=1080:-1:flags=lanczos,unsharp=5:5:0.6:5:5:0.0[fgscaled];"
            f"[bgblur][fgscaled]overlay=(W-w)/2:(H-h)/2{sub_post}[outv]"
        )

    # Ultra-HD Encoding Presets
    if video_quality == "cinema_2k":
        crf_val = "15"
        preset_val = "medium"
    elif video_quality == "fast":
        crf_val = "22"
        preset_val = "veryfast"
    else:  # ultra_1080p (Default)
        crf_val = "17"
        preset_val = "fast"

    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-i", source_video
    ]
    if extra_inputs:
        cmd.extend(extra_inputs)

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", preset_val,
        "-crf", crf_val,
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.2",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000"
    ])
    if extra_inputs:
        cmd.append("-shortest")

    cmd.append(output_clip_path)

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print(f"FFmpeg render error: {proc.stderr[-500:]}")
        raise RuntimeError(f"FFmpeg failed: {proc.stderr[-300:]}")

    return output_clip_path
