from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
import openai
import spacy
import sympy as sp
from sympy.core.sympify import SympifyError
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure session to use filesystem for storing session data
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'sessions')
Session(app)

# Load spaCy NLP model for any potential future text processing
nlp = spacy.load("en_core_web_sm")

# Set OpenAI API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("No OpenAI API key found. Make sure it's set in your .env file.")
openai.api_key = api_key

# Function to analyze learning gaps based on input length
def analyze_math_gaps(topic, facts, strategies, procedures, rationales):
    """Provides simple feedback based on the length of the user's input."""
    gaps = []
    if len(facts.split()) < 10:
        gaps.append("You can improve your mathematical facts by adding definitions, formulas, and theorems.")
    if len(strategies.split()) < 10:
        gaps.append("You can improve your strategies by explaining multiple approaches with step-by-step reasoning.")
    if len(procedures.split()) < 10:
        gaps.append("You can make your procedures more clear by providing a structured, logical breakdown of problem-solving steps.")
    if len(rationales.split()) < 10:
        gaps.append("You can add depth to your rationales by justifying why each step is necessary in the solution process.")
    return gaps

# Function to verify math solutions using SymPy
def verify_math_solution(user_solution, correct_equation):
    """
    Verifies if the user's solution equation is mathematically equivalent to the correct one.
    """
    try:
        # Safely convert string inputs into mathematical expressions
        # The original code had an error here; this is the corrected version.
        user_expr = sp.sympify(user_solution)
        correct_expr = sp.sympify(correct_equation)
        
        # Simplify the difference between the two expressions. If it's zero, they are equivalent.
        return sp.simplify(user_expr - correct_expr) == 0
    except (SympifyError, TypeError, SyntaxError) as e:
        # Catch errors if the input is not a valid mathematical expression
        print(f"Error in verifying solution: {e}")
        return False

# Function to evaluate the initial self-assessment using OpenAI
def evaluate_math_self_assessment(topic, facts, strategies, procedures, rationales):
    """Generates AI-powered feedback based on the user's self-assessment."""
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

    # Store the context in the session for follow-up questions
    session['previous_context'] = {
        "topic": topic,
        "facts": facts,
        "strategies": strategies,
        "procedures": procedures,
        "rationales": rationales,
    }

    return {"gaps": gaps, "feedback": feedback}

# Route for the main input form page
@app.route('/')
def index():
    return render_template("index.html")

# Route to process form and show the evaluation
@app.route('/evaluate', methods=['POST'])
def evaluate():
    # Get self-assessment data from the form
    topic = request.form['topic']
    facts = request.form['facts']
    strategies = request.form['strategies']
    procedures = request.form['procedures']
    rationales = request.form['rationales']

    # Get optional equation data for verification
    user_solution = request.form.get('user_solution')
    correct_equation = request.form.get('correct_equation')
    
    verification_result = None
    if user_solution and correct_equation:
        is_correct = verify_math_solution(user_solution, correct_equation)
        verification_result = "Correct!" if is_correct else "Incorrect. Let's review the steps to see where things went wrong."

    # Get the AI-generated feedback
    result = evaluate_math_self_assessment(topic, facts, strategies, procedures, rationales)
    
    return render_template("evaluate.html", result=result, topic=topic, verification=verification_result)

# Route to handle follow-up chat messages
@app.route('/chat', methods=['POST'])
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

# Run the Flask app
if __name__ == '__main__':
    # Ensure the session directory exists before starting
    if not os.path.exists(app.config['SESSION_FILE_DIR']):
        os.makedirs(app.config['SESSION_FILE_DIR'])
    app.run(debug=True)
