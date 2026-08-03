import base64
import json
import os
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

# Use the OS trust store for TLS verification — some corporate/campus networks
# intercept HTTPS with a CA that's trusted by Windows but not by certifi's bundle.
import truststore

truststore.inject_into_ssl()

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

FAVICON_PATH = Path(__file__).resolve().parent / "assets" / "paxel_favicon.png"

st.set_page_config(
    page_title="Signal by Paxel",
    page_icon=str(FAVICON_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
)

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        st.error(
            """
            **API key not found.**
            Follow the setup instructions in README.md to add your Anthropic API key.
            """
        )
        st.stop()

from agent.extractor import TranscriptReadError, extract_insights
from agent.reporter import generate_report
from agent.synthesizer import build_needs_matrix, matrix_to_csv, synthesize

os.makedirs("outputs", exist_ok=True)

# Paxel brand palette, sourced directly from paxel.ai's compiled CSS/assets:
# primary purple (--Colors-Brand-700) and the signature icon gradient.
PAXEL_PURPLE = "#683ECC"
PAXEL_GRADIENT = "135deg, #683ECC 0%, #9030D3 66.35%, #C21FDB 100%"

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "paxel_logo.png"
LOGO_B64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Urbanist:wght@700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        font-family: 'Urbanist', sans-serif;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div style='display: flex; align-items: center; gap: 0.75rem; padding: 1.5rem 0 0.5rem 0;'>
        <div style='font-family: "Urbanist", sans-serif; font-size: 2rem; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 0;'>
            <span style='background: linear-gradient({PAXEL_GRADIENT});
                       -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                       background-clip: text;'>Signal</span> <span style='color: #98A2B3; font-weight: 300; font-size: 1.25rem;'>by</span>
        </div>
        <img src='data:image/png;base64,{LOGO_B64}' style='height: 26px; margin-top: 2px;' alt='Paxel'/>
    </div>
    <p style='color: #667085; font-size: 0.95rem; margin-top: 0.25rem;'>
        Turn every call into a clear next step.
    </p>
    <hr style='border-color: #E4DEF0; margin: 0.5rem 0 1.5rem 0;'>
    """,
    unsafe_allow_html=True,
)


def _metric_card(value, label):
    st.markdown(
        f"""
        <div style='background: #FFFFFF; border: 1px solid #E4DEF0; border-radius: 8px;
                    padding: 1rem 1.5rem; display: inline-block; margin-right: 1rem;'>
            <div style='color: {PAXEL_PURPLE}; font-size: 1.5rem; font-weight: 700;'>{value}</div>
            <div style='color: #667085; font-size: 0.8rem;'>{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _escape_for_clipboard_button(text: str) -> str:
    """Escape text for embedding in a backtick JS template literal inside a
    double-quoted HTML attribute (order matters: JS escaping, then HTML).
    Normalizes line endings first — Windows text-mode I/O upstream can
    reintroduce \\r\\n, which would otherwise get copied verbatim."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped = text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    escaped = escaped.replace("&", "&amp;").replace('"', "&quot;")
    return escaped


def _copy_button(text: str, label: str):
    escaped = _escape_for_clipboard_button(text)
    # Each st.components.v1.html call renders in its own iframe, so the
    # unqualified id is safe even with multiple copy buttons on the page.
    st.components.v1.html(
        f"""
        <button id="copyBtn" onclick="copyToClipboard()"
          style="background:linear-gradient({PAXEL_GRADIENT}); color:#FFFFFF; border:none;
                 padding:0.4rem 1rem; border-radius:6px; font-weight:600; cursor:pointer;
                 font-size:0.875rem; font-family:'Inter',sans-serif; transition: background 0.2s ease;">
          {label}
        </button>
        <script>
          const btn = document.getElementById("copyBtn");
          const originalLabel = {json.dumps(label)};
          const originalBackground = btn.style.background;
          let revertTimer = null;
          function copyToClipboard() {{
            navigator.clipboard.writeText(`{escaped}`);
            clearTimeout(revertTimer);
            btn.textContent = "✅ Copied!";
            btn.style.background = "#12B76A";
            revertTimer = setTimeout(() => {{
              btn.textContent = originalLabel;
              btn.style.background = originalBackground;
            }}, 1500);
          }}
        </script>
        """,
        height=45,
    )


# Fixed pacing for the progress-bar animation below. This has nothing to do
# with predicting how long anything takes — no duration is ever shown to the
# user — it just keeps the bar visibly moving while we wait, instead of
# sitting frozen at one value for several seconds.
_EASE_SECONDS = 7.0
_SOFT_CAP_RATIO = 0.92


def _ease_to(progress_bar, start_frac: float, end_frac: float, duration: float = 0.4, steps: int = 8):
    """Animates the bar from start_frac to end_frac over a short fixed
    duration. Used for steps with no real work to poll (reading, finalizing),
    so the jump still reads as motion instead of a sudden snap."""
    for i in range(1, steps + 1):
        progress_bar.progress(start_frac + (end_frac - start_frac) * (i / steps))
        time.sleep(duration / steps)


def _run_phase(fn, *args, progress_bar, start_frac: float, end_frac: float, **kwargs):
    """Runs fn in a background thread while easing the progress bar from
    start_frac toward a soft cap short of end_frac, so the bar keeps
    creeping forward for as long as fn is still running. Only snaps to
    end_frac once fn actually finishes — the cap is never reached early."""
    soft_cap = start_frac + (end_frac - start_frac) * _SOFT_CAP_RATIO
    phase_start = time.time()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args, **kwargs)
        while not future.done():
            elapsed = time.time() - phase_start
            progress_ratio = 1 - pow(0.5, elapsed / _EASE_SECONDS)
            progress_bar.progress(start_frac + (soft_cap - start_frac) * progress_ratio)
            time.sleep(0.2)
        result = future.result()

    progress_bar.progress(end_frac)
    return result


def _save_upload_to_temp(uploaded_file) -> str:
    suffix = os.path.splitext(uploaded_file.name)[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return tmp.name


st.write("Upload your transcript files to get started.")
st.write("Accepts meeting transcriptions in .docx or .txt format.")
st.write("You can upload multiple files at once.")

uploaded_files = st.file_uploader(
    "Transcript files", type=["docx", "txt"], accept_multiple_files=True
)

run_clicked = st.button("Run Analysis", disabled=not uploaded_files)

if run_clicked:
    extractor_outputs = []
    n_files = len(uploaded_files)

    progress_placeholder = st.empty()
    with progress_placeholder.container():
        progress_bar = st.progress(0.0)
        status = st.status("Reading transcript files...", expanded=False)

    _ease_to(progress_bar, 0.0, 0.05)

    for idx, uploaded_file in enumerate(uploaded_files, start=1):
        status.update(label=f"Extracting insights from {uploaded_file.name}...")
        start_frac = 0.05 + 0.60 * (idx - 1) / n_files
        end_frac = 0.05 + 0.60 * idx / n_files
        tmp_path = None
        try:
            tmp_path = _save_upload_to_temp(uploaded_file)
            result = _run_phase(
                extract_insights,
                tmp_path,
                api_key=api_key,
                progress_bar=progress_bar,
                start_frac=start_frac,
                end_frac=end_frac,
            )
        except TranscriptReadError:
            st.warning(f"⚠️ Could not read {uploaded_file.name} — skipping.")
            progress_bar.progress(end_frac)
            continue
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            with st.expander(f"Debug details — {uploaded_file.name}"):
                st.code(traceback.format_exc())
            progress_bar.progress(end_frac)
            continue
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if not result.get("insights"):
            st.info(f"No insights found in {uploaded_file.name}.")
            progress_bar.progress(end_frac)
            continue

        extractor_outputs.append(result)
        progress_bar.progress(end_frac)

    if extractor_outputs:
        status.update(label="Synthesizing patterns across all calls...")
        synthesis = _run_phase(
            synthesize,
            extractor_outputs,
            api_key=api_key,
            progress_bar=progress_bar,
            start_frac=0.65,
            end_frac=0.85,
        )

        matrix_df, top_df = build_needs_matrix(extractor_outputs)

        status.update(label="Generating your weekly report...")
        report_md, email_draft = _run_phase(
            generate_report,
            synthesis,
            matrix_df,
            api_key=api_key,
            progress_bar=progress_bar,
            start_frac=0.85,
            end_frac=0.95,
        )

        status.update(label="Finalizing outputs...")
        _ease_to(progress_bar, 0.95, 1.0)
        st.session_state["results"] = {
            "extractor_outputs": extractor_outputs,
            "synthesis": synthesis,
            "matrix_df": matrix_df,
            "top_df": top_df,
            "report_md": report_md,
            "email_draft": email_draft,
        }
        status.update(label="Finalizing outputs...", state="complete")

        progress_placeholder.empty()
    else:
        status.update(label="No transcripts could be processed.", state="error")
        progress_placeholder.empty()
        st.error("No transcripts could be processed.")
        st.session_state.pop("results", None)

if "results" in st.session_state:
    r = st.session_state["results"]
    extractor_outputs = r["extractor_outputs"]
    synthesis = r["synthesis"]
    matrix_df = r["matrix_df"]
    top_df = r["top_df"]
    report_md = r["report_md"]
    email_draft = r["email_draft"]

    total_insights = sum(len(o.get("insights", [])) for o in extractor_outputs)
    high_priority = sum(
        1
        for o in extractor_outputs
        for i in o.get("insights", [])
        if i.get("priority_signal") == "High"
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        _metric_card(len(extractor_outputs), "Transcripts Analyzed")
    with col2:
        _metric_card(total_insights, "Insights Extracted")
    with col3:
        _metric_card(high_priority, "High Priority Items")

    st.success("Analysis complete")

    tab_report, tab_matrix, tab_raw = st.tabs(
        ["📋 Weekly Report", "📊 Needs Matrix", "🔍 Raw Insights"]
    )

    today_str = date.today().isoformat()

    with tab_report:
        st.markdown(report_md)

        st.download_button(
            "⬇️ Download Report",
            report_md,
            f"signal_report_{today_str}.md",
            "text/markdown",
        )

        if email_draft:
            with st.expander("✉️ Email Draft — ready to send to your team"):
                st.caption(
                    "Copy this into Gmail, Outlook, or any mail app. Covers the top 3 priorities."
                )
                st.text_area("", email_draft, height=300, label_visibility="collapsed")
                _copy_button(email_draft, "📋 Copy Email to Clipboard")

    with tab_matrix:
        st.dataframe(matrix_df, use_container_width=True)
        st.download_button(
            "Download Matrix",
            matrix_to_csv(matrix_df),
            f"signal_matrix_{today_str}.csv",
            "text/csv",
        )

        st.subheader("Top Insight Per Cell")
        st.dataframe(top_df, use_container_width=True)

    with tab_raw:
        for output in extractor_outputs:
            title = output.get("call_title", "Untitled call")
            call_date = output.get("call_date", "Unknown")
            with st.expander(f"{title} — {call_date}"):
                st.markdown("**Key themes from this call:**")
                for theme in output.get("key_themes", []):
                    st.markdown(f"- {theme}")

                st.markdown("**Insights extracted:**")
                insights = output.get("insights", [])
                if insights:
                    insights_df = pd.DataFrame(
                        [
                            {
                                "Persona": i.get("persona"),
                                "Type": i.get("insight_type"),
                                "Priority": i.get("priority_signal"),
                                "Product Area": i.get("product_area"),
                                "Summary": i.get("summary"),
                            }
                            for i in insights
                        ]
                    )
                    st.dataframe(insights_df, use_container_width=True)
                else:
                    st.write("No insights extracted from this call.")

        all_insights_json = json.dumps(extractor_outputs, indent=2, ensure_ascii=False)
        st.download_button(
            "Download All Insights (JSON)",
            all_insights_json,
            f"signal_insights_{today_str}.json",
            "application/json",
        )
