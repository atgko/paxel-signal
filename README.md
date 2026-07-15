# Signal by Paxel
### Turn every call into a clear next step.

Signal automatically extracts product insights from your Paxel user research
transcripts and delivers a weekly priority report — so nothing important gets
buried in hours of recorded feedback.

## What It Does

Upload your Gemini-generated meeting notes. Signal reads every transcript,
identifies what your users are asking for, groups patterns across calls, and
produces a report you can act on in 5 minutes.

**Outputs:**
- Weekly priority report with the top 5 feature recommendations
- Needs matrix broken down by persona and request type
- Raw insights from every call, available to download

---

## One-Time Setup (~10 minutes)

### 1. Install Python 3.11+
Download from python.org/downloads. During installation, check "Add Python to PATH."

### 2. Get an Anthropic API Key
1. Go to console.anthropic.com
2. Sign in or create a free account
3. Click "API Keys" in the left sidebar
4. Click "Create Key" — give it any name (e.g., "Signal")
5. Copy the key — you will only see it once

### 3. Download Signal
Click the green "Code" button on GitHub and choose "Download ZIP."
Unzip the folder somewhere you can find it (e.g., your Desktop).

### 4. Open a terminal in the Signal folder
- **Mac:** Right-click the folder → "New Terminal at Folder"
- **Windows:** Open the folder → type `cmd` in the address bar → press Enter

### 5. Install dependencies
```
pip install -r requirements.txt
```

### 6. Add your API key
1. Find the file called `.env.example` in the folder
2. Make a copy of it and rename the copy to `.env`
3. Open `.env` with any text editor (Notepad, TextEdit)
4. Replace `your_key_here` with the API key you copied in step 2
5. Save the file

### 7. Run Signal
```
streamlit run app.py
```
A browser window will open automatically at `http://localhost:8501`.

---

## How to Use Signal

1. Click **Browse files** and select your transcript files (.docx or .txt)
2. You can select multiple files at once — hold Shift or Cmd/Ctrl to select several
3. Click **Run Analysis**
4. Wait 30–90 seconds depending on how many files you uploaded
5. Use the tabs to explore your results, then click any Download button to save

---

## Deploying to the Web (Optional)
If you want to access Signal from any browser without running it locally:

1. Push the project to a GitHub repository (make sure `.env` is in `.gitignore`)
2. Go to share.streamlit.io and sign in with GitHub
3. Click "New app" and select your repository
4. Under "Advanced settings," add your API key:
   - Key: `ANTHROPIC_API_KEY`
   - Value: your API key
5. Click Deploy — you'll get a URL you can bookmark

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "API key not found" | Make sure your `.env` file exists and the key is pasted correctly with no extra spaces |
| File won't upload | Only `.docx` and `.txt` files are supported |
| Analysis is slow | Normal for large batches — allow up to 2 minutes for 10+ files |
| Browser doesn't open | Manually go to `http://localhost:8501` |
| "Module not found" error | Run `pip install -r requirements.txt` again |

---

## What's Next: Full Automation

Signal currently works by uploading transcripts manually — you drag in your files, click Run, and get your report. That's intentional: a simple tool that reliably works is more valuable than a complex one that breaks.

But the workflow your team mapped out points toward something more powerful: a fully automated pipeline where a recorded call flows through the system end-to-end with no manual steps at all. Here is exactly what that would look like, and what it would take to build it.

---

**The Full Automated Vision**

```
Call recorded → Video lands in Google Drive →
Transcription runs automatically → Signal processes the transcript →
Weekly report emails itself to Luke every Friday
```

No uploads. No button clicks. Signal runs in the background and delivers insights on a schedule.

---

**What Needs to Be Added**

**1. Google Drive Watcher**

Signal would need to monitor a specific Google Drive folder (e.g., "Paxel Call Recordings") and detect when a new video file is added. This requires connecting to the Google Drive API using OAuth credentials from your Google Workspace account.

- Complexity: Medium
- Cost: Free (included in Google Workspace)
- Dependency: A Google Cloud project with Drive API enabled and OAuth credentials configured
- Implementation: A background polling script or a Google Apps Script trigger on the folder

**2. Automatic Transcription**

Once a new video is detected, it needs to be transcribed to text before Signal can process it. Three solid options:

| Option | Best for | Cost | Notes |
|---|---|---|---|
| **Gemini API** | Already in your Google ecosystem | Pay-per-use (~$0.002/min) | Native Google Drive integration possible |
| **AssemblyAI** | Accuracy + speaker labeling | ~$0.37/hour of audio | Best speaker diarization — knows who said what |
| **OpenAI Whisper** | Cost control, self-hosted | Free if self-hosted | Slightly more setup, no speaker labels out of the box |

AssemblyAI is the strongest recommendation for Paxel's use case because it automatically labels speakers (Drew, Sara, Luke, etc.), which is critical for correctly attributing insights by persona in Signal's extractor.

**3. A Scheduler**

Instead of a button click, the weekly report needs to run automatically on a cadence — for example, every Friday at 8am. This requires a hosting environment that supports scheduled jobs, not just a web server.

- **Easiest option:** GitHub Actions (free, runs on a schedule you define in a config file)
- **More control:** A small cloud VM (AWS EC2, Google Cloud Run, Railway.app) running a cron job
- **Streamlit limitation:** Streamlit Cloud alone cannot run scheduled jobs — you would need a separate scheduler that triggers the pipeline and then pushes results to a storage location Signal reads from

**4. Automated Email Delivery**

The weekly report currently downloads as a file. In the automated version, it emails itself to Luke (and anyone else on the list) every Friday morning.

- **SendGrid:** Free tier covers 100 emails/day — straightforward API integration
- **Gmail API:** Works directly from a Google account — slightly more setup with OAuth but keeps everything in Google's ecosystem
- The report markdown would be converted to HTML for a clean email rendering

---

**Recommended Build Sequence (Post-Class)**

If the Paxel team wants to extend Signal into a fully automated system, this is the suggested order:

1. Add AssemblyAI transcription — connect it to Signal's existing extractor so the pipeline accepts audio/video input instead of only .docx files. This is the highest-value addition.
2. Add the Google Drive watcher — poll the recordings folder every hour for new files and trigger transcription + extraction automatically when one appears.
3. Add the scheduler + email delivery — run the full pipeline every Friday morning and deliver the report to Luke's inbox.

Each step builds on the previous one and can be shipped independently. You do not need to build all three at once.

---

**Estimated Additional Effort**

| Addition | Estimated Build Time | Estimated Monthly Cost |
|---|---|---|
| AssemblyAI transcription | 1 day | ~$5–15 depending on call volume |
| Google Drive watcher | 1–2 days | Free |
| Scheduler (GitHub Actions) | Half day | Free |
| Email delivery (SendGrid) | Half day | Free |
| **Full automation** | **~3–4 days total** | **~$5–20/month** |

---

**What Signal Hands Off Today**

The student team is delivering a working tool that covers everything inside the orange box in your future-state workflow diagram — processing transcripts, organizing insights, building the needs matrix, and generating the weekly report. The Google Drive integration and automated scheduling sit outside that box and represent the next phase of development.

Signal is designed so those additions slot in cleanly. The extractor, synthesizer, and reporter are modular — swapping manual file upload for an automated Drive trigger requires changing the input layer only, not the core analysis logic.

---

*Built by Athavan Elangko, Brock Thompson, Daniel Reintjes, Jameson McCarty, Jason Kofoed, Kurtis Barth, Rob Sheehy · University of Utah Product Management · July 2026*
