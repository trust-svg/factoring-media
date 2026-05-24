"""Top up questions to 25 per (grade, skill), guaranteeing no duplicate topics.

Strategy:
1. For each (grade, skill), read existing topic/prompt/question bodies from DB.
2. Pick topics from a curated pool that are NOT already present.
3. Generate via Claude with grade-aware prompts.
4. If pool exhausted, append a uniqueness hint to the prompt.
"""

import os, sys, random, time

sys.path.insert(0, "/app")
os.chdir("/app")

from app.db import SessionLocal
from app.models.question import Question
from app.services.ai_service import _get_anthropic, _safe_json_loads

TARGET = 25

# Curated, expanded topic pools (>=25 per grade/skill)
READING_TOPICS_COMMON = [
    "environmental conservation",
    "school clubs and activities",
    "travel and tourism",
    "technology in daily life",
    "healthy eating habits",
    "community volunteering",
    "animals and nature",
    "sports and fitness",
    "traditional festivals",
    "public transportation",
    "online shopping",
    "music and arts",
    "space exploration",
    "weather and climate",
    "library and reading",
    "recycling programs",
    "cultural exchange",
    "urban gardening",
    "youth entrepreneurship",
    "renewable energy",
    "Japanese tea ceremony",
    "high school memories",
    "summer vacation plans",
    "homestay experience",
    "school festival preparation",
    "family traditions",
    "weekend hobbies",
    "city versus countryside life",
    "earthquake preparedness",
    "national parks",
]

SPEAKING_TOPICS_PRE2 = [
    "Do you prefer studying alone or with friends?",
    "Do you think school uniforms are a good idea?",
    "Do you enjoy cooking at home?",
    "Do you prefer watching movies at home or at a cinema?",
    "Do you think it is important to learn a foreign language?",
    "Do you prefer city life or country life?",
    "Do you think sports are important for students?",
    "Do you prefer reading books or watching videos to learn?",
    "Do you think it is good to have a part-time job as a student?",
    "Do you prefer summer or winter?",
    "Do you think pets are good for families?",
    "Do you prefer shopping online or at stores?",
    "Do you think music lessons are important for children?",
    "Do you prefer waking up early or staying up late?",
    "Do you think it is important to recycle?",
    "Do you prefer travel by train or by car?",
    "Do you think students should join club activities?",
    "Do you prefer eating Japanese food or Western food?",
    "Do you enjoy taking pictures with your smartphone?",
    "Do you think Sunday should be a day for family?",
    "Do you prefer studying English in the morning or at night?",
    "Do you think children should help their parents at home?",
    "Do you prefer indoor sports or outdoor sports?",
    "Do you think it is good to keep a diary?",
    "Do you prefer visiting museums or amusement parks?",
    "Do you think it is important to greet your neighbors?",
]

SPEAKING_TOPICS_2 = [
    "Do you think artificial intelligence will change the way people work?",
    "Do you think remote work benefits employees more than companies?",
    "Do you agree that social media has a negative effect on young people?",
    "Do you think governments should invest more in renewable energy?",
    "Do you believe online education can replace traditional schooling?",
    "Do you think stricter laws are needed to reduce plastic waste?",
    "Do you agree that people today spend too much time on smartphones?",
    "Do you think tourism helps local communities more than it harms them?",
    "Do you believe it is important for companies to promote work-life balance?",
    "Do you think space exploration is worth the cost?",
    "Do you agree that cities should ban private cars in their centers?",
    "Do you think volunteering should be required for high school graduation?",
    "Do you believe healthy food should be made cheaper by the government?",
    "Do you think streaming services have improved or harmed the music industry?",
    "Do you agree that learning to code should be required in schools?",
    "Do you think automation will reduce the number of jobs in Japan?",
    "Do you agree that English should be the official second language of Japan?",
    "Do you think large companies should be required to plant trees?",
    "Do you believe schools should teach more about mental health?",
    "Do you think public libraries are still important in the digital age?",
    "Do you agree that universities should focus more on practical skills?",
    "Do you think bullet trains should be expanded to more regions?",
    "Do you believe e-sports should be treated like traditional sports?",
    "Do you think convenience stores have too much influence on daily life?",
    "Do you agree that the school year should start in September?",
    "Do you think Japan should welcome more foreign workers?",
]

