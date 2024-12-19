from flask import Flask, render_template, request, jsonify, url_for
from werkzeug.utils import secure_filename
import pandas as pd
import os
from xml.etree import ElementTree as ET
import psycopg2

app = Flask(__name__)
app.secret_key = 'super_secret_key'

GENERATED_GRIDS_FOLDER = os.path.join('generated_grids')
SVG_FOLDER = 'static/svg'
OUTPUT_FOLDER = 'generated_grids'
UPLOAD_FOLDER = 'uploaded_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SVG_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

CATEGORIES = [
    {"name": "М 5-7 лет", "gender": "М", "min_age": 5, "max_age": 7},
    {"name": "Ж 5-7 лет", "gender": "Ж", "min_age": 5, "max_age": 7},
    {"name": "М 8-9 лет", "gender": "М", "min_age": 8, "max_age": 9},
    {"name": "Ж 8-9 лет", "gender": "Ж", "min_age": 8, "max_age": 9},
    {"name": "М 10-11 лет", "gender": "М", "min_age": 10, "max_age": 11},
    {"name": "Ж 10-11 лет", "gender": "Ж", "min_age": 10, "max_age": 11},
    {"name": "М 12-13 лет", "gender": "М", "min_age": 12, "max_age": 13},
    {"name": "Ж 12-13 лет", "gender": "Ж", "min_age": 12, "max_age": 13},
    {"name": "М 14-15 лет", "gender": "М", "min_age": 14, "max_age": 15},
    {"name": "Ж 14-15 лет", "gender": "Ж", "min_age": 14, "max_age": 15},
    {"name": "М 16-17 лет", "gender": "М", "min_age": 16, "max_age": 17},
    {"name": "Ж 16-17 лет", "gender": "Ж", "min_age": 16, "max_age": 17},
    {"name": "М 18-35 лет", "gender": "М", "min_age": 18, "max_age": 34},
    {"name": "Ж 18-35 лет", "gender": "Ж", "min_age": 18, "max_age": 34},
    {"name": "М 35-55 лет", "gender": "М", "min_age": 35, "max_age": 55},
    {"name": "Ж 35-55 лет", "gender": "Ж", "min_age": 35, "max_age": 55},

]

def get_db_connection():
    try:
        return psycopg2.connect(
            dbname="Stash",
            user="postgres",
            password="12345",
            host="localhost"
        )
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

def strip_namespace(element):
    """Удаляет пространство имен из тегов XML."""
    for elem in element.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]

@app.route('/')
def index():
    grids = [file for file in os.listdir(OUTPUT_FOLDER) if file.endswith('.svg')]
    return render_template('index.html', grids=grids)

