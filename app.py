# -----------------------------
# 1. Import libraries
# -----------------------------

from flask import Flask, render_template, request, redirect, session
from openai import OpenAI
import pymysql, wolframalpha, pymysql.cursors, os

# -----------------------------
# 2. Set API keys
# -----------------------------
client = OpenAI(api_key=os.getenv("openai_key"))
#might integrate wolframalpha later
#wolfram_client = wolframalpha.Client(os.getenv("wolfram_api_key"))

# -----------------------------
# 3. Create the Flask app
# -----------------------------
app = Flask(__name__)
app.secret_key = os.getenv("app_secret_key")

# -----------------------------
# 4. HELPER FUNCTIONS
# -----------------------------
def generate_problem(topic="arithmetic", difficulty="easy"):
    system_prompt = (
        "You are a helpful math tutor API. Generate a math question in the exact format below:\n\n"
        "Question: \\[ LaTeX formatted question \\]\n"
        "Expression: raw expression (what a math engine should evaluate)\n"
        "Answer: simplified final answer (number or expression only). If the answer is numeric, exclude any variables such as 'x=4 -> 4'\n\n"
        "Do NOT explain or describe anything."
    )

    if topic == "arithmetic":
        if difficulty == "easy":
            user_prompt = "Generate an easy arithmetic expression using +, -, × or ÷ (no parentheses)."
        elif difficulty == "medium":
            user_prompt = "Generate a medium arithmetic expression using +, -, ×, ÷ and parentheses."
        else:
            user_prompt = "Generate a hard arithmetic expression with nested parentheses and all four operations."

    elif topic == "algebra":
        if difficulty == "easy":
            user_prompt = "Generate an easy algebra problem solving for x with one step (e.g., x + 3 = 5). ENSURE THAT THE ANSWER DOES NOT INCLUDE 'x='."
        elif difficulty == "medium":
            user_prompt = "Generate a medium algebra problem with two steps (e.g., 2x + 3 = 11). ENSURE THAT THE ANSWER DOES NOT INCLUDE 'x='."
        else:
            user_prompt = "Generate a hard algebra problem involving parentheses and distribution (e.g., 2(x + 3) = 14). ENSURE THAT THE ANSWER DOES NOT INCLUDE 'x='."

    elif topic == "calculus":
        if difficulty == "easy":
            user_prompt = "Generate a basic calculus derivative or integral of a polynomial like x^2."
        elif difficulty == "medium":
            user_prompt = "Generate a medium difficulty derivative or integral involving trig functions or x^n."
        else:
            user_prompt = "Generate a hard calculus problem involving product rule, chain rule, or u-substitution."

    else:
        user_prompt = "Generate a math problem in LaTeX and its solution."


    user_prompt += (
        "\n\nREMEMBER: Do NOT explain. Do NOT include 'x=' in the answer. ONLY return the three labeled lines in the format:\n"
        "Question: \\[ ... \\]\n"
        "Expression: ...\n"
        "Answer: ...\n")

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    return response.choices[0].message.content


def extract_question_expression_answer(text):
    question = expression = answer = ""
    for line in text.splitlines():
        if line.startswith("Question:"):
            question = line.replace("Question:", "").strip()
        elif line.startswith("Expression:"):
            expression = line.replace("Expression:", "").strip()
        elif line.startswith("Answer:"):
            answer = line.replace("Answer:", "").strip()
            answer = clean_expression(answer)
    return question, expression, answer

# comeback to this and see if it works later
#
# def evaluate_expression(expression):
#     try:
#         # First try Python's eval
#         print("Trying eval()...")
#         print(expression)
#         return str(eval(expression))
#     except Exception as e:
#         print(f"eval failed: {e}. Trying Wolfram Alpha...")

#         try:
#             res = wolfram_client.query(expression)
#             print(res)
#             return next(res.results).text
#         except Exception as wolfram_error:
#             print(f"Wolfram Alpha failed: {wolfram_error}")
#             return "Could not solve"

def clean_expression(expr):
    return (
        expr.replace("$$", "")
            .replace("\\(", "")
            .replace("\\)", "")
            .replace("\\[", "")
            .replace("\\]", "")
            .replace(" ", "")
            .replace("x=", "")
            .strip()
    )

