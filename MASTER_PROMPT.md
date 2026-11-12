# SYSTEM CONTEXT
Act as an expert Full-Stack Developer specializing in React, FastAPI, PostgreSQL, and LLM integrations. Your task is to build a web application called "AI CV Optimizer."

# PROJECT OVERVIEW
The application allows users to upload their current CV, configure LLM API keys, and paste Job Descriptions (JDs). The app then uses the configured LLM to review the CV against the JD, provides Git-style diff suggestions (add/remove/update) to tailor the CV, scores the match, dynamically updates the score as users accept/reject suggestions, and finally generates a downloadable updated CV.

# TECH STACK
*   **Frontend**: React (Functional components, Hooks), Tailwind CSS (for styling), `react-diff-viewer` or custom CSS for Git-style diffs.
*   **Backend**: FastAPI (Python), Pydantic for validation.
*   **Database**: PostgreSQL, SQLAlchemy (ORM), Alembic (Migrations).
*   **LLM Integration**: LangChain or direct API calls supporting Claude, Ollama, and Opencode Cloud.
*   **CV Processing**: `pdfplumber` / `python-docx` for parsing uploads; `reportlab` or `python-docx` for final CV generation.

---

# CORE FEATURES & REQUIREMENTS

## 1. Onboarding & Settings
*   **User Setup**: Users must upload their base CV (PDF, DOCX, or TXT format). 
*   **Settings Page**: 
    *   Input fields for LLM API Keys (Claude, Ollama Cloud, Opencode Cloud).
    *   Input for an optional LinkedIn profile URL.
    *   Save these securely in the database associated with the user profile.

## 2. 'CV Review' Creation (Main Workflow)
*   **Input**: A form to paste a Job Description (text) OR provide a URL (backend needs to scrape text from the URL).
*   **Initial Processing**: 
    *   The backend sends the parsed JD and the user's base CV to the configured LLM.
    *   The LLM evaluates the match and returns an initial **Match Score (0-100%)**.
    *   The LLM generates specific, actionable suggestions.

## 3. Suggestion UI (Git-Style Diff)
*   The UI must present the LLM's suggestions in a format similar to GitHub/Gitlab pull requests.
*   **Categories**: 
    *   **Additions** (Green): Content to add to match JD keywords.
    *   **Deletions** (Red): Fluff or irrelevant information to remove.
    *   **Updates/Modifications** (Yellow/Split view): Rewording existing bullet points for better impact.
*   **Interactivity**: Every suggestion must have an `Accept` and `Reject` button.

## 4. Dynamic Scoring
*   Whenever a user clicks Accept or Reject on a suggestion, the frontend sends the updated "pending" CV state to the backend.
*   The backend triggers a lightweight LLM call (or uses a calculated heuristic if faster) to re-evaluate the CV against the JD.
*   The UI smoothly updates the Match Score gauge/number.

## 5. Finalize and Export
*   When the user is satisfied, they click an **"Apply / Finalize"** button.
*   The backend compiles the original CV with all *accepted* changes.
*   The LLM formats this into a cohesive, professional CV document.
*   The user is prompted to download the new CV (PDF or DOCX).

---

# DATABASE SCHEMA (PostgreSQL)
Please design SQLAlchemy models for the following:
1.  **User**: id, email, created_at
2.  **UserSettings**: user_id, claude_key, ollama_key, opencode_key, linkedin_url
3.  **BaseCV**: id, user_id, original_file_path, parsed_text, uploaded_at
4.  **JobDescription**: id, user_id, source_url, raw_text
5.  **CVReview**: id, user_id, base_cv_id, job_description_id, current_score, status (draft, finalized)
6.  **Suggestion**: id, cv_review_id, type (ADD, REMOVE, UPDATE), original_text, suggested_text, status (PENDING, ACCEPTED, REJECTED)

---

# LLM PROMPTING STRATEGY (Critical)
When generating the backend LLM service, ensure the system prompt enforces structured JSON output. 
*   **Suggestion Generation Prompt**: "You are an expert tech recruiter. Compare this CV to this Job Description. Provide a JSON array of suggestions with keys: `type` (ADD/REMOVE/UPDATE), `target_section` (e.g., Experience, Skills), `original_text` (if applicable), `suggested_text`, and `reasoning`."
*   **Scoring Prompt**: "Evaluate how well this CV matches this Job Description. Return ONLY a JSON object with a single key `score` containing an integer from 0 to 100."

---

# IMPLEMENTATION PHASES
Please execute the code generation in the following phases. Wait for my confirmation after each phase.

*   **Phase 1: Backend Setup & Database**
    *   Initialize FastAPI app, SQLAlchemy configuration, and PostgreSQL connection.
    *   Define all database models and Pydantic schemas.
*   **Phase 2: Settings & Document Parsing**
    *   Create endpoints for saving user settings (API keys).
    *   Create endpoint for uploading and parsing the base CV.
*   **Phase 3: LLM Integration & JD Processing**
    *   Implement the LangChain/LLM service router (switching between Claude/Ollama/Opencode).
    *   Create the endpoint to accept JD (URL or text), trigger the initial LLM review, generate suggestions, and save to DB.
*   **Phase 4: Frontend Setup & Review UI**
    *   Initialize React app. Create the Settings page and CV Upload component.
    *   Build the Main Review Dashboard displaying the Job Description and the Initial Score.
*   **Phase 5: Git-Diff UI & Dynamic Scoring**
    *   Build the Suggestion Card component with Git-style Add/Remove/Update visualizations.
    *   Wire up the Accept/Reject buttons to update the backend and trigger the dynamic scoring endpoint.
*   **Phase 6: Finalization & Export**
    *   Implement the backend logic to merge accepted changes and generate the final downloadable document (PDF/DOCX).
    *   Add the "Apply/Download" button to the frontend.

Start by acknowledging these instructions and proceeding with **Phase 1: Backend Setup & Database**.