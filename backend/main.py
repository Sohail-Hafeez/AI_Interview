import io
import os
import re
import json
import uuid

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from groq import Groq
from opentelemetry import trace

import db
from mcp_email_client import email_mcp_session, send_email_via_mcp

tracer = trace.get_tracer("ai-interview-backend")

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY missing from .env")

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

groq_client = Groq(api_key=GROQ_API_KEY)

TOTAL_QUESTIONS = 3
LLM_MODEL = "llama-3.1-8b-instant"
STT_MODEL = "whisper-large-v3-turbo"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", FRONTEND_BASE_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()
sessions = {}


def parse_json_response(content):
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.MULTILINE)
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        content = match.group(0)
    return json.loads(content)


def to_text(value):
    """LLM sometimes nests a value in a dict (e.g. {"question": "..."}) instead of
    returning a plain string. Unwrap it so the frontend always gets a string."""
    if isinstance(value, dict):
        for key in ("question", "next_question", "comment", "text"):
            if key in value and isinstance(value[key], str):
                return value[key]
        for v in value.values():
            if isinstance(v, str):
                return v
        return str(value)
    return value


def ask_llm(messages, retries=3):
    with tracer.start_as_current_span("llm.ask") as span:
        span.set_attribute("llm.model", LLM_MODEL)
        span.set_attribute("llm.max_retries", retries)

        last_error = None
        attempts = 0
        for _ in range(retries):
            attempts += 1
            response = groq_client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            try:
                result = parse_json_response(content)
                span.set_attribute("llm.attempts", attempts)
                span.set_attribute("llm.malformed_json_retries", attempts - 1)
                return result
            except json.JSONDecodeError as e:
                last_error = e

        span.set_attribute("llm.attempts", attempts)
        span.set_attribute("llm.malformed_json_retries", attempts)
        span.set_attribute("llm.exhausted_retries", True)
        span.record_exception(last_error)
        raise last_error


def build_system_prompt(role):
    return (
        f"You are a professional interviewer conducting a job interview for the '{role}' role. "
        f"You ask {TOTAL_QUESTIONS} questions total, one at a time, covering different relevant "
        "aspects of the role, from fundamentals to practical scenarios. "
        "Always respond with strict JSON only, no extra text before or after the JSON."
    )


def find_column(columns, *candidates):
    normalized = {c.strip().lower(): c for c in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def transcribe_audio(audio_bytes, filename, token=None):
    with tracer.start_as_current_span("stt.transcribe") as span:
        span.set_attribute("stt.model", STT_MODEL)
        span.set_attribute("audio.size_bytes", len(audio_bytes))
        if token:
            span.set_attribute("interview.token", token)

        transcription = groq_client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=STT_MODEL,
        )
        text = transcription.text.strip()
        span.set_attribute("transcript.length", len(text))
        return text


@app.post("/api/candidates/upload")
async def upload_candidates(file: UploadFile = File(...)):
    file_bytes = await file.read()

    try:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python")
        except Exception:
            raise HTTPException(400, "Could not parse the uploaded file as Excel or delimited text")

    name_col = find_column(df.columns, "name", "names", "full name", "candidate name")
    email_col = find_column(df.columns, "email", "emails", "email address")
    role_col = find_column(df.columns, "role", "roles", "position", "job role")

    if not name_col or not email_col or not role_col:
        raise HTTPException(400, "Sheet must have Name, Email, and Role columns")

    candidates = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        email = str(row[email_col]).strip()
        role = str(row[role_col]).strip()
        if not name or not email or not role:
            continue
        token = uuid.uuid4().hex
        db.insert_candidate(token, name, email, role)
        candidates.append({"token": token, "name": name, "email": email, "role": role})

    sent = []
    failed = []
    async with email_mcp_session() as session:
        for candidate in candidates:
            with tracer.start_as_current_span("email.send_invite") as span:
                span.set_attribute("interview.token", candidate["token"])
                span.set_attribute("interview.role", candidate["role"])

                link = f"{FRONTEND_BASE_URL}/interview/{candidate['token']}"
                subject = f"Interview Invitation - {candidate['role']}"
                body = (
                    f"Hi {candidate['name']},\n\n"
                    f"You've been invited to complete an AI interview for the {candidate['role']} role.\n"
                    f"Please open the link below when you're ready:\n\n{link}\n\n"
                    "Good luck!"
                )
                try:
                    await send_email_via_mcp(session, candidate["email"], subject, body)
                    sent.append(candidate["email"])
                    span.set_attribute("email.sent", True)
                except Exception as e:
                    failed.append({"email": candidate["email"], "error": str(e)})
                    span.set_attribute("email.sent", False)
                    span.record_exception(e)

    return {"total": len(candidates), "sent": sent, "failed": failed}


def compute_verdict(score):
    if score is None:
        return "-"
    if score < 5:
        return "Fail"
    if score >= 7:
        return "Pass"
    return "Pending"


@app.get("/api/candidates")
def list_candidates():
    candidates = db.get_all_candidates()
    for c in candidates:
        c["verdict"] = compute_verdict(c["score"])
    return candidates