WRITING_TOPICS_PRE2 = [
    "Do you think students should have homework every day?",
    "Do you think it is better to live in a big city or a small town?",
    "Do you think children should help with housework?",
    "Do you think students should use smartphones in class?",
    "Do you agree that exercise is important for students?",
    "Do you think it is good to have school on Saturdays?",
    "Do you think students should choose their own school subjects?",
    "Do you agree that watching TV is a waste of time?",
    "Do you think it is important to eat breakfast every day?",
    "Do you think zoos are good for animals?",
    "Do you agree that students should wear school uniforms?",
    "Do you think people should travel abroad at least once?",
    "Do you think it is better to learn music or sports as a child?",
    "Do you think students should work part-time while studying?",
    "Do you agree that online classes are better than classroom lessons?",
    "Do you think it is important to read newspapers?",
    "Do you agree that elementary school students should learn English?",
    "Do you think families should eat dinner together every day?",
    "Do you think keeping a pet teaches children responsibility?",
    "Do you agree that schools should plant more trees?",
    "Do you think students should learn cooking at school?",
    "Do you agree that bicycles are the best way to travel in a city?",
    "Do you think children should have more free time on weekends?",
    "Do you agree that learning a musical instrument is useful?",
    "Do you think it is good for students to use computers at home?",
    "Do you think school trips help students learn about culture?",
]

WRITING_TOPICS_2 = [
    "Do you think companies should allow employees to work from home?",
    "Do you agree that governments should ban single-use plastic?",
    "Do you think it is important for young people to learn about history?",
    "Do you agree that artificial intelligence will create more jobs than it destroys?",
    "Do you think social media does more harm than good?",
    "Do you agree that higher education should be free for everyone?",
    "Do you think it is necessary to have a car in modern society?",
    "Do you agree that countries should spend more money on space exploration?",
    "Do you think people should adopt a vegetarian diet?",
    "Do you agree that technology has made people less creative?",
    "Do you think cities should invest more in public transportation?",
    "Do you agree that famous people have a responsibility to be role models?",
    "Do you think international travel makes people more open-minded?",
    "Do you agree that nuclear energy should be used to fight climate change?",
    "Do you think sports stars deserve their high salaries?",
    "Do you agree that Japan should accept more immigrants to support its economy?",
    "Do you think university students should study abroad at least once?",
    "Do you agree that paper books are better than e-books?",
    "Do you think rural areas should receive more government support?",
    "Do you agree that working overtime should be illegal?",
    "Do you think traditional festivals are still important in modern Japan?",
    "Do you agree that schools should reduce the number of exams?",
    "Do you think volunteering abroad benefits both volunteers and host communities?",
    "Do you agree that streaming services have harmed the cinema industry?",
    "Do you think governments should put a higher tax on sugary drinks?",
    "Do you agree that learning more than one foreign language is necessary?",
]

# Listening: name + scenario diversity already handled by gen_listening2.py
LISTENING_NAMES = [
    "Tom",
    "Emma",
    "Mike",
    "Lisa",
    "David",
    "Anna",
    "Kevin",
    "Yuki",
    "Chris",
    "Maya",
    "Jake",
    "Mia",
    "Leo",
    "Chloe",
    "Ryan",
    "Hana",
    "Ben",
    "Nora",
    "Sam",
    "Ella",
    "Kai",
    "Amy",
    "Luke",
    "Rina",
]
LISTENING_SCENARIOS = [
    "at school",
    "at the library",
    "at a supermarket",
    "at a train station",
    "at a hospital",
    "in a park",
    "at work / in the office",
    "at a coffee shop",
    "at a travel agency",
    "at a post office",
    "at a sports club",
    "at home (phone call)",
    "at a bookstore",
    "at a doctor's office",
    "at a department store",
    "at a bus stop",
    "at a museum",
    "at a hotel front desk",
    "at a school cafeteria",
    "at a pharmacy",
    "on a school trip",
    "at a zoo",
]
LISTENING_QTYPES = [
    "Why",
    "What",
    "When",
    "Where",
    "How",
    "Who",
    "What time",
    "How many",
    "How long",
]


