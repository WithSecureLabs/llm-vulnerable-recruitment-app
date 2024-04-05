from flask import Flask, request, render_template, redirect, url_for, session, flash
import markdown
from openai import OpenAI
import subprocess
from dotenv import load_dotenv
import sqlite3
import os
from flask import g

import torch
from transformers import AutoModelForSequenceClassification
from transformers import AutoTokenizer

from prompt_injection_utils import detect_prompt_injection

DATABASE = "recruitment_demo.db"
MAX_CV_LENGTH = 2000
MAX_INPUT_LENGTH = 50

def get_boolean_env_var(var_name):
    value = os.getenv(var_name)
    return value.lower() in ['true', '1', 't', 'y', 'yes'] if value is not None else False

# Job spec for a Prompt Engineer
job_spec = """
**Job Specification for Prompt Engineer:**
We are seeking a talented and creative Prompt Engineer to join our team. The ideal candidate will have a knack for designing engaging and effective prompts that drive meaningful interactions with AI models.

- Strong skills in natural language processing and understanding.
- Experience in designing prompts for AI or chatbot applications.
- Ability to work collaboratively with cross-functional teams to refine AI outputs.
"""
load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

enable_prompt_injection_detection = get_boolean_env_var('ENABLE_PROMPT_INJECTION_DETECTION')

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "885a531b-36ee-4393-8706-f404eddaea51"

