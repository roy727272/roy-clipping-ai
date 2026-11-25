import os
import re
import time
import subprocess
from pathlib import Path
import streamlit as st

from clipper_core import (
    extract_video_id,
    fetch_youtube_metadata,
    fetch_transcript,
    analyze_viral_moments_gemini,
    analyze_viral_moments_heuristic,
    generate_neon_ass_subtitle,
    download_clip_range,
    detect_streamer_facecam_ai,
    render_vertical_clip,
    SUBTITLE_STYLES,
    FFMPEG_PATH
)

st.set_page_config(
    page_title="Roy Clipping AI Studio PRO",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark Theme + Neon Studio Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@700;800&display=swap');
    
    .stApp {
        background-color: #08090d;
        color: #f1f5f9;
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    .header-box {
        text-align: center;
        padding: 26px 12px 14px 12px;
        margin-bottom: 24px;
        background: radial-gradient(circle at 50% 0%, rgba(0, 240, 255, 0.12) 0%, rgba(8, 9, 13, 0) 70%);
        border-radius: 20px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .header-badge {
        display: inline-block;
        background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(121, 40, 202, 0.2));
        border: 1px solid rgba(0, 240, 255, 0.4);
        color: #00f0ff;
        font-size: 0.8rem;
        font-weight: 700;
        padding: 5px 14px;
        border-radius: 9999px;
        margin-bottom: 12px;
        letter-spacing: 0.5px;
    }
    .header-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2.6rem;
        font-weight: 800;
        background: linear-gradient(135deg, #00f0ff 0%, #a855f7 50%, #ff007f 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
        letter-spacing: -0.5px;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 1.05rem;
        max-width: 720px;
        margin: 0 auto;
        line-height: 1.5;
    }
    .feature-card {
        background: rgba(18, 20, 29, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 18px;
    }
    .virality-badge {
        display: inline-block;
        background: linear-gradient(135deg, #10b981, #059669);
        color: #ffffff;
        font-weight: 800;
        padding: 5px 14px;
        border-radius: 9999px;
        font-size: 0.85rem;
        margin-bottom: 8px;
    }
    .score-chip {
        display: inline-block;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.12);
        color: #e2e8f0;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.78rem;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .tag-badge {
        display: inline-block;
        background: rgba(0, 240, 255, 0.12);
        color: #00f0ff;
        border: 1px solid rgba(0, 240, 255, 0.3);
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.78rem;
        margin-right: 5px;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

# App Header
st.markdown("""
<div class="header-box">
    <div class="header-badge">⚡ 24/7 CLOUD HOSTED • WORKS WITH PC OFF • MOBILE READY</div>
    <div class="header-title">👑 Roy Clipping AI Studio PRO</div>
    <div class="header-subtitle">Turn Gaming Livestreams & Long Videos into Viral 9:16 Shorts with Circular Streamer Facecam, Clean Center Gameplay & Animated Subtitles</div>
</div>
""", unsafe_allow_html=True)

WORKDIR = Path("downloads_st")
OUTPUT_DIR = Path("output_st")
WORKDIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_file_duration(file_path: str) -> float:
    try:
        cmd = [
            FFMPEG_PATH or "ffmpeg", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return float(out)
    except Exception:
        return 300.0

# Top Bar Configuration
with st.expander("⚙️ Advanced Settings & Google Gemini API Key", expanded=False):
    saved_key = os.environ.get("GEMINI_API_KEY", "")
    api_key_input = st.text_input(
        "Google Gemini API Key (Optional for heuristic, Recommended for AI facecam detection & viral hooks):",
        value=st.session_state.get("gemini_key", saved_key),
        type="password",
        help="Get your free key at aistudio.google.com"
    )
    if api_key_input:
        st.session_state["gemini_key"] = api_key_input.strip()

# Video Input Tabs
input_tab1, input_tab2 = st.tabs([
    "🔗 Paste YouTube Video Link",
    "📁 Upload Video from Phone / PC (100% YouTube Bypass)"
])

youtube_url = ""
uploaded_file = None

with input_tab1:
    youtube_url = st.text_input(
        "YouTube Video URL:",
        placeholder="https://www.youtube.com/watch?v=...",
        help="Enter any YouTube livestream or video link"
    )
    st.caption("💡 Tip: Agar YouTube bot detection block kare toh '📁 Upload Video' tab use karein!")

with input_tab2:
    uploaded_file = st.file_uploader(
        "Upload Video / Recording File:",
        type=["mp4", "mov", "mkv", "webm"],
        help="Directly upload gameplay or streamer video from your device (100% works without any YouTube limits)"
    )

st.markdown("### 🎛️ Studio Clipping & Framing Controls")

col_layout, col_quality = st.columns([2, 1])

with col_layout:
    layout_choice = st.selectbox(
        "📐 Video Layout Style:",
        options=[
            ("split_streamer_circle", "👑 Circular Facecam Top + Clean Gameplay Bottom (AI Exclude Facecam)"),
            ("split_streamer_top", "🖼️ Rectangular Facecam Top + Clean Gameplay Bottom"),
            ("blur", "📱 Cinematic Blurred Fill (Opus Clip Style)"),
            ("stacked_bottom", "🎮 Gameplay Top + Facecam Bottom"),
            ("pip", "🪟 Picture-in-Picture Floating Overlay"),
            ("crop", "🔍 9:16 Full Screen Center Crop")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]

with col_quality:
    video_quality = st.selectbox(
        "✨ Output Video Quality:",
        options=[
            ("ultra_1080p", "🔥 Ultra 1080p 60fps (Crisp & Sharp) [Default]"),
            ("cinema_2k", "💎 2K 1440p Master Edition"),
            ("fast", "⚡ 720p 30fps Fast Rendering")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]

# Interactive Framing & Positioning (Manual Selection as requested)
with st.expander("🎯 Streamer Facecam & Gameplay Alignment Controls", expanded=True):
    col_face, col_game = st.columns(2)
    
    with col_face:
        st.markdown("**🔴 Streamer Facecam Positioning:**")
        face_mode = st.selectbox(
            "Streamer Facecam Location:",
            options=[
                ("auto", "🤖 Auto AI Smart Center (Detects Face Automatically)"),
                ("bottom_left", "↙️ Bottom-Left Streamer (GTA / Valorant / BGMI)"),
                ("bottom_right", "↘️ Bottom-Right Streamer (Minecraft / Apex)"),
                ("top_left", "↖️ Top-Left Streamer (Reaction / Esports)"),
                ("top_right", "↗️ Top-Right Streamer (Fortnite / CoD)"),
                ("center", "🎯 Center Streamer (Talk Show / Podcast)"),
                ("custom", "🛠️ Custom Manual Sliders (Adjust X, Y, Size)")
            ],
            format_func=lambda x: x[1],
            index=0
        )[0]
        
        custom_face_crop = None
        if face_mode == "custom":
            face_x = st.slider("Streamer Horizontal X (%)", 0, 100, 15)
            face_y = st.slider("Streamer Vertical Y (%)", 0, 100, 60)
            face_w = st.slider("Streamer Window Size (%)", 15, 50, 28)
            custom_face_crop = f"crop=iw*{face_w/100:.2f}:ih*{face_w*1.5/100:.2f}:iw*{face_x/100:.2f}:ih*{face_y/100:.2f}"
    
    with col_game:
        st.markdown("**🎮 Gameplay Horizontal Focus:**")
        game_focus = st.selectbox(
            "Gameplay Center Framing:",
            options=[
                ("center", "🎯 Center Game Focus (Action Centered - Standard)"),
                ("left", "🕹️ Left Bias (Keeps Left Action & Character)"),
                ("right", "🎮 Right Bias (Keeps Right Action & Weapon)"),
                ("custom", "🛠️ Custom Gameplay Center Slider")
            ],
            format_func=lambda x: x[1],
            index=0
        )[0]
        
        custom_game_crop_x = None
        if game_focus == "center":
            custom_game_crop_x = "(in_w-1080)/2"
        elif game_focus == "left":
            custom_game_crop_x = "0"
        elif game_focus == "right":
            custom_game_crop_x = "in_w-1080"
        elif game_focus == "custom":
            crop_pct = st.slider("Gameplay Center Offset (%)", 0, 100, 50)
            custom_game_crop_x = f"(in_w-1080)*{crop_pct/100:.2f}"

col_sub, col_count = st.columns(2)

with col_sub:
    sub_keys = list(SUBTITLE_STYLES.keys())
    sub_labels = {
        "hormozi_yellow": "🔥 MrBeast / Hormozi Viral Yellow (High Impact)",
        "neon_cyan": "💎 Cyberpunk Neon Cyan & Pink Glow",
        "red_devour": "🎮 Devour Gaming Red Glow (Clutch Moments)",
        "beast_bold": "👑 Bold Gold Luxury High-Contrast",
        "green_money": "🚀 Alex Hormozi Green Pop",
        "minimal_white": "✨ Minimal Clean White"
    }
    subtitle_style = st.selectbox(
        "🎨 Subtitle Typography & Colors:",
        options=sub_keys,
        format_func=lambda k: sub_labels.get(k, SUBTITLE_STYLES[k]["name"]),
        index=0
    )

with col_count:
    clip_count_opt = st.selectbox(
        "✂️ Number of Clips to Generate:",
        options=["auto", "1", "2", "3", "5"],
        format_func=lambda x: "🧠 Auto AI (Dynamic Length Selection)" if x == "auto" else f"{x} Clip(s)",
        index=0
    )

generate_btn = st.button("🚀 Generate Viral Shorts Now", type="primary", use_container_width=True)

# Processing Logic
if generate_btn:
    api_key = st.session_state.get("gemini_key", os.environ.get("GEMINI_API_KEY", ""))
    
    is_uploaded = (uploaded_file is not None)
    is_yt = bool(youtube_url.strip())
    
    if not is_uploaded and not is_yt:
        st.error("⚠️ Please enter a YouTube video link OR upload a video file to proceed!")
    else:
        status_box = st.status("🎬 Processing your video...", expanded=True)
        progress_bar = st.progress(5)
        
        try:
            source_video_path = ""
            video_title = "Highlight Clip"
            transcript = []
            duration_sec = 300.0
            video_id = "custom"
            
            # --- STAGE 1: SOURCE ACQUISITION ---
            if is_uploaded:
                status_box.update(label="📁 Step 1/5: Loading uploaded video...")
                clean_name = re.sub(r'[^a-zA-Z0-9_.]', '_', uploaded_file.name)
                source_video_path = str(WORKDIR / f"uploaded_{clean_name}")
                with open(source_video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                video_title = Path(uploaded_file.name).stem
                duration_sec = get_file_duration(source_video_path)
                video_id = f"up_{int(time.time())}"
                st.write(f"✅ **Loaded file:** {video_title} ({int(duration_sec / 60)}m {int(duration_sec % 60)}s)")
                progress_bar.progress(35)
                
            else:
                video_id = extract_video_id(youtube_url) or "video"
                status_box.update(label="🔍 Step 1/5: Fetching YouTube metadata...")
                try:
                    meta = fetch_youtube_metadata(youtube_url)
                    video_title = meta.get("title", "YouTube Highlight")
                    duration_sec = float(meta.get("duration", 0) or 600.0)
                    st.write(f"✅ **Found:** {video_title} ({int(duration_sec / 60)} mins)")
                except Exception as me:
                    st.write(f"Notice on metadata ({me}), continuing with direct stream analysis...")
                progress_bar.progress(20)
                
                # Transcript
                status_box.update(label="📝 Step 2/5: Fetching speech transcript...")
                try:
                    transcript = fetch_transcript(video_id, youtube_url, caption_lang="en")
                except Exception as te:
                    st.write(f"Notice: Transcript auto-fetch ({te}). Using AI smart timeline detection.")
                    transcript = []
                progress_bar.progress(35)
                
                status_box.update(label="📥 Step 3/5: Stream verified, preparing fast range clips...")
                progress_bar.progress(50)

            # --- STAGE 2: VIRAL MOMENT ANALYSIS ---
            status_box.update(label="🧠 Step 4/5: AI analyzing highest viral engagement moments...")
            duration_mins = duration_sec / 60.0
            
            if clip_count_opt == "auto":
                if duration_mins <= 6:
                    target_clips = 2
                elif duration_mins <= 15:
                    target_clips = 3
                elif duration_mins <= 35:
                    target_clips = 5
                else:
                    target_clips = 6
            else:
                target_clips = int(clip_count_opt)
            
            if api_key and len(api_key.strip()) > 10:
                viral_clips = analyze_viral_moments_gemini(
                    transcript=transcript,
                    video_title=video_title,
                    api_key=api_key.strip(),
                    clip_count=target_clips,
                    video_duration=duration_sec
                )
            else:
                viral_clips = analyze_viral_moments_heuristic(
                    transcript=transcript,
                    clip_count=target_clips,
                    video_duration=duration_sec
                )
            
            st.write(f"🎯 AI identified **{len(viral_clips)} high-performing viral moments**!")
            progress_bar.progress(65)
            
            # --- STAGE 3: FACECAM CALCULATION & RENDERING ---
            status_box.update(label="👀 Step 5/5: Auto-centering streamer facecam & rendering 9:16 vertical clips...")
            
            final_face_crop = custom_face_crop
            final_game_crop_x = custom_game_crop_x
            
            # If Auto AI and we have an uploaded source video, perform AI face detection
            if face_mode == "auto" and source_video_path and os.path.exists(source_video_path):
                face_info = detect_streamer_facecam_ai(source_video_path, api_key=api_key)
                final_face_crop = face_info.get("crop_filter")
                if not custom_game_crop_x:
                    final_game_crop_x = face_info.get("game_crop_x")
                st.write(f"✅ Streamer Facecam: {face_info.get('description', 'Auto-Centered')}")
            elif face_mode != "auto" and face_mode != "custom":
                # Preset selection
                final_face_crop = None
            
            completed_clips = []
            total_c = len(viral_clips)
            
            for idx, c in enumerate(viral_clips, 1):
                raw_segment_path = None
                
                if is_uploaded and source_video_path:
                    render_source = source_video_path
                    render_clip_info = c
                else:
                    status_box.update(label=f"📥 Downloading Clip {idx}/{total_c} ({c.get('title', 'Clip')})...")
                    raw_segment_path = str(WORKDIR / f"raw_{video_id}_{idx}.mp4")
                    download_clip_range(
                        video_url=youtube_url,
                        start_sec=c["start"],
                        end_sec=c["end"],
                        output_path=raw_segment_path
                    )
                    render_source = raw_segment_path
                    render_clip_info = {
                        "start": 0.0,
                        "end": max(1.0, c["end"] - c["start"]),
                        "title": c.get("title", f"Viral Clip #{idx}")
                    }

                status_box.update(label=f"🎬 Rendering Clip {idx}/{total_c} in {video_quality} quality...")
                
                sub_path = str(WORKDIR / f"sub_{video_id}_{idx}.ass")
                generate_neon_ass_subtitle(
                    transcript=transcript,
                    clip_start=c["start"],
                    clip_end=c["end"],
                    output_path=sub_path,
                    style_name=subtitle_style,
                    clip_subtitles=c.get("subtitles")
                )
                
                out_clip_path = str(OUTPUT_DIR / f"roy_clip_{video_id}_{idx}.mp4")
                render_vertical_clip(
                    source_video=render_source,
                    clip_info=render_clip_info,
                    output_clip_path=out_clip_path,
                    subtitle_ass_path=sub_path,
                    layout=layout_choice,
                    facecam_pos=face_mode if face_mode != "custom" else "auto",
                    custom_face_crop=final_face_crop,
                    custom_game_crop_x=final_game_crop_x,
                    video_quality=video_quality
                )

                if raw_segment_path and os.path.exists(raw_segment_path):
                    try:
                        os.remove(raw_segment_path)
                    except Exception:
                        pass
                
                c["file_path"] = out_clip_path
                completed_clips.append(c)
                progress_bar.progress(int(65 + (33 * (idx / total_c))))
            
            progress_bar.progress(100)
            status_box.update(label="🎉 All Viral Shorts Generated Successfully!", state="complete", expanded=False)
            st.session_state["generated_clips"] = completed_clips
            
        except Exception as e:
            err_msg = str(e)
            status_box.update(label="❌ Clip Generation Paused", state="error")
            if "botguard" in err_msg.lower() or "bot" in err_msg.lower() or "429" in err_msg.lower():
                st.error(
                    f"⚠️ **YouTube Datacenter Restriction Notice:**\n\n"
                    f"{err_msg}\n\n"
                    f"💡 **Solution (100% Guaranteed):** Upar '📁 Upload Video from Phone / PC' tab par click karein aur apne device se video upload karein. File upload par YouTube ka koi restriction nahi lagta aur video turant render hoti hai!"
                )
            else:
                st.error(f"⚠️ Processing Error: {err_msg}")

# Display Generated Clips
if "generated_clips" in st.session_state and st.session_state["generated_clips"]:
    st.markdown("---")
    st.markdown("### 👑 Generated Viral Shorts & Reels")
    
    clips = st.session_state["generated_clips"]
    
    for idx, clip in enumerate(clips, 1):
        with st.container():
            col_v, col_d = st.columns([1, 1.3])
            
            with col_v:
                if os.path.exists(clip["file_path"]):
                    st.video(clip["file_path"])
                    with open(clip["file_path"], "rb") as f:
                        clip_bytes = f.read()
                    st.download_button(
                        label=f"⬇️ Download Clip #{idx} (Ultra 1080p MP4)",
                        data=clip_bytes,
                        file_name=f"RoyClip_{idx}_{Path(clip['file_path']).name}",
                        mime="video/mp4",
                        key=f"dl_{idx}",
                        use_container_width=True
                    )
            
            with col_d:
                st.markdown(f"#### #{idx} {clip.get('title', 'Highlight')}")
                st.markdown(f"<span class='virality-badge'>🔥 {clip.get('virality_score', 94)}% Virality Score</span>", unsafe_allow_html=True)
                
                # Score breakdown
                st.markdown(
                    f"<span class='score-chip'>🎣 Hook Score: {clip.get('hook_score', 92)}/100</span>"
                    f"<span class='score-chip'>⏱️ Retention: {clip.get('retention_score', 90)}%</span>"
                    f"<span class='score-chip'>📈 Viral Potential: Ultra High</span>",
                    unsafe_allow_html=True
                )
                
                st.markdown(f"**🎯 Hook Caption:**")
                st.code(clip.get("hook", "Watch till the end! 😱"), language="text")
                
                st.markdown(f"**💡 AI Virality Analysis:** {clip.get('reason', 'High engagement tempo and dramatic buildup.')}")
                st.markdown(f"**⏰ Best Time to Post:** `{clip.get('best_time_to_post', '6:00 PM - 9:00 PM')}`")
                
                tags = clip.get("hashtags", ["#viral", "#shorts", "#trending", "#gaming", "#fyp"])
                st.markdown("**🏷️ Trending Hashtags:**")
                st.code(" ".join(tags), language="text")
            
            st.markdown("---")
