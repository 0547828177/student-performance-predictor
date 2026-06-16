from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
import joblib
import pandas as pd
import numpy as np
import csv
from io import TextIOWrapper
from datetime import datetime

app = Flask(__name__)
# Email settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'ednaacheampong772@gmail.com'
app.config['MAIL_PASSWORD'] = 'tvew iwak aish rsmj'
mail = Mail(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///students.db'
db = SQLAlchemy(app)

model = joblib.load('model.pkl')
scaler = joblib.load('scaler.pkl')

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    student_id = db.Column(db.String(20))
    program = db.Column(db.String(20), default='CS')
    attendance = db.Column(db.Float)
    assignment = db.Column(db.Float)
    midterm = db.Column(db.Float)
    quiz = db.Column(db.Float)
    gpa = db.Column(db.Float)
    hours = db.Column(db.Float)
    risk = db.Column(db.Integer)
    risk_prob = db.Column(db.Float)

with app.app_context():
    db.create_all()

class Intervention(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref=db.backref('interventions', lazy=True))

def predict_risk(att, ass, mid, quiz, gpa, hours):
    data = pd.DataFrame([[att, ass, mid, quiz, gpa, hours]], 
                        columns=['attendance_rate', 'assignment_avg', 'midterm_score',
                                 'quiz_avg', 'previous_gpa', 'hours_studied_weekly'])
    scaled = scaler.transform(data)
    prob = model.predict_proba(scaled)[0][1]
    return 1 if prob >= 0.5 else 0, prob

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        name = request.form['name']
        student_id = request.form['student_id']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        program = request.form.get('program', 'CS')
        att = float(request.form['attendance'])
        ass = float(request.form['assignment'])
        mid = float(request.form['midterm'])
        quiz = float(request.form['quiz'])
        gpa = float(request.form['gpa'])
        hours = float(request.form['hours'])
        
        risk, prob = predict_risk(att, ass, mid, quiz, gpa, hours)
        
        student = Student(
            name=name, student_id=student_id, program=program,
            attendance=att, assignment=ass, midterm=mid, quiz=quiz,
            gpa=gpa, hours=hours, risk=risk, risk_prob=prob
        )
        db.session.add(student)
        db.session.commit()
        
        # Send email if at risk and email provided
        if risk == 1 and email:
            try:
                from flask_mail import Message
                msg = Message("Academic Risk Alert",
                              sender=app.config['MAIL_USERNAME'],
                              recipients=[email])
                msg.body = f"Student {name} is AT RISK ({prob*100:.1f}%). Please intervene."
                mail.send(msg)
                print("Email sent to", email)
            except Exception as e:
                print("Email error:", e)
        
        msg_result = f"Student {name} is {'AT RISK' if risk else 'GOOD'} (probability: {prob*100:.1f}%)"
        return f'''
        <div style="text-align:center; margin-top:50px;">
            <h3>{msg_result}</h3>
            <a href="/add" class="btn btn-primary">Add Another</a>
            <a href="/list" class="btn btn-secondary">View All</a>
        </div>
        '''
    
    return render_template('add.html')

@app.route('/list')
def list_students():
    students = Student.query.all()
    return render_template('list.html', students=students)

@app.route('/export/excel')
def export_excel():
    import pandas as pd
    from flask import send_file
    import io
    
    students = Student.query.all()
    data = []
    for s in students:
        data.append({
            'Name': s.name,
            'Student ID': s.student_id,
            'Program': s.program if hasattr(s, 'program') else 'CS',
            'Attendance (%)': f"{s.attendance*100:.1f}",
            'Assignment Avg': s.assignment,
            'Midterm Score': s.midterm,
            'Quiz Avg': s.quiz,
            'Previous GPA': s.gpa,
            'Hours Studied/Week': s.hours,
            'Risk Status': 'At Risk' if s.risk else 'Good',
            'Risk Probability (%)': f"{s.risk_prob*100:.1f}"
        })
    
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Students', index=False)
    
    output.seek(0)
    return send_file(output, download_name='student_report.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/upload', methods=['GET', 'POST'])
def upload_students():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file:
            return "No file uploaded", 400
        
        csv_data = TextIOWrapper(file, encoding='utf-8')
        reader = csv.DictReader(csv_data)
        imported = 0
        errors = []
        
        for row in reader:
            try:
                name = row.get('name') or row.get('Name')
                student_id = row.get('student_id') or row.get('Student ID')
                att = float(row.get('attendance', 0))
                ass = float(row.get('assignment', 0))
                mid = float(row.get('midterm', 0))
                quiz = float(row.get('quiz', 0))
                gpa = float(row.get('gpa', 0))
                hours = float(row.get('hours', 0))
                program = row.get('program', 'CS')
                
                if not name or not student_id:
                    errors.append(f"Missing name or ID in row")
                    continue
                
                risk, prob = predict_risk(att, ass, mid, quiz, gpa, hours)
                student = Student(
                    name=name, student_id=student_id, program=program,
                    attendance=att, assignment=ass, midterm=mid, quiz=quiz,
                    gpa=gpa, hours=hours, risk=risk, risk_prob=prob
                )
                db.session.add(student)
                imported += 1
            except Exception as e:
                errors.append(str(e))
        
        db.session.commit()
        return f"""
        <div class='container mt-5'>
            <h3>Import completed</h3>
            <p>✅ Imported: {imported} students</p>
            <p>⚠️ Errors: {len(errors)}</p>
            <a href='/list' class='btn btn-primary'>View Students</a>
            <a href='/upload' class='btn btn-secondary'>Upload another</a>
        </div>
        """
    return render_template('upload.html')

@app.route('/intervention/<int:student_id>', methods=['GET', 'POST'])
def add_intervention(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        action = request.form['action']
        notes = request.form.get('notes', '')
        intervention = Intervention(student_id=student_id, action=action, notes=notes)
        db.session.add(intervention)
        db.session.commit()
        return redirect(url_for('list_students'))
    return render_template('intervention.html', student=student)

@app.route('/analytics')
def analytics():
    students = Student.query.all()
    total = len(students)
    at_risk = sum(1 for s in students if s.risk == 1)
    safe = total - at_risk
    
    # Count by program
    programs = {}
    for s in students:
        prog = s.program if s.program else 'CS'
        if prog not in programs:
            programs[prog] = {'total': 0, 'risk': 0}
        programs[prog]['total'] += 1
        if s.risk == 1:
            programs[prog]['risk'] += 1
    
    prog_labels = list(programs.keys())
    prog_risk_counts = [programs[p]['risk'] for p in prog_labels]
    
    return render_template('analytics.html', 
                           total=total, at_risk=at_risk, safe=safe,
                           prog_labels=prog_labels, prog_risk_counts=prog_risk_counts)

if __name__ == '__main__':
    app.run(debug=True)