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
    download_video_segment,
    detect_streamer_facecam_ai,
    render_vertical_clip,
    SUBTITLE_STYLES,
    FFMPEG_PATH
)

st.set_page_config(
    page_title="Roy Clipping AI PRO",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark Theme + Neon Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Space+Grotesk:wght@700&display=swap');
    
    .stApp {
        background-color: #08090d;
        color: #f1f5f9;
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    .header-box {
        text-align: center;
        padding: 24px 10px 10px 10px;
        margin-bottom: 20px;
    }
    .header-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #00f0ff, #7928ca, #ff007f);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 1rem;
    }
    .clip-card {
        background: rgba(18, 20, 29, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
    }
    .virality-badge {
        display: inline-block;
        background: linear-gradient(135deg, #10b981, #059669);
        color: #ffffff;
        font-weight: 800;
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 0.85rem;
        margin-bottom: 8px;
    }
    .tag-badge {
        display: inline-block;
        background: rgba(0, 240, 255, 0.12);
        color: #00f0ff;
        border: 1px solid rgba(0, 240, 255, 0.3);
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 0.75rem;
        margin-right: 4px;
        margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)

# App Header
st.markdown("""
<div class="header-box">
    <div class="header-title">👑 Roy Clipping AI PRO</div>
    <div class="header-subtitle">Turn Long YouTube Videos & Recordings Into Viral 9:16 Shorts (Streamer Auto-Center & Neon Subtitles)</div>
</div>
""", unsafe_allow_html=True)

# Work Directories
WORKDIR = Path("downloads_st")
OUTPUT_DIR = Path("output_st")
WORKDIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Helper function to get duration of any local video file using ffprobe
def get_file_duration(file_path: str) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return float(out)
    except Exception:
        return 300.0

# Configuration Bar
with st.expander("⚙️ Settings & Gemini API Key", expanded=False):
    saved_key = os.environ.get("GEMINI_API_KEY", "")
    api_key_input = st.text_input(
        "Google Gemini API Key (Optional for heuristic, Required for AI facecam centering & viral hooks):",
        value=st.session_state.get("gemini_key", saved_key),
        type="password",
        help="Get your free key at aistudio.google.com"
    )
    if api_key_input:
        st.session_state["gemini_key"] = api_key_input.strip()

# Input Mode: YouTube Link OR Direct File Upload
input_mode = st.radio(
    "Choose Video Source:",
    options=["🔗 Paste YouTube Video Link", "📁 Upload Video from Phone / PC"],
    horizontal=True
)

youtube_url = ""
uploaded_file = None

col1, col2 = st.columns([2, 1])

with col1:
    if input_mode == "🔗 Paste YouTube Video Link":
        youtube_url = st.text_input(
            "YouTube Video Link:",
            placeholder="https://www.youtube.com/watch?v=...",
            help="Paste any YouTube video or livestream link"
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload Video File (MP4, MOV, MKV):",
            type=["mp4", "mov", "mkv", "webm"],
            help="Directly upload any streamer recording or gameplay video from your device"
        )

with col2:
    layout_choice = st.selectbox(
        "📐 Video Layout:",
        options=[
            ("split_streamer_top", "👑 Split-Screen: Streamer Facecam Top + Gameplay Bottom"),
            ("blur", "📱 Cinematic Blur (Opus Clip Style)"),
            ("stacked_bottom", "🎮 Gameplay Top + Streamer Facecam Bottom"),
            ("pip", "🖼️ Picture-in-Picture (Overlay Box)"),
            ("crop", "🔍 9:16 Full Center Crop")
        ],
        format_func=lambda x: x[1],
        index=0
    )[0]

col3, col4 = st.columns(2)

with col3:
    subtitle_style = st.selectbox(
        "🎨 Subtitle Style:",
        options=list(SUBTITLE_STYLES.keys()),
        format_func=lambda k: f"{SUBTITLE_STYLES[k]['name']}",
        index=0
    )

with col4:
    clip_count_opt = st.selectbox(
        "✂️ Number of Clips:",
        options=["auto", "1", "2", "3", "5"],
        format_func=lambda x: "🧠 Auto AI (Dynamic Length Selection)" if x == "auto" else f"{x} Clip(s)",
        index=0
    )

generate_btn = st.button("🚀 Generate Viral Shorts Now", type="primary", use_container_width=True)

# Execution Logic
if generate_btn:
    api_key = st.session_state.get("gemini_key", os.environ.get("GEMINI_API_KEY", ""))
    
    if input_mode == "🔗 Paste YouTube Video Link" and not youtube_url.strip():
        st.error("⚠️ Please enter a valid YouTube video link!")
    elif input_mode == "📁 Upload Video from Phone / PC" and uploaded_file is None:
        st.error("⚠️ Please select a video file to upload!")
    else:
        status_box = st.status("🎬 Processing your video...", expanded=True)
        progress_bar = st.progress(5)
        
        try:
            source_video_path = ""
            video_title = "Video Clip"
            transcript = []
            duration_sec = 300.0
            video_id = "custom"
            
            # --- SOURCE HANDLING ---
            if input_mode == "📁 Upload Video from Phone / PC":
                status_box.update(label="📁 Step 1/5: Staging uploaded video...")
                clean_name = re.sub(r'[^a-zA-Z0-9_.]', '_', uploaded_file.name)
                source_video_path = str(WORKDIR / f"uploaded_{clean_name}")
                with open(source_video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                video_title = Path(uploaded_file.name).stem
                duration_sec = get_file_duration(source_video_path)
                video_id = f"up_{int(time.time())}"
                st.write(f"**Loaded:** {video_title} ({int(duration_sec / 60)}m {int(duration_sec % 60)}s)")
                progress_bar.progress(35)
                
            else:
                # YouTube Mode
                video_id = extract_video_id(youtube_url) or "video"
                status_box.update(label="🔍 Step 1/5: Fetching YouTube metadata...")
                meta = fetch_youtube_metadata(youtube_url)
                video_title = meta.get("title", "YouTube Highlight")
                duration_sec = float(meta.get("duration", 0) or 600.0)
                st.write(f"**Found:** {video_title} ({int(duration_sec / 60)} mins)")
                progress_bar.progress(20)
                
                # Transcript
                status_box.update(label="📝 Step 2/5: Fetching speech transcript...")
                try:
                    transcript = fetch_transcript(video_id, youtube_url, caption_lang="en")
                except Exception as te:
                    st.write(f"Notice: Transcript auto-fetch ({te}). Using AI smart timeline detection.")
                    transcript = []
                progress_bar.progress(35)
                
                # Download YouTube video
                status_box.update(label="📥 Step 3/5: Downloading source video stream...")
                source_video_path = str(WORKDIR / f"{video_id}_src.mp4")
                if not os.path.exists(source_video_path) or os.path.getsize(source_video_path) == 0:
                    download_video_segment(youtube_url, source_video_path)
                progress_bar.progress(55)

            # --- VIRAL MOMENT ANALYSIS ---
            status_box.update(label="🧠 Step 4/5: AI analyzing highest viral engagement hooks...")
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
            progress_bar.progress(70)
            
            # --- FACECAM DETECTION & RENDERING ---
            status_box.update(label="👁️ Step 5/5: AI auto-centering streamer facecam & rendering 9:16 vertical clips...")
            custom_face_crop = None
            if layout_choice in ["split_streamer_top", "stacked_bottom", "pip"]:
                face_info = detect_streamer_facecam_ai(source_video_path, api_key=api_key)
                custom_face_crop = face_info.get("crop_filter")
                st.write(f"✅ Streamer Facecam: {face_info.get('description', 'Auto-Centered')}")
            
            completed_clips = []
            total_c = len(viral_clips)
            
            for idx, c in enumerate(viral_clips, 1):
                status_box.update(label=f"🎬 Rendering Clip {idx}/{total_c}: {c['title']}...")
                
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
                    source_video=source_video_path,
                    clip_info=c,
                    output_clip_path=out_clip_path,
                    subtitle_ass_path=sub_path,
                    layout=layout_choice,
                    facecam_pos="auto",
                    custom_face_crop=custom_face_crop
                )
                
                c["file_path"] = out_clip_path
                completed_clips.append(c)
                progress_bar.progress(int(70 + (28 * (idx / total_c))))
            
            progress_bar.progress(100)
            status_box.update(label="🎉 All Viral Shorts Generated Successfully!", state="complete", expanded=False)
            st.session_state["generated_clips"] = completed_clips
            
        except Exception as e:
            status_box.update(label=f"❌ Error: {str(e)}", state="error")
            st.error(f"Processing failed: {str(e)}")

# Display Generated Clips
if "generated_clips" in st.session_state and st.session_state["generated_clips"]:
    st.markdown("---")
    st.markdown("### 👑 Generated Viral Shorts & Reels")
    
    clips = st.session_state["generated_clips"]
    
    for idx, clip in enumerate(clips, 1):
        with st.container():
            col_v, col_d = st.columns([1, 1.2])
            
            with col_v:
                if os.path.exists(clip["file_path"]):
                    st.video(clip["file_path"])
                    with open(clip["file_path"], "rb") as f:
                        clip_bytes = f.read()
                    st.download_button(
                        label=f"⬇️ Download Clip #{idx} (9:16 MP4)",
                        data=clip_bytes,
                        file_name=f"RoyClip_{idx}_{Path(clip['file_path']).name}",
                        mime="video/mp4",
                        key=f"dl_{idx}",
                        use_container_width=True
                    )
            
            with col_d:
                st.markdown(f"#### #{idx} {clip.get('title', 'Highlight')}")
                st.markdown(f"<span class='virality-badge'>🔥 {clip.get('virality_score', 92)}% Viral Probability</span>", unsafe_allow_html=True)
                st.markdown(f"**🎣 Hook Line:** *\"{clip.get('hook', 'Watch this moment!')}\"*")
                st.markdown(f"**💡 Why Viral:** {clip.get('reason', 'High engagement tempo.')}")
                st.markdown(f"**⏰ Best Time to Post:** `{clip.get('best_time_to_post', '6:00 PM - 9:00 PM')}`")
                
                tags_html = "".join([f"<span class='tag-badge'>{tag}</span>" for tag in clip.get("hashtags", [])])
                st.markdown(f"**🏷️ Hashtags:**<br>{tags_html}", unsafe_allow_html=True)
            
            st.markdown("---")