@app.route('/generate_grids', methods=['POST'])
def generate_grids():
    """Генерация сеток на основе категорий и участников."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Failed to connect to the database."}), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT last_name, first_name, age, gender FROM participants")
        participants = cur.fetchall()
        cur.close()
    except Exception as e:
        conn.close()
        print(f"Error fetching participants from database: {e}")
        return jsonify({"message": "Error fetching participants."}), 500

    grids_created = []
    for category in CATEGORIES:
        filtered_participants = [
            {"last_name": p[0], "first_name": p[1], "age": p[2], "gender": p[3]}
            for p in participants
            if category['min_age'] <= p[2] <= category['max_age'] and p[3] == category['gender']
        ]

        if not filtered_participants:
            continue

        participant_count = len(filtered_participants) 
        svg_template = f"Group_{participant_count}.svg"
        template_path = os.path.join(SVG_FOLDER, svg_template)
        output_path = os.path.join(OUTPUT_FOLDER, f"{category['name']}.svg")

        if not os.path.exists(template_path):
            continue

        try:
            tree = ET.parse(template_path)
            root = tree.getroot()
            strip_namespace(root)

            for idx, participant in enumerate(filtered_participants, start=1):
                text_element = root.find(f".//*[@id='participant_{idx}']")
                if text_element is not None:
                    text_element.text = f"{participant['first_name']} {participant['last_name']}"

            tree.write(output_path, encoding='utf-8', xml_declaration=True)
            grids_created.append(output_path)
        except Exception as e:
            print(f"Error processing template {svg_template}: {e}")

    conn.close()

    if not grids_created:
        return jsonify({"message": "No grids created."}), 400

    return jsonify({"message": "Grids created successfully!"}), 200

@app.route('/brackets', methods=['GET'])
def get_brackets():
    """Получить список всех турнирных сеток."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, t.name AS tournament_name, c.name AS category_name, b.created_at
        FROM brackets b
        JOIN tournaments t ON b.tournament_id = t.id
        JOIN categories c ON b.category_id = c.id
        ORDER BY b.created_at
    """)
    brackets = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {"id": b[0], "tournament_name": b[1], "category_name": b[2], "created_at": b[3]}
        for b in brackets
    ])


@app.route('/grid_list')
def grid_list():
    grids = [file for file in os.listdir(OUTPUT_FOLDER) if file.endswith('.svg')]
    return render_template('grid_list.html', grids=grids)


@app.route('/save_bracket', methods=['POST'])
def save_bracket():
    """Пересохраняет измененную турнирную сетку в папке generated_grids."""
    try:
        data = request.json
        bracket_content = data.get('bracket')
        category = data.get('category')

        if not bracket_content or not category:
            return jsonify({"message": "Данные для сохранения не предоставлены."}), 400

        # Путь для сохранения файла
        output_path = os.path.join('generated_grids', f"{category}.svg")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)  # Создаем папку, если она не существует

        print(f"Пересохранение сетки в файл: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(bracket_content)

        return jsonify({"message": "Сетка успешно пересохранена."}), 200
    except Exception as e:
        print(f"Ошибка при сохранении сетки: {e}")
        return jsonify({"message": f"Ошибка при сохранении: {e}"}), 500

@app.route('/upload_excel', methods=['POST'])
def upload_excel():
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({"message": "Файл не предоставлен."}), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        # Читаем файл Excel
        df = pd.read_excel(file_path, header=None)
        df.columns = ['last_name', 'first_name', 'middle_name', 'age', 'weight', 'city', 'gender', 'rank_type', 'rank_value']

        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT INTO participants (
                    last_name, first_name, middle_name, age, weight, city, gender, rank_type, rank_value
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (row['last_name'], row['first_name'], row.get('middle_name', ''),
                 row['age'], row['weight'], row['city'], row['gender'], row['rank_type'], row['rank_value'])
            )
        conn.commit()
        cur.close()
        conn.close()
        os.remove(file_path)

        return jsonify({"message": "Участники успешно добавлены из файла."}), 200
    except Exception as e:
        print(f"Ошибка при загрузке участников из Excel: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500



@app.route('/view_bracket/<category>', methods=['GET'])
def view_bracket(category):
    """Отображает готовую турнирную сетку из папки generated_grids."""
    try:
        # Путь к файлу в папке generated_grids
        grid_path = os.path.join('generated_grids', f"{category}.svg")

        if os.path.exists(grid_path):
            # Читаем содержимое файла
            with open(grid_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
        else:
            return jsonify({"message": f"Сетка для категории {category} не найдена."}), 404

        # Передаем содержимое в шаблон
        return render_template('view_bracket.html', svg_content=svg_content, category=category)
    except Exception as e:
        print(f"Ошибка при загрузке сетки: {e}")
        return jsonify({"message": f"Ошибка при загрузке: {e}"}), 500


@app.route('/preview_bracket/<category>', methods=['GET'])
def preview_bracket(category):
    svg_file = os.path.join(OUTPUT_FOLDER, f"{category}.svg")
    try:
        if not os.path.exists(svg_file):
            return jsonify({"message": f"SVG файл '{category}.svg' не найден."}), 404

        with open(svg_file, 'r', encoding='utf-8') as file:
            svg_content = file.read()

        return render_template('view_bracket_readonly.html', svg_content=svg_content)
    except Exception as e:
        print(f"Ошибка при чтении SVG файла: {e}")
        return jsonify({"message": "Ошибка при обработке SVG файла."}), 500


@app.route('/add_participant', methods=['POST'])
def add_participant():
    """Добавление одного участника вручную."""
    try:
        data = request.form
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO participants (
                last_name, first_name, middle_name, age, weight, city, gender, rank_type, rank_value
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data.get('last_name'),
                data.get('first_name'),
                data.get('middle_name', ''),
                data.get('age'),
                data.get('weight'),
                data.get('city'),
                data.get('gender'),
                data.get('rank_type'),
                data.get('rank_value'),
            )
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Участник успешно добавлен!"}), 200
    except Exception as e:
        print(f"Ошибка при добавлении участника: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500


@app.route('/tournaments', methods=['GET'])
def get_tournaments():
    """Получить список всех турниров."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("SELECT id, name, location, date FROM tournaments ORDER BY date")
    tournaments = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{"id": t[0], "name": t[1], "location": t[2], "date": t[3]} for t in tournaments])