@app.get("/api/candidates/export")
def export_candidates():
    candidates = db.get_all_candidates()
    for c in candidates:
        c["cheating"] = "Yes" if c.get("flags") else "No"
        c["verdict"] = compute_verdict(c["score"])
    df = pd.DataFrame(
        candidates,
        columns=["name", "email", "role", "score", "verdict", "status", "cheating", "flags"],
    )
    df.columns = [
        "Name",
        "Email",
        "Role",
        "Score",
        "Result",
        "Status",
        "Cheating",
        "Cheating Reason",
    ]

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=interview_results.xlsx"},
    )


@app.get("/api/candidates/{token}")
def get_candidate_info(token: str):
    candidate = db.get_candidate(token)
    if not candidate:
        raise HTTPException(404, "Invalid interview link")
    return candidate


@app.post("/api/mic-check")
async def mic_check(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    text = transcribe_audio(audio_bytes, audio.filename or "mic_check.webm")
    return {"transcript": text}


NETWORK_TEST_PAYLOAD = os.urandom(500 * 1024)


@app.get("/api/network-test-file")
def network_test_file():
    return StreamingResponse(
        io.BytesIO(NETWORK_TEST_PAYLOAD),
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/candidates/{token}/disqualify")
def disqualify_candidate(token: str, reason: str = Form(...)):
    span = trace.get_current_span()
    span.set_attribute("interview.token", token)
    span.set_attribute("disqualify.reason", reason)

    candidate = db.get_candidate(token)
    if not candidate:
        raise HTTPException(404, "Invalid interview link")
    span.set_attribute("interview.role", candidate["role"])
    db.set_candidate_score(token, 0, f"Disqualified: {reason}")
    db.update_candidate_status(token, "disqualified")
    return {"status": "disqualified"}


@app.post("/api/candidates/{token}/flag")
def flag_candidate(token: str, reason: str = Form(...)):
    span = trace.get_current_span()
    span.set_attribute("interview.token", token)
    span.set_attribute("flag.reason", reason)

    candidate = db.get_candidate(token)
    if not candidate:
        raise HTTPException(404, "Invalid interview link")
    db.add_flag(token, reason)
    return {"status": "flagged"}


@app.post("/api/candidates/{token}/start")
def start_interview(token: str):
    span = trace.get_current_span()
    span.set_attribute("interview.token", token)

    candidate = db.get_candidate(token)
    if not candidate:
        raise HTTPException(404, "Invalid interview link")
    if candidate["status"] == "completed":
        raise HTTPException(400, "This interview has already been completed")

    span.set_attribute("interview.role", candidate["role"])
    span.set_attribute("interview.total_questions", TOTAL_QUESTIONS)

    messages = [
        {"role": "system", "content": build_system_prompt(candidate["role"])},
        {
            "role": "user",
            "content": (
                f"Ask interview question number 1 of {TOTAL_QUESTIONS}. "
                'Respond as JSON: {"question": "..."}'
            ),
        },
    ]
    result = ask_llm(messages)
    messages.append({"role": "assistant", "content": json.dumps(result)})

    sessions[token] = {
        "question_number": 1,
        "messages": messages,
        "finished": False,
    }
    db.update_candidate_status(token, "in_progress")

    return {
        "question": to_text(result["question"]),
        "question_number": 1,
        "total_questions": TOTAL_QUESTIONS,
    }


@app.post("/api/candidates/{token}/answer")
async def submit_answer(token: str, audio: UploadFile = File(...)):
    span = trace.get_current_span()
    span.set_attribute("interview.token", token)

    session = sessions.get(token)
    if not session or session["finished"]:
        raise HTTPException(400, "Invalid or finished session")

    audio_bytes = await audio.read()
    transcript = transcribe_audio(audio_bytes, audio.filename or "answer.webm", token=token)

    question_number = session["question_number"]
    span.set_attribute("interview.question_number", question_number)
    is_last = question_number >= TOTAL_QUESTIONS

    if is_last:
        prompt = (
            f'The candidate answered: "{transcript}". '
            "Give a brief 1-2 sentence comment on this answer, then based on the "
            "entire interview so far, give an overall score out of 10 and a 2-3 "
            'sentence summary. Respond as JSON: {"comment": "...", "score": <number 0-10>, "summary": "..."}'
        )
    else:
        prompt = (
            f'The candidate answered: "{transcript}". '
            "Give a brief 1-2 sentence comment on this answer, then ask interview "
            f"question number {question_number + 1} of {TOTAL_QUESTIONS}. "
            'Respond as JSON: {"comment": "...", "next_question": "..."}'
        )

    session["messages"].append({"role": "user", "content": prompt})
    result = ask_llm(session["messages"])
    session["messages"].append({"role": "assistant", "content": json.dumps(result)})

    if is_last:
        session["finished"] = True
        summary = to_text(result["summary"])
        span.set_attribute("interview.final_score", result["score"])
        span.set_attribute("interview.completed", True)
        db.set_candidate_score(token, result["score"], summary)
        return {
            "transcript": transcript,
            "comment": to_text(result["comment"]),
            "score": result["score"],
            "summary": summary,
            "finished": True,
        }

    session["question_number"] += 1
    return {
        "transcript": transcript,
        "comment": to_text(result["comment"]),
        "question": to_text(result["next_question"]),
        "question_number": session["question_number"],
        "total_questions": TOTAL_QUESTIONS,
        "finished": False,
    }
