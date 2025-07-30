from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
from flask_httpauth import HTTPBasicAuth # Import the library
import openai
# import spacy # Removed as it's not used
import sympy as sp
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app and HTTPAuth
app = Flask(__name__)
auth = HTTPBasicAuth()

# --- START OF AUTHENTICATION SETUP ---

# Create a dictionary of users and their passwords.
users = {
    "tester123": "JohnLeddo123123@",
    "tester321": "LeddoJohn321321@"
}

@auth.verify_password
def verify_password(username, password):
    """Checks if the provided username and password are valid."""
    if username in users and users.get(username) == password:
        return username

# --- END OF AUTHENTICATION SETUP ---


# Configure session to use filesystem
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'sessions')
Session(app)

# Set OpenAI API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("No OpenAI API key found. Make sure it's set in your .env file.")
openai.api_key = api_key
print("OpenAI API Key loaded successfully.") # Added for confirmation

# Function to analyze learning gaps
def analyze_math_gaps(topic, facts, strategies, procedures, rationales):
    gaps = []
    if len(facts.split()) < 10:
        gaps.append("Your mathematical facts are too brief. Add definitions and key formulas.")
    if len(strategies.split()) < 10:
        gaps.append("Your strategies lack depth. Explain different approaches to solving problems.")
    if len(procedures.split()) < 10:
        gaps.append("Your procedures are incomplete. Include step-by-step calculations.")
    if len(rationales.split()) < 10:
        gaps.append("Your rationales are unclear. Explain why these steps are necessary.")
    return gaps

# Function to verify math solutions using SymPy
def verify_math_solution(user_solution, correct_equation):
    try:
        user_expr = sp.sympify(user_solution)
        correct_expr = sp.sympify(correct_equation)
        return sp.simplify(user_expr - correct_expr) == 0
    except Exception as e:
        print(f"Error in verifying solution: {e}")
        return False

# Function to evaluate self-assessment using OpenAI (LLM)
def evaluate_math_self_assessment(topic, facts, strategies, procedures, rationales):
    gaps = analyze_math_gaps(topic, facts, strategies, procedures, rationales)

    prompt = f"""
    You are an expert math tutor analyzing a student's self-assessment on "{topic}". The student's responses are:

    - **Facts:** {facts}
    - **Strategies:** {strategies}
    - **Procedures:** {procedures}
    - **Rationales:** {rationales}

    Based on the given responses:
    1. **Identify the student's mistakes or missing concepts.** If a response lacks important details, highlight those gaps.
    2. **Correct misunderstandings explicitly.** If there is a factual error, provide the correct information.
    3. **Expand explanations with precise, structured guidance.** Use examples or alternative methods where applicable.
    4. **Do NOT repeat what the user already knows.** Only focus on missing knowledge.
    5. **If the student has written incomplete procedures or strategies, guide them to structure it properly.**
    6. **Ensure the feedback is actionable**—suggest specific study techniques or exercises to reinforce weak areas.
    7. **For mathematical proofs or equations, clarify errors and demonstrate correct reasoning.**

    Provide your response in a structured format:
    - **Identified Gaps**
    - **Corrections & Explanations**
    - **Suggested Improvements & Study Plan**
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a highly detailed math tutor who corrects mistakes and provides structured learning guidance."},
                      {"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=600
        )
        feedback = response.choices[0].message.content
    except Exception as e:
        feedback = f"Error fetching response from OpenAI: {e}"

    session['previous_context'] = {
        "topic": topic,
        "facts": facts,
        "strategies": strategies,
        "procedures": procedures,
        "rationales": rationales,
    }

    return {"gaps": gaps, "feedback": feedback}

# Route for the input form - NOW PROTECTED
@app.route('/')
@auth.login_required # This line protects the page
def index():
    return render_template("index.html")

# Route to process form input and display chatbot interface
@app.route('/evaluate', methods=['POST'])
@auth.login_required # Protect this route as well
def evaluate():
    topic = request.form['topic']
    facts = request.form['facts']
    strategies = request.form['strategies']
    procedures = request.form['procedures']
    rationales = request.form['rationales']

    result = evaluate_math_self_assessment(topic, facts, strategies, procedures, rationales)
    
    return render_template("evaluate.html", result=result, topic=topic)

# Route to handle chatbot follow-up questions
@app.route('/chat', methods=['POST'])
@auth.login_required # And this one
def chat():
    user_message = request.json.get("message")
    previous_context = session.get('previous_context', {})

    prompt = f"""
    The student is asking a follow-up question on "{previous_context.get('topic', 'Unknown Topic')}".
    Previous knowledge includes:
    - **Facts:** {previous_context.get('facts', '')}
    - **Strategies:** {previous_context.get('strategies', '')}
    - **Procedures:** {previous_context.get('procedures', '')}
    - **Rationales:** {previous_context.get('rationales', '')}

    **User Question:** {user_message}

    Provide a precise, correction-focused answer that:
    - **Identifies errors or misconceptions in the question.** - **Clarifies gaps in reasoning.**
    - **Uses structured, step-by-step explanations.**
    - **Does not repeat known information.**
    - **Suggests specific improvements.**
    - **Make sure to reply to the user's question based on their mathematic level, for example, if the student is at a basic level answer at a beginner level and if they are at advanced level, answer at an advanced level**
    - **State which level the student is at explicitly**
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a knowledgeable tutor correcting user mistakes and improving understanding."},
                      {"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=600
        )
        bot_response = response.choices[0].message.content
    except Exception as e:
        bot_response = f"Error fetching response: {e}"

    return jsonify({"response": bot_response})

# Run Flask app
if __name__ == '__main__':
    if not os.path.exists(app.config['SESSION_FILE_DIR']):
        os.makedirs(app.config['SESSION_FILE_DIR'])
    # Added use_reloader=False to prevent crashing in Spyder
    app.run(debug=True, use_reloader=False)