@app.route('/tournaments', methods=['POST'])
def add_tournament():
    """Добавить новый турнир."""
    try:
        data = request.json
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tournaments (name, location, date)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (data.get('name'), data.get('location'), data.get('date'))
        )
        tournament_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Турнир успешно добавлен!", "id": tournament_id}), 201
    except Exception as e:
        print(f"Ошибка при добавлении турнира: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500

@app.route('/categories', methods=['GET'])
def get_categories():
    """Получить список всех категорий."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("SELECT id, name, age_min, age_max, weight_min, weight_max FROM categories")
    categories = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {"id": c[0], "name": c[1], "age_min": c[2], "age_max": c[3], "weight_min": c[4], "weight_max": c[5]}
        for c in categories
    ])

@app.route('/categories', methods=['POST'])
def add_category():
    """Добавить новую категорию."""
    try:
        data = request.json
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO categories (name, age_min, age_max, weight_min, weight_max)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (data.get('name'), data.get('age_min'), data.get('age_max'), data.get('weight_min'), data.get('weight_max'))
        )
        category_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Категория успешно добавлена!", "id": category_id}), 201
    except Exception as e:
        print(f"Ошибка при добавлении категории: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500

@app.route('/brackets', methods=['GET'])
def get_brackets():
    """Получить список всех турнирных сеток."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, t.name AS tournament_name, c.name AS category_name, b.created_at
        FROM brackets b
        JOIN tournaments t ON b.tournament_id = t.id
        JOIN categories c ON b.category_id = c.id
        ORDER BY b.created_at
    """)
    brackets = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {"id": b[0], "tournament_name": b[1], "category_name": b[2], "created_at": b[3]}
        for b in brackets
    ])

@app.route('/brackets', methods=['POST'])
def add_bracket():
    """Добавить новую турнирную сетку."""
    try:
        data = request.json
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO brackets (tournament_id, category_id)
            VALUES (%s, %s)
            RETURNING id
            """,
            (data.get('tournament_id'), data.get('category_id'))
        )
        bracket_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Сетка успешно добавлена!", "id": bracket_id}), 201
    except Exception as e:
        print(f"Ошибка при добавлении сетки: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500

@app.route('/matches/<int:bracket_id>', methods=['GET'])
def get_matches(bracket_id):
    """Получить список всех матчей в рамках турнирной сетки."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.participant_1_id, m.participant_2_id, m.winner_id, m.round, m.match_number
        FROM matches m
        WHERE m.bracket_id = %s
        ORDER BY m.round, m.match_number
    """, (bracket_id,))
    matches = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "id": m[0],
            "participant_1_id": m[1],
            "participant_2_id": m[2],
            "winner_id": m[3],
            "round": m[4],
            "match_number": m[5]
        }
        for m in matches
    ])

@app.route('/matches', methods=['POST'])
def add_match():
    """Добавить новый матч в рамках турнирной сетки."""
    try:
        data = request.json
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO matches (bracket_id, participant_1_id, participant_2_id, round, match_number)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (data.get('bracket_id'), data.get('participant_1_id'), data.get('participant_2_id'),
             data.get('round'), data.get('match_number'))
        )
        match_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Матч успешно добавлен!", "id": match_id}), 201
    except Exception as e:
        print(f"Ошибка при добавлении матча: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500

@app.route('/organizations', methods=['GET'])
def get_organizations():
    """Получить список всех организаций."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("SELECT id, name, city, contact_info FROM organizations")
    organizations = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {"id": o[0], "name": o[1], "city": o[2], "contact_info": o[3]} for o in organizations
    ])

@app.route('/organizations', methods=['POST'])
def add_organization():
    """Добавить новую организацию."""
    try:
        data = request.json
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO organizations (name, city, contact_info)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (data.get('name'), data.get('city'), data.get('contact_info'))
        )
        organization_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Организация успешно добавлена!", "id": organization_id}), 201
    except Exception as e:
        print(f"Ошибка при добавлении организации: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500


@app.route('/sponsors', methods=['GET'])
def get_sponsors():
    """Получить список всех спонсоров."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.name, s.contact_info, s.contribution, t.name AS tournament_name
        FROM sponsors s
        LEFT JOIN tournaments t ON s.tournament_id = t.id
    """)
    sponsors = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "id": s[0],
            "name": s[1],
            "contact_info": s[2],
            "contribution": s[3],
            "tournament_name": s[4]
        }
        for s in sponsors
    ])

@app.route('/sponsors', methods=['POST'])
def add_sponsor():
    """Добавить нового спонсора."""
    try:
        data = request.json
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Не удалось подключиться к базе данных."}), 500

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sponsors (name, contact_info, contribution, tournament_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (data.get('name'), data.get('contact_info'), data.get('contribution'), data.get('tournament_id'))
        )
        sponsor_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Спонсор успешно добавлен!", "id": sponsor_id}), 201
    except Exception as e:
        print(f"Ошибка при добавлении спонсора: {e}")
        return jsonify({"message": f"Ошибка: {e}"}), 500



if __name__ == '__main__':
    app.run(debug=True)
