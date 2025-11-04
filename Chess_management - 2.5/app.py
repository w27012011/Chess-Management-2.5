from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import sqlite3
from functools import wraps
import datetime
import csv
from io import StringIO, BytesIO
import random
import uuid
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import os
import re

app = Flask(__name__)
app.secret_key = 'secret_key_for_session'  # Change this in production

# Ensure required directories exist
if not os.path.exists('Entry_fee'):
    os.makedirs('Entry_fee')
if not os.path.exists('DB'):
    os.makedirs('DB')

# Database connection helper
def get_db_connection():
    batch_name = session.get('batch_name')
    if not batch_name:
        raise Exception("No batch selected")
    # Sanitize batch_name to match database creation
    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', batch_name)
    db_path = f'DB/batch_{safe_batch_name}_database.db'
    if not os.path.exists(db_path):
        raise Exception(f"Database for batch {batch_name} not found")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        if 'batch_name' not in session:
            return redirect(url_for('select_batch'))
        return f(*args, **kwargs)
    return decorated_function

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            return redirect(url_for('select_batch'))
    return render_template('login.html')

# Batch selection route
@app.route('/select_batch', methods=['GET', 'POST'])
def select_batch():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'select':
            batch_name = request.form.get('batch_name')
            safe_batch_name = re.sub(r'[^a-zAZ0-9_-]', '_', batch_name)
            if batch_name and os.path.exists(f'DB/batch_{safe_batch_name}_database.db'):
                session['batch_name'] = batch_name
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid batch selected", "error")
        elif action == 'new':
            batch_name = request.form.get('batch_name')
            if batch_name:
                from database import create_batch_database
                create_batch_database(batch_name)
                session['batch_name'] = batch_name
                flash(f"New batch '{batch_name}' created", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Batch name is required", "error")
    
    # List existing batches
    batches = []
    for file in os.listdir('DB'):
        if file.startswith('batch_') and file.endswith('_database.db'):
            batch_name = file[len('batch_'):-len('_database.db')]
            batches.append({'batch_name': batch_name, 'display_name': batch_name})
    return render_template('select_batch.html', batches=batches)

# Logout route
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('batch_name', None)
    return redirect(url_for('login'))

# Dashboard route
@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    total_students = conn.execute('SELECT COUNT(*) FROM Students').fetchone()[0]
    total_matches = conn.execute('SELECT COUNT(*) FROM Matches').fetchone()[0]
    top5 = conn.execute('SELECT student_id, name, points FROM Students ORDER BY points DESC LIMIT 5').fetchall()
    batch_name = session.get('batch_name')
    conn.close()
    return render_template('dashboard.html', total_students=total_students, total_matches=total_matches, top5=top5, batch_name=batch_name)

# Students list with search
@app.route('/students')
@login_required
def students():
    q = request.args.get('q', '')
    conn = get_db_connection()
    if q:
        students = conn.execute('SELECT * FROM Students WHERE name LIKE ? OR student_id LIKE ?', (f'%{q}%', f'%{q}%')).fetchall()
    else:
        students = conn.execute('SELECT * FROM Students').fetchall()
    batch_name = session.get('batch_name')
    conn.close()
    return render_template('students.html', students=students, batch_name=batch_name)

# Toggle paid entry
@app.route('/students/toggle_paid/<student_id>')
@login_required
def toggle_paid(student_id):
    conn = get_db_connection()
    current_status = conn.execute('SELECT paid_entry FROM Students WHERE student_id = ?', (student_id,)).fetchone()['paid_entry']
    new_status = 0 if current_status else 1
    conn.execute('UPDATE Students SET paid_entry = ? WHERE student_id = ?', (new_status, student_id))
    conn.commit()
    conn.close()
    return redirect(url_for('students'))

# Toggle all students' paid entry to Yes
@app.route('/students/toggle_all_paid')
@login_required
def toggle_all_paid():
    conn = get_db_connection()
    conn.execute('UPDATE Students SET paid_entry = 1')
    conn.commit()
    conn.close()
    flash("All students' paid entry status set to Yes", "success")
    return redirect(url_for('students'))

# Add student
@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        class_ = request.form['class']
        roll = request.form.get('roll', '')
        mobile = request.form.get('mobile', '')
        year = request.form.get('year', '')
        conn = get_db_connection()
        max_id = conn.execute('SELECT MAX(student_id) FROM Students').fetchone()[0]
        if max_id is None:
            new_id = '00001'
        else:
            new_id = str(int(max_id) + 1).zfill(5)
        conn.execute('INSERT INTO Students (student_id, name, class, roll, mobile, year, paid_entry) VALUES (?, ?, ?, ?, ?, ?, 0)',
                     (new_id, name, class_, roll, mobile, year))
        conn.commit()
        conn.close()
        return redirect(url_for('students'))
    return render_template('add_student.html')

# Edit student
@app.route('/students/edit/<student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    conn = get_db_connection()
    student = conn.execute('SELECT * FROM Students WHERE student_id = ?', (student_id,)).fetchone()
    if request.method == 'POST':
        name = request.form['name']
        class_ = request.form['class']
        roll = request.form.get('roll', '')
        mobile = request.form.get('mobile', '')
        year = request.form.get('year', '')
        paid_entry = 1 if 'paid_entry' in request.form else 0
        conn.execute('''
            UPDATE Students SET name = ?, class = ?, roll = ?, mobile = ?, year = ?, paid_entry = ?
            WHERE student_id = ?
        ''', (name, class_, roll, mobile, year, paid_entry, student_id))
        conn.commit()
        conn.close()
        return redirect(url_for('students'))
    conn.close()
    return render_template('edit_student.html', student=student)

# Export students to CSV
@app.route('/students/export_csv')
@login_required
def export_csv():
    conn = get_db_connection()
    students = conn.execute('SELECT student_id, name, class, roll, mobile, year, paid_entry FROM Students').fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Class', 'Roll', 'Mobile', 'Year', 'Paid Entry'])
    for student in students:
        writer.writerow([student['student_id'], student['name'], student['class'], student['roll'], student['mobile'], student['year'], 'Yes' if student['paid_entry'] else 'No'])
    
    output.seek(0)
    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', session["batch_name"])
    return send_file(
        BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'students_batch_{safe_batch_name}.csv'
    )

# Import students from CSV
@app.route('/students/import_csv', methods=['GET', 'POST'])
@login_required
def import_csv():
    if request.method == 'POST':
        print("POST request received for CSV import")
        if 'file' not in request.files:
            print("No file in request.files")
            flash("No file uploaded", "error")
            return redirect(url_for('students'))
        file = request.files['file']
        print(f"Selected file: {file.filename}")
        if file.filename == '':
            print("Empty filename")
            flash("No file selected", "error")
            return redirect(url_for('students'))
        if not file.filename.lower().endswith('.csv'):
            print(f"Invalid file extension: {file.filename}")
            flash("Invalid file format. Please upload a CSV file.", "error")
            return redirect(url_for('students'))
        
        # Save uploaded file for inspection
        file.save('uploaded_csv.csv')
        print("Saved uploaded file as uploaded_csv.csv")
        
        # Read raw file content for debugging
        file.seek(0)  # Reset file pointer
        raw_content = file.read().decode('utf-8', errors='replace')
        print(f"Raw CSV content (first 500 chars):\n{raw_content[:500]}")
        
        if not raw_content.strip():
            print("CSV file is empty")
            flash("The uploaded CSV file is empty.", "error")
            return redirect(url_for('students'))
        
        conn = get_db_connection()
        # Optional: Clear existing students to start fresh (uncomment if desired)
        # conn.execute('DELETE FROM Students')
        # conn.commit()
        # print("Cleared existing students from database")
        
        max_id = conn.execute('SELECT MAX(student_id) FROM Students').fetchone()[0]
        next_id = int(max_id) + 1 if max_id else 1
        print(f"Starting next_id: {next_id}")
        
        stream = StringIO(raw_content)
        csv_reader = csv.DictReader(stream)
        required_headers = {'ID', 'Name', 'Class', 'Roll', 'Mobile', 'Year'}
        
        if csv_reader.fieldnames is None:
            conn.close()
            print("No headers found in CSV")
            flash("CSV file has no headers or is malformed. Expected headers: ID, Name, Class, Roll, Mobile, Year", "error")
            return redirect(url_for('students'))
        
        print(f"CSV headers: {csv_reader.fieldnames}")
        if not required_headers.issubset(csv_reader.fieldnames):
            conn.close()
            print("Invalid headers")
            flash(f"CSV must contain headers: {', '.join(required_headers)}", "error")
            return redirect(url_for('students'))
        
        row_count = 0
        try:
            for row in csv_reader:
                row_count += 1
                print(f"Processing row {row_count}: {row}")
                student_id = row['ID'] if row['ID'] else str(next_id).zfill(5)
                next_id += 1
                name = row['Name']
                class_ = row['Class']
                roll = row.get('Roll', '')
                mobile = row.get('Mobile', '')
                year = row.get('Year', '')
                conn.execute('''
                    INSERT OR REPLACE INTO Students (student_id, name, class, roll, mobile, year, points, matches_played, paid_entry)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)
                ''', (student_id, name, class_, roll, mobile, year))
            print(f"Total rows processed: {row_count}")
            conn.commit()
            total_students = conn.execute('SELECT COUNT(*) FROM Students').fetchone()[0]
            print(f"Total students in database after import: {total_students}")
            conn.close()
            flash(f"Successfully imported {row_count} students. Total students: {total_students}", "success")
            return redirect(url_for('students'))
        except Exception as e:
            print(f"Error at row {row_count}: {str(e)}")
            conn.close()
            flash(f"Error processing CSV at row {row_count}: {str(e)}", "error")
            return redirect(url_for('students'))
    return render_template('import_csv.html')

# Helper function to generate entry fee PDF
def generate_entry_fee_pdf(batch_name, safe_batch_name, fee_amount, students):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(A4[1], A4[0]))  # Landscape A4
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph(f"Entry Fee Report - Batch {batch_name}", styles['Title']))
    elements.append(Paragraph(f"Generated on {datetime.date.today().strftime('%Y-%m-%d')}", styles['Normal']))
    elements.append(Paragraph(f"Fee per Student: {fee_amount} Taka", styles['Normal']))

    if students:
        data = [['Student ID', 'Name', 'Class', 'Roll', 'Mobile', 'Year', 'Paid']]  # Header
        for student in students:
            data.append([
                student['student_id'],
                student['name'],
                student['class'],
                student['roll'],
                student['mobile'],
                student['year'],
                'Yes' if student['paid_entry'] else 'No'
            ])
        
        table = Table(data, colWidths=[20*mm, 40*mm, 20*mm, 20*mm, 25*mm, 20*mm, 20*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)

        total_students = len(students)
        total_amount = total_students * fee_amount
        elements.append(Paragraph(f"Total Students: {total_students}", styles['Normal']))
        elements.append(Paragraph(f"Total Amount: {total_amount} Taka", styles['Normal']))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# Entry fee PDF (existing report)
@app.route('/students/export_entry_fee', methods=['GET', 'POST'])
@login_required
def export_entry_fee():
    batch_name = session.get('batch_name')
    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', batch_name)
    if request.method == 'POST':
        fee_amount = float(request.form.get('fee_amount', 0))
        conn = get_db_connection()
        students = conn.execute('SELECT * FROM Students WHERE paid_entry = 1').fetchall()
        conn.close()

        pdf = generate_entry_fee_pdf(batch_name, safe_batch_name, fee_amount, students)

        # Save PDF to Entry_fee folder
        pdf_filename = f'Entry_fee/entry_fee_{safe_batch_name}_{datetime.date.today().strftime("%Y%m%d")}.pdf'
        with open(pdf_filename, 'wb') as f:
            f.write(pdf)

        return send_file(
            BytesIO(pdf),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'entry_fee_{safe_batch_name}.pdf'
        )

    return render_template('entry_fee_form.html', batch_name=batch_name)

# Entry fee form PDF (new feature)
@app.route('/students/export_entry_fee_form', methods=['GET', 'POST'])
@login_required
def export_entry_fee_form():
    batch_name = session.get('batch_name')
    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', batch_name)
    if request.method == 'POST':
        fee_amount = float(request.form.get('fee_amount', 0))
        conn = get_db_connection()
        students = conn.execute('SELECT * FROM Students').fetchall()  # Include all students
        conn.close()

        pdf = generate_entry_fee_pdf(batch_name, safe_batch_name, fee_amount, students)

        # Save PDF to Entry_fee folder
        pdf_filename = f'Entry_fee/entry_fee_form_{safe_batch_name}_{datetime.date.today().strftime("%Y%m%d")}.pdf'
        with open(pdf_filename, 'wb') as f:
            f.write(pdf)

        return send_file(
            BytesIO(pdf),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'entry_fee_form_{safe_batch_name}.pdf'
        )

    return render_template('entry_fee_form_select.html', batch_name=batch_name)

# Entry fee history page
@app.route('/entry_fee_history')
@login_required
def entry_fee_history():
    batch_name = session.get('batch_name')
    safe_batch_name = re.sub(r'[^a-zAZ0-9_-]', '_', batch_name)
    entry_fee_files = []
    for file in os.listdir('Entry_fee'):
        if file.endswith('.pdf') and (file.startswith(f'entry_fee_{safe_batch_name}_') or file.startswith(f'entry_fee_form_{safe_batch_name}_')):
            try:
                # Extract date from filename (format: YYYYMMDD)
                date_part = file.split('_')[-1].split('.')[0]
                formatted_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                entry_fee_files.append({
                    'filename': file,
                    'path': f'Entry_fee/{file}',
                    'batch_name': batch_name,
                    'date': formatted_date
                })
            except (IndexError, ValueError):
                # Skip files with invalid date formats
                continue
    return render_template('entry_fee_history.html', files=entry_fee_files)

# Download archived entry fee PDF
@app.route('/entry_fee/download/<path:filename>')
@login_required
def download_entry_fee(filename):
    return send_file(f'Entry_fee/{filename}', as_attachment=True)

# Matches list
@app.route('/matches', methods=['GET', 'POST'])
@login_required
def matches():
    conn = get_db_connection()
    matches = conn.execute('''
        SELECT m.*, s1.name AS s1_name, s2.name AS s2_name, w.name AS winner_name
        FROM Matches m
        LEFT JOIN Students s1 ON m.student1_id = s1.student_id
        LEFT JOIN Students s2 ON m.student2_id = s2.student_id
        LEFT JOIN Students w ON m.winner_id = w.student_id
    ''').fetchall()
    batch_name = session.get('batch_name')
    conn.close()
    return render_template('matches.html', matches=matches, batch_name=batch_name)

# Auto generate matches
@app.route('/matches/auto', methods=['POST'])
@login_required
def auto_matches():
    max_matches = int(request.form.get('max_matches', 5))
    if max_matches < 1 or max_matches > 20:
        flash("Number of matches must be between 1 and 20", "error")
        return redirect(url_for('matches'))

    conn = get_db_connection()
    # Check for incomplete matches
    incomplete_matches = conn.execute('SELECT COUNT(*) FROM Matches WHERE points_assigned = 0').fetchone()[0]
    if incomplete_matches > 0:
        conn.close()
        flash("Cannot generate new matches until current batch is completed", "error")
        return redirect(url_for('matches'))

    students = conn.execute('SELECT student_id FROM Students WHERE paid_entry = 1').fetchall()
    student_ids = [s['student_id'] for s in students]
    random.shuffle(student_ids)
    
    matches = []
    match_counts = {sid: 0 for sid in student_ids}
    batch_name = session.get('batch_name')
    
    while any(count < max_matches for count in match_counts.values()) and len(student_ids) >= 2:
        available = [sid for sid, count in match_counts.items() if count < max_matches]
        if len(available) < 2:
            break
        random.shuffle(available)
        for i in range(0, len(available)-1, 2):
            s1, s2 = available[i], available[i+1]
            if match_counts[s1] < max_matches and match_counts[s2] < max_matches:
                matches.append((s1, s2, batch_name))
                match_counts[s1] += 1
                match_counts[s2] += 1
    
    for s1, s2, bname in matches:
        conn.execute('INSERT INTO Matches (student1_id, student2_id, batch_id) VALUES (?, ?, ?)', (s1, s2, bname))
    conn.commit()
    conn.close()
    flash("Matches generated successfully", "success")
    return redirect(url_for('matches'))

# Download tournament schedule as PDF
@app.route('/matches/export_schedule')
@login_required
def export_schedule():
    conn = get_db_connection()
    matches = conn.execute('''
        SELECT m.match_id, s1.student_id AS s1_id, s1.name AS s1_name, s1.class AS s1_class,
               s2.student_id AS s2_id, s2.name AS s2_name, s2.class AS s2_class
        FROM Matches m
        LEFT JOIN Students s1 ON m.student1_id = s1.student_id
        LEFT JOIN Students s2 ON m.student2_id = s2.student_id
        WHERE m.winner_id IS NULL
    ''').fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(A4[1], A4[0]))  # Landscape A4
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph(f"Chess Club Tournament Schedule - Batch {session['batch_name']}", styles['Title']))
    elements.append(Paragraph(f"Generated on {datetime.date.today().strftime('%Y-%m-%d')}", styles['Normal']))
    elements.append(Spacer(1, 12))  # Add spacing after header

    if matches:
        # Group matches into sessions of 10
        matches_per_session = 10
        for session_num, i in enumerate(range(0, len(matches), matches_per_session), 1):
            session_matches = matches[i:i + matches_per_session]
            elements.append(Paragraph(f"Session {session_num}", styles['Heading2']))
            elements.append(Spacer(1, 6))

            data = [['Match ID', 'Board', 'Player 1 ID', 'Player 1 Name', 'Player 1 Class',
                     'Player 2 ID', 'Player 2 Name', 'Player 2 Class']]
            for j, match in enumerate(session_matches):
                # Calculate board number: (j % 10) + 1 to reset to 1-10 per session
                board = f"Board-{((j % 10) + 1)}"
                data.append([
                    str(match['match_id']),
                    board,
                    match['s1_id'],
                    match['s1_name'],
                    match['s1_class'],
                    match['s2_id'],
                    match['s2_name'],
                    match['s2_class']
                ])

            table = Table(data, colWidths=[20*mm, 20*mm, 20*mm, 40*mm, 20*mm, 20*mm, 40*mm, 20*mm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))  # Add spacing between sessions
    else:
        elements.append(Paragraph("No pending matches available.", styles['Normal']))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', session["batch_name"])
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'tournament_schedule_{safe_batch_name}.pdf'
    )