client = _get_anthropic()
db = SessionLocal()


def existing_bodies(grade: str, skill: str) -> set:
    """Return set of topic/prompt/question already present for this grade+skill."""
    rows = (
        db.query(Question)
        .filter(Question.grade == grade, Question.skill == skill)
        .all()
    )
    bodies = set()
    for q in rows:
        c = q.content or {}
        body = c.get("topic") or c.get("prompt") or c.get("question") or ""
        # Normalize: strip trailing "Write about NN words." for writing prompts
        if skill == "writing":
            for tail in (
                " Write about 50 words.",
                " Write about 80 words.",
                " Write about 80 to 100 words.",
            ):
                if body.endswith(tail):
                    body = body[: -len(tail)]
            # Cut everything from " Write about" onwards (catches grade-2 variants)
            idx = body.find(" Write about")
            if idx > 0:
                body = body[:idx]
        bodies.add(body.strip())
    return bodies


def gen_reading(grade_label: str, topic: str) -> dict:
    prompt = f"""Create one English reading comprehension question for EIKEN {grade_label} level.
Topic: {topic}

Return ONLY valid JSON (no markdown):
{{
  "passage": "English passage (120-160 words) about {topic}",
  "question": "one comprehension question in English",
  "choices": ["A", "B", "C", "D"],
  "answer": 0,
  "explanation": "explanation in Japanese (2-3 sentences)"
}}
answer = index 0-3 of the correct choice. Make all 4 choices plausible."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return _safe_json_loads(msg.content[0].text)


def gen_speaking(grade_label: str, topic: str) -> dict:
    points_pool = [
        ["Cost", "Convenience"],
        ["Health", "Environment"],
        ["Education", "Fun"],
        ["Time", "Social interaction"],
        ["Safety", "Freedom"],
        ["Tradition", "Modern lifestyle"],
        ["Economy", "Innovation"],
        ["Productivity", "Work-life balance"],
        ["Mental health", "Social connections"],
    ]
    points = random.choice(points_pool)
    prompt = f"""Create one EIKEN {grade_label} speaking question.

Topic: {topic}
Speaking points to use: {points[0]}, {points[1]}

Return ONLY valid JSON (no markdown):
{{
  "topic": "{topic}",
  "speaking_points": ["{points[0]}", "{points[1]}"],
  "time_limit_seconds": 60
}}"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return _safe_json_loads(msg.content[0].text)


def gen_writing_pre2(topic: str) -> dict:
    prompt = f"""Create one EIKEN Pre-2 writing question.
Topic: {topic}

Return ONLY valid JSON (no markdown):
{{
  "prompt": "{topic} Write about 50 words.",
  "min_words": 50,
  "example_response": "model answer in English (50-60 words) with clear opinion and two reasons"
}}"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return _safe_json_loads(msg.content[0].text)


def gen_writing_2(topic: str) -> dict:
    points = random.sample(
        [
            "Environment",
            "Economy",
            "Health",
            "Education",
            "Technology",
            "Society",
            "Convenience",
            "Safety",
            "Culture",
            "Future generations",
            "Cost",
            "Innovation",
        ],
        3,
    )
    prompt = f"""Create one EIKEN Grade 2 writing question.
Topic: {topic}
Use these three points: {points[0]}, {points[1]}, {points[2]}

Return ONLY valid JSON (no markdown):
{{
  "prompt": "{topic} Write about 80 to 100 words. Use TWO of the following POINTS: [{points[0]}] / [{points[1]}] / [{points[2]}]",
  "points": ["{points[0]}", "{points[1]}", "{points[2]}"],
  "min_words": 80,
  "example_response": "model answer in English (80-100 words) using two of the points"
}}"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return _safe_json_loads(msg.content[0].text)


