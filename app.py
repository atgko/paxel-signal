import json
import os
import tempfile
import traceback
from datetime import date

# Use the OS trust store for TLS verification — some corporate/campus networks
# intercept HTTPS with a CA that's trusted by Windows but not by certifi's bundle.
import truststore

truststore.inject_into_ssl()

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Signal by Paxel",
    page_icon="💊",
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

st.markdown(
    """
    <div style='padding: 1.5rem 0 0.5rem 0;'>
        <h1 style='color: #00C2C7; font-size: 2rem; font-weight: 700;
                   letter-spacing: -0.5px; margin-bottom: 0;'>
            Signal <span style='color: #F0F0F0; font-weight: 300;'>by Paxel</span>
        </h1>
        <p style='color: #888888; font-size: 0.95rem; margin-top: 0.25rem;'>
            Turn every call into a clear next step.
        </p>
    </div>
    <hr style='border-color: #222222; margin: 0.5rem 0 1.5rem 0;'>
    """,
    unsafe_allow_html=True,
)


def _metric_card(value, label):
    st.markdown(
        f"""
        <div style='background: #141414; border: 1px solid #222222; border-radius: 8px;
                    padding: 1rem 1.5rem; display: inline-block; margin-right: 1rem;'>
            <div style='color: #00C2C7; font-size: 1.5rem; font-weight: 700;'>{value}</div>
            <div style='color: #888888; font-size: 0.8rem;'>{label}</div>
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
    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText(`{escaped}`)"
          style="background:#00C2C7; color:#0A0A0A; border:none; padding:0.4rem 1rem;
                 border-radius:4px; font-weight:600; cursor:pointer; font-size:0.875rem;">
          {label}
        </button>
        """,
        height=45,
    )


def _save_upload_to_temp(uploaded_file) -> str:
    suffix = os.path.splitext(uploaded_file.name)[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return tmp.name


st.write("Upload your transcript files to get started.")
st.write("Accepts Gemini-generated meeting notes in .docx or .txt format.")
st.write("You can upload multiple files at once.")

uploaded_files = st.file_uploader(
    "Transcript files", type=["docx", "txt"], accept_multiple_files=True
)

run_clicked = st.button("Run Analysis", disabled=not uploaded_files)

if run_clicked:
    extractor_outputs = []

    with st.spinner("Reading transcripts..."):
        pass

    for uploaded_file in uploaded_files:
        with st.spinner(f"Extracting insights from {uploaded_file.name}..."):
            tmp_path = None
            try:
                tmp_path = _save_upload_to_temp(uploaded_file)
                result = extract_insights(tmp_path, api_key=api_key)
            except TranscriptReadError:
                st.warning(f"⚠️ Could not read {uploaded_file.name} — skipping.")
                continue
            except Exception as e:
                st.error(f"Analysis failed: {e}")
                with st.expander(f"Debug details — {uploaded_file.name}"):
                    st.code(traceback.format_exc())
                continue
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        if not result.get("insights"):
            st.info(f"No insights found in {uploaded_file.name}.")
            continue

        extractor_outputs.append(result)

    if extractor_outputs:
        with st.spinner("Synthesizing patterns across all calls..."):
            synthesis = synthesize(extractor_outputs, api_key=api_key)
            matrix_df, top_df = build_needs_matrix(extractor_outputs)

        with st.spinner("Generating your weekly report..."):
            report_md, email_draft = generate_report(synthesis, matrix_df, api_key=api_key)

        st.session_state["results"] = {
            "extractor_outputs": extractor_outputs,
            "synthesis": synthesis,
            "matrix_df": matrix_df,
            "top_df": top_df,
            "report_md": report_md,
            "email_draft": email_draft,
        }
    else:
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

        dl_col, copy_col = st.columns([1, 1])
        with dl_col:
            st.download_button(
                "⬇️ Download Report",
                report_md,
                f"signal_report_{today_str}.md",
                "text/markdown",
            )
        with copy_col:
            _copy_button(report_md, "📋 Copy to Clipboard")

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