# Download match results as PDF
@app.route('/matches/export_results')
@login_required
def export_results():
    conn = get_db_connection()
    matches = conn.execute('''
        SELECT m.match_id, s1.student_id AS s1_id, s1.name AS s1_name, s1.class AS s1_class,
               s2.student_id AS s2_id, s2.name AS s2_name, s2.class AS s2_class, w.name AS winner_name
        FROM Matches m
        LEFT JOIN Students s1 ON m.student1_id = s1.student_id
        LEFT JOIN Students s2 ON m.student2_id = s2.student_id
        LEFT JOIN Students w ON m.winner_id = w.student_id
        WHERE m.points_assigned = 1
    ''').fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(A4[1], A4[0]))
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f"Chess Club Match Results - Batch {session['batch_name']}", styles['Title']))
    elements.append(Paragraph(f"Generated on {datetime.date.today().strftime('%Y-%m-%d')}", styles['Normal']))
    
    if matches:
        data = [['Match ID', 'Player 1 ID', 'Player 1 Name', 'Player 1 Class',
                 'Player 2 ID', 'Player 2 Name', 'Player 2 Class', 'Winner']]
        for match in matches:
            data.append([
                str(match['match_id']),
                match['s1_id'],
                match['s1_name'],
                match['s1_class'],
                match['s2_id'],
                match['s2_name'],
                match['s2_class'],
                match['winner_name'] or 'Draw'
            ])
        
        table = Table(data, colWidths=[20*mm, 20*mm, 40*mm, 20*mm, 20*mm, 40*mm, 20*mm, 40*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)
    
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', session["batch_name"])
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'match_results_{safe_batch_name}.pdf'
    )