def generate_hint(question, expression):
    prompt = (
        f"You're a helpful math tutor. Give a hint (not the answer) "
        f"to help a student solve this math question:\n"
        f"Question: {question}\n"
        f"Expression: {expression}\n"
        f"Hint:"
    )
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful math tutor."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=60,
            temperature=0.5,
        )

        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        print("Error generating hint:", e)
        return "Hint generation failed. Try simplifying the problem."

# -----------------------------
# 5. Database Setup
# -----------------------------
def get_db_connection():
    return pymysql.connect(
        host=os.getenv("dbhost"),
        user=os.getenv("dbuser"),
        password=os.getenv("dbpassword"),
        db=os.getenv("dbname"),
        port=int(os.getenv("dbport")),
        ssl={"ssl": {}},
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL
        );
    """)

    # Create questions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            grade VARCHAR(20),
            topic VARCHAR(50),
            question TEXT,
            expression TEXT
        );
    """)
    
    #create progress table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            question TEXT,
            expression TEXT,
            user_answer TEXT,
            correct_answer TEXT,
            is_correct BOOLEAN,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            difficulty VARCHAR(10),       
            topic VARCHAR(50)
        );
    """)

    conn.commit()
    cursor.close()
    conn.close()

# -----------------------------
# 6. Flask Routes (register, login, dashboard, etc.)
# -----------------------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (user, pw))
            conn.commit()
        except:
            return "Username already exists"
        finally:
            c.close()
            conn.close()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = %s AND password = %s', (user, pw))
        result = c.fetchone()
        c.close()
        conn.close()
        if result:
            session['username'] = user
            return redirect('/dashboard')
        return "Invalid credentials"
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect('/login')

    if 'difficulty' not in session:
        session['difficulty'] = 'easy'

    # Step 1: If topic is chosen
    if request.method == 'POST' and 'topic' in request.form:
        session['topic'] = request.form['topic']
        problem_text = generate_problem(topic=session['topic'], difficulty=session['difficulty'])
        question, expression, answer = extract_question_expression_answer(problem_text)
        return render_template(
            'dashboard.html',
            user=session['username'],
            question=question,
            expression=expression,
            feedback=None,
            user_answer=None,
            correct_answer=answer,
            difficulty=session.get('difficulty', 'easy'),
            correct_streak=session.get('correct_streak', 0),
            wrong_streak=session.get('wrong_streak', 0)
)

    # Step 2: New question requested
    if request.method == 'POST' and request.form.get('new_question') == 'true':
        topic = session.get('topic', 'arithmetic')
        problem_text = generate_problem(topic=topic, difficulty=session['difficulty'])
        question, expression, answer = extract_question_expression_answer(problem_text)
        return render_template(
            'dashboard.html',
            user=session['username'],
            question=question,
            expression=expression,
            feedback=None,
            user_answer=None,
            correct_answer=answer,
            difficulty=session.get('difficulty', 'easy'),
            correct_streak=session.get('correct_streak', 0),
            wrong_streak=session.get('wrong_streak', 0)
        )


    # Step 2.5: Hint requested
    if request.method == 'POST' and request.form.get('get_hint') == 'true':
        question = request.form['question']
        expression = request.form['expression']
        correct_answer = request.form['correct_answer']

        # Check if hint already used for this question
        if session.get('hint_used') == question:
            hint = "Hint already used for this question."
        else:
            # Generate hint
            hint = generate_hint(question, expression)
            session['hint_used'] = question

        return render_template(
            'dashboard.html',
            user=session['username'],
            question=question,
            expression=expression,
            feedback=None,
            user_answer=None,
            correct_answer=correct_answer,
            difficulty=session.get('difficulty', 'easy'),
            correct_streak=session.get('correct_streak', 0),
            wrong_streak=session.get('wrong_streak', 0),
            hint=hint
        )


    # Step 3: Submitting an answer
    if request.method == 'POST' and 'answer' in request.form:
        user_answer = request.form['answer']
        question = request.form['question']
        expression = request.form['expression']
        correct_answer = request.form['correct_answer']
        topic = session.get('topic', 'arithmetic')



        is_correct = correct_answer.strip().lower() == user_answer.strip().lower()
        feedback = "✅ Correct!" if is_correct else f"❌ Incorrect. The correct answer is: {correct_answer}"

        # Adjust difficulty based on correctness streaks
        if is_correct:
            session['correct_streak'] = session.get('correct_streak', 0) + 1
            session['wrong_streak'] = 0
        else:
            session['wrong_streak'] = session.get('wrong_streak', 0) + 1
            session['correct_streak'] = 0

        # Scale difficulty up/down
        if session['correct_streak'] >= 3:
            if session['difficulty'] == 'easy':
                session['difficulty'] = 'medium'
            elif session['difficulty'] == 'medium':
                session['difficulty'] = 'hard'
        elif session['wrong_streak'] >= 2:
            if session['difficulty'] == 'hard':
                session['difficulty'] = 'medium'
            elif session['difficulty'] == 'medium':
                session['difficulty'] = 'easy'


        # Save to progress table
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO progress (username, question, expression, user_answer, correct_answer, is_correct, difficulty, topic)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (session['username'], question, expression, user_answer, correct_answer, is_correct, session['difficulty'], session['topic']))
        conn.commit()
        c.close()
        conn.close()

        return render_template(
            'dashboard.html',
            user=session['username'],
            question=question,
            expression=expression,
            feedback=feedback,
            user_answer=user_answer,
            correct_answer=correct_answer,
            difficulty=session.get('difficulty', 'easy'),
            correct_streak=session.get('correct_streak', 0),
            wrong_streak=session.get('wrong_streak', 0)
        )

    # Step 3.5: Override submitted
    if request.method == 'POST' and request.form.get('override') == 'true':
        question = request.form['question']
        expression = request.form['expression']
        user_answer = request.form['user_answer']
        correct_answer = request.form['correct_answer']

        # Override: treat it as correct
        is_correct = True
        feedback = "✅ Marked correct by student override."

        # Update most recent incorrect entry
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE progress
            SET is_correct = %s
            WHERE username = %s AND question = %s AND expression = %s AND is_correct = false
            ORDER BY timestamp DESC
            LIMIT 1
        """, (is_correct, session['username'], question, expression))
        conn.commit()
        c.close()
        conn.close()

        return render_template(
            'dashboard.html',
            user=session['username'],
            question=question,
            expression=expression,
            feedback=feedback,
            user_answer=user_answer,
            correct_answer=correct_answer,
            difficulty=session.get('difficulty', 'easy'),
            correct_streak=session.get('correct_streak', 0),
            wrong_streak=session.get('wrong_streak', 0)
        )