def gen_listening(grade_label: str, used_pairs: set) -> tuple[dict, str, tuple]:
    for _ in range(20):
        name = random.choice(LISTENING_NAMES)
        scenario = random.choice(LISTENING_SCENARIOS)
        if (name, scenario) not in used_pairs:
            break
    q_type = random.choice(LISTENING_QTYPES)
    prompt = f"""Create one English listening comprehension question for EIKEN {grade_label} level.

REQUIRED (strictly follow):
- Main character: {name}  ← use ONLY this name
- Setting: {scenario}
- Question must start with: "{q_type}"
- Conversation/passage: 80-120 words. Use A:/B: format for dialogue, plain text for announcement/monologue.

Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "conversation": "text to be read aloud",
  "question": "{q_type} ...",
  "choices": ["A", "B", "C", "D"],
  "answer": 0,
  "explanation": "2-3 sentence explanation in Japanese"
}}
answer = index 0-3 of the correct choice."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _safe_json_loads(msg.content[0].text)
    return data, data.pop("conversation", None), (name, scenario)


PLANS = [
    ("pre2", "reading", READING_TOPICS_COMMON),
    ("2", "reading", READING_TOPICS_COMMON),
    ("pre2", "speaking", SPEAKING_TOPICS_PRE2),
    ("2", "speaking", SPEAKING_TOPICS_2),
    ("pre2", "writing", WRITING_TOPICS_PRE2),
    ("2", "writing", WRITING_TOPICS_2),
]

for grade, skill, topic_pool in PLANS:
    current = (
        db.query(Question)
        .filter(Question.grade == grade, Question.skill == skill)
        .count()
    )
    needed = max(0, TARGET - current)
    if needed == 0:
        print(f"[{grade}/{skill}]: already {current}, skip")
        continue
    print(f"[{grade}/{skill}]: have {current}, need {needed}")

    existing = existing_bodies(grade, skill)
    available = [t for t in topic_pool if t not in existing]
    random.shuffle(available)

    grade_label = "Pre-2" if grade == "pre2" else "Grade 2"
    made = 0
    for topic in available[:needed]:
        try:
            if skill == "reading":
                data = gen_reading(grade_label, topic)
                audio = None
            elif skill == "speaking":
                data = gen_speaking(grade_label, topic)
                audio = None
            elif skill == "writing":
                data = (
                    gen_writing_pre2(topic) if grade == "pre2" else gen_writing_2(topic)
                )
                audio = None
            db.add(
                Question(
                    grade=grade,
                    skill=skill,
                    source="ai_generated",
                    content=data,
                    audio_text=audio,
                )
            )
            db.commit()
            made += 1
            label = data.get("prompt", data.get("topic", data.get("question", "")))[:60]
            print(f"  +{made}/{needed}: {label}")
            time.sleep(0.3)
        except Exception as e:
            print(f"  FAIL ({topic!r}): {e}")
    if made < needed:
        print(f"  WARN: only {made}/{needed} generated (pool exhausted)")

# Listening — uses name+scenario seeding instead of topic list
for grade in ("pre2", "2"):
    current = (
        db.query(Question)
        .filter(Question.grade == grade, Question.skill == "listening")
        .count()
    )
    needed = max(0, TARGET - current)
    if needed == 0:
        print(f"[{grade}/listening]: already {current}, skip")
        continue
    print(f"[{grade}/listening]: have {current}, need {needed}")
    grade_label = "Pre-2" if grade == "pre2" else "Grade 2"
    # Pre-load existing (name, scenario)-ish keys is impractical (free text);
    # rely on random name+scenario rotation for variety.
    used = set()
    made = 0
    attempts = 0
    while made < needed and attempts < needed * 4:
        attempts += 1
        try:
            data, audio, pair = gen_listening(grade_label, used)
            used.add(pair)
            db.add(
                Question(
                    grade=grade,
                    skill="listening",
                    source="ai_generated",
                    content=data,
                    audio_text=audio,
                )
            )
            db.commit()
            made += 1
            print(
                f"  +{made}/{needed}: [{pair[0]} / {pair[1]}] {data.get('question', '')[:50]}"
            )
            time.sleep(0.3)
        except Exception as e:
            print(f"  FAIL: {e}")

db.close()
print("\nDone")
