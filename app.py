import os
import asyncio
import random
import secrets
import re
from datetime import datetime, timedelta, date

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, abort,
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user,
)
from werkzeug.security import generate_password_hash

from models import (
    db, User, School, Class, TeacherStudent, StudentParent,
    Schedule, Homework, Grade, Reminder, ChatMessage,
)
from ai import ask_ai

load_dotenv()

# ===== НАСТРОЙКИ =====
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты полезный и дружелюбный ассистент. Отвечай кратко и по делу.",
)
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))

SUBJECTS = [
    "Русский", "Литература", "Татарский", "Английский",
    "Алгебра", "Геометрия", "Теория вероятности",
    "Математический практикум", "Информатика", "История",
    "Обществознание", "География", "Физика", "Химия", "Биология",
    "Физкультура", "ОБЖ", "Черчение", "ПРОЕКТ",
]

DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

CUISINES = [
    "🍝 Итальянская: паста карбонара, пицца Маргарита, тирамису",
    "🥟 Русская: борщ, пельмени, компот",
    "🍣 Японская: суши, роллы, мисо-суп",
    "🍖 Кавказская: шашлык, хачапури, лаваш",
    "🌮 Мексиканская: тако, бурито, гуакамоле",
    "🍜 Китайская: лапша вок, дим-самы, чай",
    "🥐 Французская: круассаны, луковый суп, рататуй",
    "🍛 Индийская: карри, наан, рис басмати",
    "🥙 Греческая: гирос, салат хориатики",
    "🍔 Американская: бургер, картошка, милкшейк",
]

MODE_TITLES = {"student": "🎓 Ученик", "parent": "👨‍👩‍👧 Родитель", "teacher": "👩‍🏫 Учитель"}

# ===== ИНИЦИАЛИЗАЦИЯ =====
app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///school.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