# Step 4: Initial GET (first visit)
    return render_template(
    'dashboard.html',
    user=session['username'],
    question=None,
    difficulty=session.get('difficulty', 'easy'),
    correct_streak=session.get('correct_streak', 0),
    wrong_streak=session.get('wrong_streak', 0)
    )


@app.route('/history')
def history():
    if 'username' not in session:
        return redirect('/login')

    conn = get_db_connection()
    c = conn.cursor()

    # Full history
    c.execute("""
        SELECT question, user_answer, correct_answer, is_correct, difficulty, topic, timestamp
        FROM progress
        WHERE username = %s
        ORDER BY timestamp DESC
    """, (session['username'],))
    full_history = c.fetchall()

    # Grouped accuracy by topic
    c.execute("""
        SELECT topic,
               COUNT(*) AS total,
               SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct,
               ROUND(100.0 * SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) / COUNT(*), 1) AS accuracy
        FROM progress
        WHERE username = %s
        GROUP BY topic
    """, (session['username'],))
    topic_summary = c.fetchall()

    # Accuracy over time (for chart)
    c.execute("""
        SELECT DATE(timestamp) as date,
               SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct,
               COUNT(*) AS total
        FROM progress
        WHERE username = %s
        GROUP BY DATE(timestamp)
        ORDER BY DATE(timestamp)
    """, (session['username'],))
    accuracy_over_time = c.fetchall()

    # Average difficulty level (convert to score)
    difficulty_score = {"easy": 1, "medium": 2, "hard": 3}
    c.execute("""
        SELECT difficulty FROM progress
        WHERE username = %s
    """, (session['username'],))
    difficulties = [row['difficulty'] for row in c.fetchall()]
    if difficulties:
        avg_score = round(sum(difficulty_score.get(d, 1) for d in difficulties) / len(difficulties), 2)
        if avg_score < 1.5:
            avg_difficulty = "Easy"
        elif avg_score < 2.5:
            avg_difficulty = "Medium"
        else:
            avg_difficulty = "Hard"
    else:
        avg_difficulty = "N/A"

    c.close()
    conn.close()

    return render_template(
        'history.html',
        user=session['username'],
        history=full_history,
        topic_summary=topic_summary,
        accuracy_over_time=accuracy_over_time,
        avg_difficulty=avg_difficulty
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')
