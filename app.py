import csv
import io
import json
import os
import tempfile
from pathlib import Path
import streamlit as st
import pandas as pd

from rank import rank_candidates, load_candidates

# Page configuration
st.set_page_config(
    page_title="Redrob Candidate Discovery Sandbox",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom premium styling
st.markdown(
    """
    <style>
    .main {
        background-color: #0f111a;
        color: #e6edf3;
        font-family: 'Inter', sans-serif;
    }
    .stApp {
        background-color: #0f111a;
    }
    h1 {
        color: #58a6ff;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
    }
    .metric-val {
        font-size: 24px;
        font-weight: bold;
        color: #58a6ff;
    }
    .metric-lbl {
        font-size: 14px;
        color: #8b949e;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🔍 Redrob Candidate Discovery Sandbox")
st.markdown("Verify and reproduce the candidate ranking pipeline on small sample files (up to 100 candidates).")

st.markdown("---")

# File upload or fallback selection
uploaded_file = st.file_uploader(
    "Upload Candidate Sample (JSON / JSONL)",
    type=["json", "jsonl"],
    help="Upload a sample candidates file to run the ranker."
)

candidates = None
source_name = ""

if uploaded_file is not None:
    # Save uploaded file to temp file to reuse load_candidates Path logic
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = Path(temp_file.name)
    
    try:
        candidates = load_candidates(temp_path)
        source_name = uploaded_file.name
    except Exception as e:
        st.error(f"Error loading uploaded file: {e}")
    finally:
        if temp_path.exists():
            os.unlink(temp_path)
else:
    # Fallback to pre-loaded sample_candidates.json
    default_path = Path("sample_candidates.json")
    if not default_path.exists() and Path("ProjectFile/sample_candidates.json").exists():
        default_path = Path("ProjectFile/sample_candidates.json")
        
    if default_path.exists():
        candidates = load_candidates(default_path)
        source_name = default_path.name
        st.info(f"Using pre-loaded sample file: `{source_name}` (First 50 candidates)")
    else:
        st.warning("No sample file uploaded, and default `sample_candidates.json` was not found.")

if candidates:
    # Truncate input sample to 100 max per sandbox spec
    original_len = len(candidates)
    if original_len > 100:
        candidates = candidates[:100]
        st.warning(f"Input truncated from {original_len} to 100 candidates to comply with sandbox specs.")

    # Run ranking
    with st.spinner("Executing ranking pipeline..."):
        results = rank_candidates(candidates, verbose=False, top_n=100)
    
    # Honeypot counts and general stats
    total_input = len(candidates)
    non_honeypots = len([r for r in results if not r[3].startswith("EXCLUDED:")])
    honeypots_count = total_input - non_honeypots

    # Layout metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f'<div class="metric-card"><div class="metric-lbl">Total Candidates Scored</div><div class="metric-val">{total_input}</div></div>',
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f'<div class="metric-card"><div class="metric-lbl">Honeypots Detected & Excluded</div><div class="metric-val">{honeypots_count}</div></div>',
            unsafe_allow_html=True
        )
    with col3:
        best_candidate = results[0][0] if results else "N/A"
        st.markdown(
            f'<div class="metric-card"><div class="metric-lbl">Top Candidate ID</div><div class="metric-val">{best_candidate}</div></div>',
            unsafe_allow_html=True
        )

    # Convert results to DataFrame for display
    df_data = []
    for cid, rank, score, reasoning in results:
        df_data.append({
            "Rank": rank,
            "Candidate ID": cid,
            "Score": f"{score:.4f}",
            "Reasoning": reasoning
        })
    df = pd.DataFrame(df_data)

    st.subheader("Ranked Candidates")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Generate CSV in memory for download
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["candidate_id", "rank", "score", "reasoning"])
    for cid, rank, score, reasoning in results:
        safe_reasoning = reasoning.replace("\n", " ").replace("\r", " ")
        writer.writerow([cid, rank, score, safe_reasoning])
    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    st.markdown("---")
    st.download_button(
        label="📥 Download submission.csv",
        data=csv_bytes,
        file_name="submission.csv",
        mime="text/csv",
        help="Download the valid CSV submission for the uploaded candidates."
    )
