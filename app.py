import streamlit as st
import google.generativeai as genai
from vapi import Vapi
import re
import io
import PyPDF2
import docx

try:
    VAPI_SECRET_KEY = st.secrets["VAPI_SECRET_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    VAPI_PHONE_NUMBER_ID = st.secrets["VAPI_PHONE_NUMBER_ID"]
except KeyError:
    st.error("ERROR: Missing secrets! Please add VAPI_SECRET_KEY, GEMINI_API_KEY, and VAPI_PHONE_NUMBER_ID to your Streamlit secrets.")
    st.stop()

def extract_text_from_file(uploaded_file):
    if uploaded_file is None:
        return ""
    
    file_extension = uploaded_file.name.split(".")[-1].lower()
    text = ""
    
    try:
        if file_extension == "pdf":
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text += page.extract_text() or ""
        elif file_extension == "docx":
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        st.error(f"Error reading resume file: {e}")
        return ""
        
    return text

def generate_system_prompt_with_gemini(api_key, job_title, job_description, candidate_name, resume_text):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        You are an expert hiring manager and technical recruiter responsible for creating world-class, automated phone screen scripts for an AI interviewer named Alex.

        Your task is to generate a complete and precise `systemPrompt` for a voice-based AI interviewer named Alex. This `systemPrompt` will be fed directly into the Vapi API to configure the interviewer bot.

        The generated systemPrompt must instruct the AI interviewer (Alex) to:
        1.  **Introduction:** Start with a warm, professional greeting. Introduce itself as "Alex, an AI recruiting assistant," and clearly state the purpose of the call: a brief initial screening for the '{job_title}' position. Confirm the candidate's name is '{candidate_name}'.
        2.  **Core Questions (5-7 total):**
            *   **Resume-Specific Questions (1-2):** Generate 1-2 questions that DIRECTLY REFERENCE the candidate's experience listed on their resume and connect it to the requirements of the job description.
            *   **Technical/Experience Questions (2-3):** Generate questions directly related to the key skills in the job description that may not be covered by the resume questions.
            *   **Behavioral Question (1-2):** Generate questions (e.g., "Tell me about a time when...") to assess soft skills.
        3.  **Candidate Questions:** Provide a clear moment for the candidate to ask any questions they might have.
        4.  **Conclusion:** Politely conclude the interview, thank the candidate for their time, and clearly explain the next steps.
        5.  **Tone:** Maintain a friendly, engaging, and professional tone throughout.

        The output should be ONLY the system prompt text, ready to be used in the Vapi API.

        ---
        **Job Title:** {job_title}
        **Job Description:** {job_description}
        **Candidate Name:** {candidate_name}
        **Candidate's Resume Text:**
        {resume_text}
        ---
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error calling Gemini API: {e}")
        return None


st.set_page_config(layout="wide")
st.title("VAPI Phone Interview")

if 'prompt_generated' not in st.session_state: st.session_state.prompt_generated = False
if 'assistant_id' not in st.session_state: st.session_state.assistant_id = None
if 'call_result' not in st.session_state: st.session_state.call_result = None
if 'call_initiated' not in st.session_state: st.session_state.call_initiated = False
if 'candidate_phone_number' not in st.session_state: st.session_state.candidate_phone_number = ""

st.header("Interviewee Details")

with st.form("interview_details_form"):
    candidate_name = st.text_input("Candidate Name")
    candidate_phone_number_input = st.text_input("Candidate's Phone Number (e.g., +15551234567)")
    job_title = st.text_input("Job Title")
    job_description = st.text_area("Job Description", height=150)
    uploaded_resume = st.file_uploader("Upload Candidate's Resume (Optional, PDF or DOCX)", type=["pdf", "docx"])
    
    generate_button = st.form_submit_button("Generate Interview Prompt", use_container_width=True)

if generate_button:
    st.session_state.prompt_generated = False
    st.session_state.assistant_id = None
    st.session_state.call_result = None
    st.session_state.call_initiated = False
    st.session_state.candidate_phone_number = candidate_phone_number_input
    
    with st.spinner("Analyzing resume and generating interview script..."):
        resume_text = extract_text_from_file(uploaded_resume)
        if uploaded_resume and not resume_text:
            st.stop()
            
        system_prompt = generate_system_prompt_with_gemini(GEMINI_API_KEY, job_title, job_description, candidate_name, resume_text)
        if system_prompt:
            st.session_state.generated_prompt = system_prompt
            st.session_state.prompt_generated = True

if st.session_state.prompt_generated:
    st.markdown("---")
    st.header("Review Script & Start Phone Call")
    with st.form("create_and_call_form"):
        edited_prompt = st.text_area("Editable System Prompt", value=st.session_state.generated_prompt, height=600)
        start_call_button = st.form_submit_button(" Confirm Script & Start Phone Call", use_container_width=True)

    if start_call_button:
        try:
            vapi_client = Vapi(token=VAPI_SECRET_KEY)
            with st.spinner("Creating AI Interviewer..."):
                assistant_config = {
                    "name": f"Phone Interviewer for {candidate_name}",
                    "first_message": f"Hi {candidate_name}, this is Alex, the AI recruiting assistant. I'm calling for a brief screening for the {job_title} position. Is now a good time to chat?",
                    "model": {"provider": "openai", "model": "gpt-4o", "temperature": 0.5, "messages": [{"role": "system", "content": edited_prompt}]},
                    "voice": {"provider": "vapi", "voiceId": "Elliot"},
                    "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "en", "endpointing": 150},
                    "start_speaking_plan": {"waitSeconds": 0.4, "smart_endpointing_enabled": "livekit"},
                    "analysis_plan": {
                        "summaryPrompt": "You are a senior HR Manager...",
                        "structuredDataSchema": { "type": "object", "properties": { "overallRating": {"type": "number"}, "competencies": {"type": "object", "properties": {"technicalCommunication": {"type": "number"}, "clarityOfThought": {"type": "number"}, "professionalism": {"type": "number"}}}, "keyStrengths": {"type": "string"}, "areasForImprovement": {"type": "string"}, "finalRecommendation": {"type": "string"} }, "required": ["overallRating", "finalRecommendation"] },
                        "successEvaluationPrompt": "You are a hiring manager... Respond with only the word 'Success' or 'Failure'."
                    }
                }
                assistant = vapi_client.assistants.create(**assistant_config)
                st.session_state.assistant_id = assistant.id

            with st.spinner(f"Placing phone call to {st.session_state.candidate_phone_number}..."):
                call = vapi_client.calls.create(
                    phone_number_id=VAPI_PHONE_NUMBER_ID,
                    assistant_id=assistant.id,
                    customer={"number": st.session_state.candidate_phone_number}
                )
                st.session_state.call_initiated = True
                st.success(f"Call initiated successfully! The phone at {st.session_state.candidate_phone_number} should be ringing shortly. Call ID: `{call.id}`")

        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")

if st.session_state.call_initiated:
    st.markdown("---")
    st.header("Step 3: Get Interview Results")
    st.warning("After the phone call is finished, click the button below to fetch the analysis.")

    if st.button("Fetch Last Interview Result", use_container_width=True):
        with st.spinner("Searching for the last completed call..."):
            vapi_client = Vapi(token=VAPI_SECRET_KEY)
            calls = vapi_client.calls.list(assistant_id=st.session_state.assistant_id, limit=1)
            if calls:
                st.session_state.call_result = calls[0].dict()
            else:
                st.warning("No calls found for this assistant yet.")

if st.session_state.call_result:
    result = st.session_state.call_result
    st.markdown("---")
    st.header("Interview Analysis Report")

    analysis = result.get('analysis', {})
    if analysis:
        st.subheader("Summary")
        structured_data = analysis.get('structuredData', {})
        st.metric(label="Overall Rating", value=f"{structured_data.get('overallRating', 0)} / 10")
        st.metric(label="Recommendation", value=structured_data.get('finalRecommendation', 'N/A'))
        st.metric(label="Outcome", value=analysis.get('successEvaluation', 'N/A'))
        st.write("")
        st.write(analysis.get('summary', 'Summary not available.'))
        
        st.subheader("Detailed Evaluation")
        st.markdown("**Competency Ratings (out of 5):**")
        competencies = structured_data.get('competencies', {})
        
        def render_stars(rating, max_stars=5):
            try:
                rating = int(rating)
                return "★" * rating + "☆" * (max_stars - rating)
            except (ValueError, TypeError):
                return "N/A"

        for competency, rating in competencies.items():
            formatted_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', competency).title()
            st.markdown(f"- **{formatted_name}:** `{render_stars(rating)}` ({rating}/5)")
        
        st.write("")
        st.markdown(f"**Key Strengths:** {structured_data.get('keyStrengths', 'N/A')}")
        st.markdown(f"**Areas for Improvement:** {structured_data.get('areasForImprovement', 'N/A')}")
    
    elif result.get('status') != 'ended':
        st.warning(f"The call has not ended yet. Current status: `{result.get('status')}`. Please wait and try again.")
    else:
        st.warning("Analysis data not available. It may still be processing.")
        
    st.subheader("Full Call Transcript")
    with st.expander("Click to view full transcript"):
        transcript = result.get('transcript')
        if transcript:
            parts = re.split(r'(AI:|User:)', transcript)
            if parts and not parts[0].strip():
                parts = parts[1:]
            for i in range(0, len(parts), 2):
                speaker = parts[i].strip()
                dialogue = parts[i+1].strip()
                if speaker == "AI:":
                    st.markdown(f"**🤖 Alex (AI):** {dialogue}")
                elif speaker == "User:":
                    candidate_name_from_state = st.session_state.get('candidate_name', 'User')
                    st.markdown(f"**👤 {candidate_name_from_state} (User):** {dialogue}")
        else:
            st.write("Transcript not available.")