# Archive completed matches to history
@app.route('/matches/archive')
@login_required
def archive_matches():
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO MatchHistory (student1_id, student2_id, winner_id, points_assigned, match_date, batch_id)
        SELECT student1_id, student2_id, winner_id, points_assigned, match_date, batch_id
        FROM Matches
        WHERE points_assigned = 1
    ''')
    conn.execute('DELETE FROM Matches WHERE points_assigned = 1')
    conn.commit()
    conn.close()
    flash("Completed matches archived successfully", "success")
    return redirect(url_for('matches'))

# Match history
@app.route('/match_history')
@login_required
def match_history():
    conn = get_db_connection()
    matches = conn.execute('''
        SELECT m.*, s1.name AS s1_name, s2.name AS s2_name, w.name AS winner_name
        FROM MatchHistory m
        LEFT JOIN Students s1 ON m.student1_id = s1.student_id
        LEFT JOIN Students s2 ON m.student2_id = s2.student_id
        LEFT JOIN Students w ON m.winner_id = s1.student_id
    ''').fetchall()
    conn.close()
    return render_template('match_history.html', matches=matches)

# Update match
@app.route('/matches/update/<int:match_id>', methods=['GET', 'POST'])
@login_required
def update_match(match_id):
    conn = get_db_connection()
    match = conn.execute('''
        SELECT m.*, s1.name AS s1_name, s2.name AS s2_name
        FROM Matches m
        LEFT JOIN Students s1 ON m.student1_id = s1.student_id
        LEFT JOIN Students s2 ON m.student2_id = s2.student_id
        WHERE m.match_id = ?
    ''', (match_id,)).fetchone()
    if request.method == 'POST':
        winner = request.form['winner']
        if match['points_assigned'] == 0:
            conn.execute('UPDATE Students SET matches_played = matches_played + 1 WHERE student_id = ?', (match['student1_id'],))
            conn.execute('UPDATE Students SET matches_played = matches_played + 1 WHERE student_id = ?', (match['student2_id'],))
            if winner == 'draw':
                conn.execute('UPDATE Students SET points = points + 0.5 WHERE student_id = ?', (match['student1_id'],))
                conn.execute('UPDATE Students SET points = points + 0.5 WHERE student_id = ?', (match['student2_id'],))
            elif winner:
                conn.execute('UPDATE Students SET points = points + 3 WHERE student_id = ?', (winner,))
        conn.execute('UPDATE Matches SET winner_id = ?, points_assigned = 1 WHERE match_id = ?', (winner if winner != 'draw' else None, match_id))
        conn.commit()
        conn.close()
        return redirect(url_for('matches'))
    conn.close()
    return render_template('update_match.html', match=match)

# Leaderboard
@app.route('/leaderboard')
@login_required
def leaderboard():
    class_filter = request.args.get('class', '')
    month_filter = request.args.get('month', '')
    conn = get_db_connection()
    batch_name = session.get('batch_name')

    if month_filter:
        query = '''
            SELECT s.student_id, s.name, s.class, s.roll, s.mobile, s.year, s.matches_played,
                   SUM(CASE WHEN m.winner_id = s.student_id THEN 3
                            WHEN m.winner_id IS NULL THEN 0.5
                            ELSE 0 END) AS points
            FROM MatchHistory m
            JOIN Students s ON m.student1_id = s.student_id OR m.student2_id = s.student_id
            WHERE strftime('%Y-%m', m.match_date) = ? AND m.points_assigned = 1
            GROUP BY s.student_id
        '''
        params = (month_filter,)
        if class_filter:
            query = query.replace('WHERE', 'WHERE s.class = ? AND')
            params = (class_filter, month_filter)
        leaders = conn.execute(query, params).fetchall()
    else:
        query = '''
            SELECT s.student_id, s.name, s.class, s.roll, s.mobile, s.year, s.matches_played,
                   SUM(CASE WHEN m.winner_id = s.student_id THEN 3
                            WHEN m.winner_id IS NULL THEN 0.5
                            ELSE 0 END) AS points
            FROM Matches m
            JOIN Students s ON m.student1_id = s.student_id OR m.student2_id = s.student_id
            WHERE m.batch_id = ? AND m.points_assigned = 1
            GROUP BY s.student_id
        '''
        params = (batch_name,)
        if class_filter:
            query = query.replace('WHERE', 'WHERE s.class = ? AND')
            params = (class_filter, batch_name)
        leaders = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('leaderboard.html', leaders=leaders, class_filter=class_filter, month_filter=month_filter, batch_name=batch_name)

# Download leaderboard as PDF
@app.route('/leaderboard/export')
@login_required
def export_leaderboard():
    class_filter = request.args.get('class', '')
    month_filter = request.args.get('month', '')
    conn = get_db_connection()
    batch_name = session.get('batch_name')

    if month_filter:
        query = '''
            SELECT s.student_id, s.name, s.class, s.roll, s.mobile, s.year, s.matches_played,
                   SUM(CASE WHEN m.winner_id = s.student_id THEN 3
                            WHEN m.winner_id IS NULL THEN 0.5
                            ELSE 0 END) AS points
            FROM MatchHistory m
            JOIN Students s ON m.student1_id = s.student_id OR m.student2_id = s.student_id
            WHERE strftime('%Y-%m', m.match_date) = ? AND m.points_assigned = 1
            GROUP BY s.student_id
            ORDER BY points DESC
        '''
        params = (month_filter,)
        if class_filter:
            query = query.replace('WHERE', 'WHERE s.class = ? AND')
            params = (class_filter, month_filter)
        leaders = conn.execute(query, params).fetchall()
    else:
        query = '''
            SELECT s.student_id, s.name, s.class, s.roll, s.mobile, s.year, s.matches_played,
                   SUM(CASE WHEN m.winner_id = s.student_id THEN 3
                            WHEN m.winner_id IS NULL THEN 0.5
                            ELSE 0 END) AS points
            FROM Matches m
            JOIN Students s ON m.student1_id = s.student_id OR m.student2_id = s.student_id
            WHERE m.batch_id = ? AND m.points_assigned = 1
            GROUP BY s.student_id
            ORDER BY points DESC
        '''
        params = (batch_name,)
        if class_filter:
            query = query.replace('WHERE', 'WHERE s.class = ? AND')
            params = (class_filter, batch_name)
        leaders = conn.execute(query, params).fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(A4[1], A4[0]))
    elements = []
    styles = getSampleStyleSheet()
    
    title = f"Chess Club Leaderboard - Batch {batch_name}"
    if month_filter:
        title += f" ({month_filter})"
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Paragraph(f"Generated on {datetime.date.today().strftime('%Y-%m-%d')}", styles['Normal']))
    
    if leaders:
        data = [['Rank', 'Student ID', 'Name', 'Class', 'Roll', 'Mobile', 'Year', 'Points', 'Matches Played']]
        for i, leader in enumerate(leaders):
            data.append([
                str(i + 1),
                leader['student_id'],
                leader['name'],
                leader['class'],
                leader['roll'],
                leader['mobile'],
                leader['year'],
                str(leader['points']),
                str(leader['matches_played'])
            ])
        
        table = Table(data, colWidths=[15*mm, 20*mm, 40*mm, 20*mm, 20*mm, 25*mm, 20*mm, 20*mm, 20*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)
    
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', session["batch_name"])
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'leaderboard_{safe_batch_name}.pdf'
    )

if __name__ == '__main__':
    app.run(debug=True)