def run_bot():
    try:
        # The command to run
        command = ["node", "bot.js"]
        
        # Execute the command and wait for it to complete
        # subprocess.run is available in Python 3.5+
        result = subprocess.run(command, check=True, text=True, capture_output=True, timeout=120)  # Timeout set to 120 seconds (2 minutes)
        
        # If the command was successful, return its output
        return {'status': 'success', 'output': result.stdout}
    except subprocess.CalledProcessError as e:
        # If the command failed, return the error
        return {'status': 'error', 'output': e.stderr}
    except subprocess.TimeoutExpired:
        # If the command timed out, return a timeout message
        return {'status': 'error', 'output': 'Command timed out.'}


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Create the applications table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                email_address TEXT,
                phone_number TEXT,
                cv_text TEXT
            )
        """)
        # Check if the applications table is empty
        cursor.execute("SELECT COUNT(*) FROM applications")
        if cursor.fetchone()[0] == 0:  # If there are no rows in the table
            # Insert sample applications
            sample_applications = [
                ('user1', 'Jordan Smith', 'jordan.smith@email.com', '+44 1632 960712', 'Experienced in NLP and prompt design, with a strong background in computer science. Worked on various projects involving chatbot development and AI interaction enhancements. Passionate about creating intuitive AI interfaces.'),
                ('user2', 'Alex Johnson', 'alex.johnson@email.com', '+44 1632 960158','Creative prompt engineer with expertise in user engagement strategies and AI-driven content creation. Successfully implemented NLP solutions to improve user experience in tech startups. Eager to contribute to innovative AI applications.')
            ]
            cursor.executemany("INSERT INTO applications (username, full_name, email_address, phone_number, cv_text) VALUES (?,?, ?, ?, ?)", sample_applications)
        
        db.commit()



# Call this function to initialize the database
init_db()

# Hardcoded credentials
users = {
    "admin": {"username": "admin", "password": "admin123"},
    "candidate": {"username": "candidate", "password": "candidate123"},
}

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in users and users[username]["password"] == password:
            session["username"] = username
            # Check if the user is an admin and redirect to the admin view
            if username == "admin":
                return redirect(url_for("admin_view"))
            # Otherwise, redirect to the candidate dashboard
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    # Remove 'username' from session
    session.pop("username", None)
    # Redirect to login page
    return redirect(url_for("login"))


@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT full_name, email_address, phone_number, cv_text FROM applications WHERE username = ?", (session['username'],))
        application = cursor.fetchone()
        application_data = {
            'full_name': application[0], 
            'email_address': application[1], 
            'phone_number': application[2], 
            'cv_text': application[3]} if application else None

        return render_template('candidate_dashboard.html', application=application_data)
    return redirect(url_for('login'))

@app.route("/admin")
def admin_view():
    if "username" in session and session["username"] == "admin":
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT full_name, email_address, phone_number, cv_text FROM applications")
        apps = [{"full_name": row[0],  "email_address": row[1], "phone_number": row[2], "cv_text": row[3]} for row in cursor.fetchall()]

        # Create a chat prompt to evaluate applications against the job spec
        prompt = (
            f"{job_spec}\n\nHere are the applications:\n"
            + "\n".join([f"###{app['full_name']} (email:{app['email_address']}, phone:{app['phone_number']})\n{app['cv_text']}" for app in apps])
            + "\n\nBased on the job specification, just return the top application and provide a short one sentence summary in markdown format."
        )
        print(prompt)

        response = client.chat.completions.create(model="gpt-4-0125-preview",
        messages=[
            {
                "role": "system",
                "content": "You are an expert recruiter assistant. Your task is to evaluate job applications against the provided job specification for a Prompt Engineer position and select the top one based on their merits. You are concise, follow instructions and do not provide unoprompted long explanations, you just get to the task.",
            },
            {"role": "user", "content": prompt},
        ])

        # Assuming the response is formatted in Markdown
        summaries = (
            response.choices[0].message.content
            if response.choices
            else "No summary available."
        )
        html_summaries = markdown.markdown(summaries)

        return render_template("admin_view.html", summaries=html_summaries)
    return redirect(url_for("login"))

@app.route("/application", methods=["GET", "POST"])
def application():
    if "username" in session and session["username"] == "candidate":
        error_message = None  # Initialize an error message variable
        if request.method == "POST":
            username = session["username"]
            full_name = request.form["full_name"]
            email_address = request.form["email_address"]
            phone_number = request.form["phone_number"]
            cv_text = request.form["cv_text"]

            
            if enable_prompt_injection_detection and detect_prompt_injection(cv_text):
                error_message = f"CV contains a prompt injection ..."
         
            # Check character limits
            if len(full_name) > MAX_INPUT_LENGTH:
                error_message = f"Full name must not exceed {MAX_INPUT_LENGTH} characters."
            if len(email_address) > MAX_INPUT_LENGTH:
                error_message = f"Email address must not exceed {MAX_INPUT_LENGTH} characters."
            if len(phone_number) > MAX_INPUT_LENGTH:
                error_message = f"Phone number must not exceed {MAX_INPUT_LENGTH} characters."
            elif len(cv_text) > MAX_CV_LENGTH:
                error_message = f"CV text must not exceed {MAX_CV_LENGTH} characters."

            if not error_message:
                db = get_db()
                cursor = db.cursor()
                cursor.execute(
                    "SELECT id FROM applications WHERE username = ?", (username,)
                )
                application = cursor.fetchone()
                if application:
                    cursor.execute(
                        "UPDATE applications SET full_name = ?, email_address = ?, phone_number = ?, cv_text = ? WHERE username = ?",
                        (full_name, email_address, phone_number, cv_text, username),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO applications (username, full_name, email_address, phone_number, cv_text) VALUES (?, ?, ?, ?, ?)",
                        (username, full_name, email_address, phone_number, cv_text),
                    )
                db.commit()
                return redirect(url_for("dashboard"))
            else:
                # Pass the error message to the template if character limits are exceeded
                return render_template("application_form.html", error=error_message, application={'full_name': full_name, 
                'email_address': email_address, 'phone_number': phone_number, 'cv_text': cv_text})

        # Fetch existing application to pre-fill the form for editing
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT full_name, email_address, phone_number, cv_text FROM applications WHERE username = ?", (session["username"],)
        )
        application = cursor.fetchone()
        application_data = {'full_name': application[0], 'email_address': application[1], 'phone_number': application[2], 'cv_text': application[3]} if application else None
        return render_template("application_form.html", application=application_data)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0")