# ===== УТИЛИТЫ =====
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gen_code(n: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


def unique_code(model, field):
    for _ in range(50):
        c = gen_code()
        if not model.query.filter_by(**{field: c}).first():
            return c
    return gen_code(8)


def parse_grades(text: str) -> list[float]:
    parts = re.split(r"[,\s;]+", (text or "").strip())
    out = []
    for p in parts:
        if not p:
            continue
        try:
            v = float(p.replace(",", "."))
        except ValueError:
            continue
        if 2 <= v <= 5:
            out.append(v)
    return out


def round_school(x: float) -> int:
    import math
    return math.floor(x + 0.4)


def avg_of(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def encouragement(avg: float) -> str:
    if avg >= 4.5:
        return "🌟 Ты просто звезда! Так держать!"
    if avg >= 4.0:
        return "👏 Отличный результат, ты молодец!"
    if avg >= 3.5:
        return "💪 Хороший темп! Продолжай стараться."
    return "🌱 Не сдавайся! У тебя всё получится."


def days_before(user_id: int) -> dict:
    rows = Schedule.query.filter_by(user_id=user_id).all()
    return {r.day: r.content for r in rows}


def my_school() -> School | None:
    if not current_user.is_authenticated:
        return None
    if current_user.school_id:
        return db.session.get(School, current_user.school_id)
    return School.query.filter_by(director_id=current_user.id).first()


# ===== АВТОРИЗАЦИЯ =====
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()

        if not username or not password:
            flash("Заполни логин и пароль", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Такой логин уже занят", "error")
            return redirect(url_for("register"))

        u = User(
            username=username,
            full_name=full_name or username,
            teacher_code=unique_code(User, "teacher_code"),
            student_code=unique_code(User, "student_code"),
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

        login_user(u)
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = User.query.filter_by(username=username).first()
        if not u or not u.check_password(password):
            flash("Неверный логин или пароль", "error")
            return redirect(url_for("login"))
        login_user(u)
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ===== ГЛАВНАЯ =====
@app.route("/")
@login_required
def index():
    return render_template(
        "chat.html",
        mode_title=MODE_TITLES.get(current_user.mode, current_user.mode),
    )


# ===== AI-ЧАТ =====
@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    text = (request.json or {}).get("message", "").strip()
    if not text:
        return jsonify({"error": "Пустое сообщение"}), 400

    # сохраняем сообщение пользователя
    db.session.add(ChatMessage(user_id=current_user.id, role="user", content=text))
    db.session.commit()

    # собираем историю
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    rows = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.id.desc())
        .limit(MAX_HISTORY)
        .all()
    )
    for r in reversed(rows):
        history.append({"role": r.role, "content": r.content})

    try:
        answer = asyncio.run(ask_ai(history))
    except Exception as e:
        answer = f"⚠️ Ошибка AI: {e}"

    db.session.add(ChatMessage(user_id=current_user.id, role="assistant", content=answer))
    db.session.commit()

    return jsonify({"answer": answer})


@app.route("/api/chat/history")
@login_required
def api_chat_history():
    rows = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return jsonify([{"role": r.role, "content": r.content} for r in rows])


@app.route("/api/chat/reset", methods=["POST"])
@login_required
def api_chat_reset():
    ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


# ===== ПРОФИЛЬ =====
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        new_mode = request.form.get("mode")
        if new_mode in MODE_TITLES:
            current_user.mode = new_mode
            db.session.commit()
            flash(f"Режим: {MODE_TITLES[new_mode]}", "ok")
        return redirect(url_for("profile"))

    school = my_school()
    classes = []
    if school:
        classes = [c.name for c in school.classes]

    return render_template(
        "profile.html",
        school=school,
        classes=classes,
        mode_title=MODE_TITLES.get(current_user.mode, current_user.mode),
    )


@app.route("/profile/class", methods=["POST"])
@login_required
def set_class():
    school = my_school()
    cls_name = request.form.get("class_name", "").strip()
    if not school:
        flash("Сначала вступите в школу", "error")
        return redirect(url_for("profile"))
    c = Class.query.filter_by(school_id=school.id, name=cls_name).first()
    if not c:
        flash("Класс не найден", "error")
        return redirect(url_for("profile"))
    current_user.class_id = c.id
    db.session.commit()
    flash(f"Класс: {c.name}", "ok")
    return redirect(url_for("profile"))


# ===== РАСПИСАНИЕ =====
@app.route("/schedule", methods=["GET", "POST"])
@login_required
def schedule():
    if request.method == "POST":
        day = request.form.get("day")
        content = request.form.get("content", "").strip()
        if day in DAYS and content:
            row = Schedule.query.filter_by(user_id=current_user.id, day=day).first()
            if row:
                row.content = content
            else:
                db.session.add(Schedule(user_id=current_user.id, day=day, content=content))
            db.session.commit()
            flash(f"Сохранено на {day}", "ok")
        return redirect(url_for("schedule"))

    rows = {r.day: r.content for r in Schedule.query.filter_by(user_id=current_user.id).all()}
    return render_template("schedule.html", days=DAYS, rows=rows)


@app.route("/schedule/clear", methods=["POST"])
@login_required
def schedule_clear():
    Schedule.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash("Расписание очищено", "ok")
    return redirect(url_for("schedule"))


# ===== ОЦЕНКИ =====
@app.route("/grades", methods=["GET", "POST"])
@login_required
def grades():
    if request.method == "POST":
        subject = request.form.get("subject")
        text = request.form.get("grades", "")
        values = parse_grades(text)
        if subject in SUBJECTS and values:
            for v in values:
                db.session.add(Grade(user_id=current_user.id, subject=subject, value=v))
            db.session.commit()
            flash(f"Добавлено {len(values)} оценок по «{subject}»", "ok")
        else:
            flash("Проверь предмет и оценки (2–5)", "error")
        return redirect(url_for("grades"))

    rows = Grade.query.filter_by(user_id=current_user.id).all()
    per_subj: dict[str, list[float]] = {}
    for r in rows:
        per_subj.setdefault(r.subject, []).append(r.value)

    summary = {}
    all_vals = []
    for s, vals in per_subj.items():
        summary[s] = {
            "count": len(vals),
            "avg": avg_of(vals),
            "rounded": round_school(avg_of(vals)),
        }
        all_vals += vals

    overall = avg_of(all_vals)
    return render_template(
        "grades.html",
        subjects=SUBJECTS,
        summary=summary,
        overall=overall,
        overall_rounded=round_school(overall),
        encouragement=encouragement(overall),
    )


@app.route("/grades/calc", methods=["POST"])
@login_required
def grades_calc():
    values = parse_grades(request.form.get("grades", ""))
    if not values:
        flash("Не удалось распознать оценки", "error")
        return redirect(url_for("grades"))
    avg = avg_of(values)
    flash(
        f"Средний: {avg:.2f}, округлённо: {round_school(avg)}. "
        f"{encouragement(avg)}",
        "ok",
    )
    return redirect(url_for("grades"))


@app.route("/grades/delete/<int:gid>", methods=["POST"])
@login_required
def grade_delete(gid):
    g = Grade.query.filter_by(id=gid, user_id=current_user.id).first()
    if g:
        db.session.delete(g)
        db.session.commit()
    return redirect(url_for("grades"))


# ===== ДОМАШКА =====
@app.route("/homework", methods=["GET", "POST"])
@login_required
def homework():
    school = my_school()
    if not school:
        return render_template("homework.html", items=[], school=None, subjects=SUBJECTS, classes=[])

    if request.method == "POST":
        if current_user.mode != "teacher":
            flash("Только учитель может добавлять ДЗ", "error")
            return redirect(url_for("homework"))
        cls_name = request.form.get("class_name")
        subject = request.form.get("subject")
        text = request.form.get("text", "").strip()
        c = Class.query.filter_by(school_id=school.id, name=cls_name).first()
        if not c or subject not in SUBJECTS or not text:
            flash("Проверь данные", "error")
            return redirect(url_for("homework"))
        db.session.add(Homework(
            school_id=school.id, class_id=c.id,
            subject=subject, text=text, author_id=current_user.id,
        ))
        db.session.commit()
        flash("ДЗ добавлено", "ok")
        return redirect(url_for("homework"))

    query = Homework.query.filter_by(school_id=school.id)
    if current_user.mode != "teacher" and current_user.class_id:
        query = query.filter_by(class_id=current_user.class_id)
    items = query.order_by(Homework.created_at.desc()).all()

    classes = [c.name for c in school.classes]
    return render_template(
        "homework.html", items=items, school=school, subjects=SUBJECTS, classes=classes,
    )


@app.route("/homework/delete/<int:hid>", methods=["POST"])
@login_required
def homework_delete(hid):
    if current_user.mode != "teacher":
        abort(403)
    h = Homework.query.get_or_404(hid)
    db.session.delete(h)
    db.session.commit()
    return redirect(url_for("homework"))


# ===== НАПОМИНАНИЯ =====
@app.route("/reminders", methods=["GET", "POST"])
@login_required
def reminders():
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        when_str = request.form.get("when", "").strip()
        dt = None
        try:
            dt = datetime.fromisoformat(when_str)
        except Exception:
            pass
        if not text or not dt:
            flash("Укажи текст и корректное время", "error")
            return redirect(url_for("reminders"))
        db.session.add(Reminder(user_id=current_user.id, text=text, when=dt))
        db.session.commit()
        flash("Напоминание добавлено", "ok")
        return redirect(url_for("reminders"))

    now = datetime.now()
    items = (
        Reminder.query
        .filter_by(user_id=current_user.id)
        .order_by(Reminder.when.asc())
        .all()
    )
    return render_template("reminders.html", items=items, now=now)


@app.route("/reminders/delete/<int:rid>", methods=["POST"])
@login_required
def reminder_delete(rid):
    r = Reminder.query.filter_by(id=rid, user_id=current_user.id).first()
    if r:
        db.session.delete(r)
        db.session.commit()
    return redirect(url_for("reminders"))


@app.route("/api/reminders/due")
@login_required
def api_reminders_due():
    now = datetime.now()
    rows = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.when <= now,
        Reminder.notified == False,
    ).all()
    out = []
    for r in rows:
        r.notified = True
        out.append({"id": r.id, "text": r.text})
    db.session.commit()
    return jsonify(out)


# ===== ШКОЛА =====
@app.route("/school")
@login_required
def school_page():
    school = my_school()
    return render_template("school.html", school=school)


@app.route("/school/create", methods=["POST"])
@login_required
def school_create():
    if current_user.mode == "student":
        flash("Ученик не может создать школу", "error")
        return redirect(url_for("school_page"))
    if my_school():
        flash("У вас уже есть школа", "error")
        return redirect(url_for("school_page"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("Введите название", "error")
        return redirect(url_for("school_page"))
    code = unique_code(School, "code")
    s = School(name=name[:100], code=code, director_id=current_user.id)
    db.session.add(s)
    db.session.commit()
    current_user.school_id = s.id
    # создать стандартные классы
    for g in range(1, 12):
        for l in ["А", "Б", "В"]:
            db.session.add(Class(school_id=s.id, name=f"{g}{l}"))
    db.session.commit()
    flash(f"Школа «{s.name}» создана. Код: {s.code}", "ok")
    return redirect(url_for("school_page"))


@app.route("/school/join", methods=["POST"])
@login_required
def school_join():
    code = request.form.get("code", "").strip().upper()
    s = School.query.filter_by(code=code).first()
    if not s:
        flash("Школа не найдена", "error")
        return redirect(url_for("school_page"))
    current_user.school_id = s.id
    # если класса ещё нет — назначить первый
    if not current_user.class_id and s.classes:
        current_user.class_id = s.classes[0].id
    db.session.commit()
    flash(f"Вы вступили в «{s.name}»", "ok")
    return redirect(url_for("school_page"))


@app.route("/school/class/add", methods=["POST"])
@login_required
def school_class_add():
    s = School.query.filter_by(director_id=current_user.id).first()
    if not s:
        abort(403)
    name = request.form.get("name", "").strip()[:20]
    if not name:
        flash("Пустое название", "error")
        return redirect(url_for("school_page"))
    if Class.query.filter_by(school_id=s.id, name=name).first():
        flash("Такой класс уже есть", "error")
        return redirect(url_for("school_page"))
    db.session.add(Class(school_id=s.id, name=name))
    db.session.commit()
    return redirect(url_for("school_page"))


@app.route("/school/class/delete/<int:cid>", methods=["POST"])
@login_required
def school_class_delete(cid):
    s = School.query.filter_by(director_id=current_user.id).first()
    if not s:
        abort(403)
    c = Class.query.filter_by(id=cid, school_id=s.id).first()
    if c:
        # сбросить класс у пользователей
        User.query.filter_by(class_id=c.id).update({"class_id": None})
        db.session.delete(c)
        db.session.commit()
    return redirect(url_for("school_page"))


@app.route("/school/delete", methods=["POST"])
@login_required
def school_delete():
    s = School.query.filter_by(director_id=current_user.id).first()
    if not s:
        abort(403)
    User.query.filter_by(school_id=s.id).update({"school_id": None, "class_id": None})
    current_user.school_id = None
    db.session.delete(s)
    db.session.commit()
    flash("Школа удалена", "ok")
    return redirect(url_for("school_page"))


# ===== КОДЫ И СВЯЗИ =====
@app.route("/my-codes")
@login_required
def my_codes():
    return render_template("codes.html")


@app.route("/link/teacher", methods=["POST"])
@login_required
def link_teacher():
    code = request.form.get("code", "").strip().upper()
    t = User.query.filter_by(teacher_code=code).first()
    if not t or t.id == current_user.id:
        flash("Код не найден", "error")
        return redirect(url_for("my_codes"))
    if TeacherStudent.query.filter_by(teacher_id=t.id, student_id=current_user.id).first():
        flash("Уже привязаны", "error")
        return redirect(url_for("my_codes"))
    db.session.add(TeacherStudent(teacher_id=t.id, student_id=current_user.id))
    db.session.commit()
    flash(f"Привязан к учителю {t.full_name}", "ok")
    return redirect(url_for("my_codes"))


@app.route("/link/student", methods=["POST"])
@login_required
def link_student():
    code = request.form.get("code", "").strip().upper()
    s = User.query.filter_by(student_code=code).first()
    if not s or s.id == current_user.id:
        flash("Код не найден", "error")
        return redirect(url_for("my_codes"))
    if StudentParent.query.filter_by(student_id=s.id, parent_id=current_user.id).first():
        flash("Уже привязаны", "error")
        return redirect(url_for("my_codes"))
    db.session.add(StudentParent(student_id=s.id, parent_id=current_user.id))
    db.session.commit()
    flash(f"Привязан к ученику {s.full_name}", "ok")
    return redirect(url_for("my_codes"))


# ===== СТОЛОВАЯ =====
@app.route("/canteen")
@login_required
def canteen():
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    rnd = random.Random(iso_year * 100 + iso_week)
    menu = {day: rnd.choice(CUISINES) for day in DAYS[:6]}
    return render_template("canteen.html", menu=menu, week=iso_week)


# ===== ЗАПУСК =====
def init_db():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
