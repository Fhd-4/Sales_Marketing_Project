from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3, os, re
from datetime import datetime
import pytesseract
import cv2

# إعداد تطبيق Flask والمسارات
app = Flask(__name__)
app.secret_key = 'smart_sales_analytics_final_2026' 

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

#pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def get_db_connection():
    conn = sqlite3.connect('final_project.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS sales 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     vendor TEXT, inv_no TEXT, amount TEXT, 
                     category TEXT, date TEXT, time TEXT)''')
    conn.commit()
    conn.close()

# --- المسارات البرمجية ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # صلاحيات المدير (كامل الصلاحيات)
        if username == 'admin' and password == '1234':
            session['logged_in'] = True
            session['role'] = 'admin'
            return redirect(url_for('dashboard'))
            
        # صلاحيات مدخل البيانات (إضافة فواتير فقط)
        elif username == 'user' and password == '0000':
            session['logged_in'] = True
            session['role'] = 'entry'
            return redirect(url_for('add'))
            
        return render_template('login.html', error="بيانات الدخول غير صحيحة")
    return render_template('login.html')

@app.route('/')
@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect(url_for('login'))
    # منع مدخل البيانات من دخول الداشبورد
    if session.get('role') != 'admin': return redirect(url_for('add'))
    
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM sales").fetchall()
    
    total = sum(float(str(r['amount']).replace(',', '')) for r in rows) if rows else 0.0
    aov = total / len(rows) if rows else 0.0
    
    top_vendor = "لا يوجد"
    top_category = "لا يوجد"
    if rows:
        vendors = [r['vendor'] for r in rows]
        categories = [r['category'] for r in rows]
        top_vendor = max(set(vendors), key=vendors.count)
        top_category = max(set(categories), key=categories.count)
        
    conn.close()
    return render_template('dashboard.html', total=total, aov=aov, count=len(rows), 
                           top_vendor=top_vendor, top_category=top_category)

@app.route('/logs')
def logs():
    if not session.get('logged_in'): return redirect(url_for('login'))
    # منع مدخل البيانات من دخول السجل
    if session.get('role') != 'admin': return redirect(url_for('add'))
    
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', 'all') 
    
    conn = get_db_connection()
    query = "SELECT * FROM sales WHERE 1=1"
    params = []
    
    if search:
        query += " AND (vendor LIKE ? OR category LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
        
    if filter_type == 'today':
        today_str = datetime.now().strftime("%Y-%m-%d")
        query += " AND date = ?"
        params.append(today_str)
        
    query += " ORDER BY id DESC"
    
    data = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template('logs.html', sales=data, search_query=search, filter_type=filter_type)

@app.route('/add')
def add():
    if not session.get('logged_in'): return redirect(url_for('login'))
    # هذه الصفحة متاحة للجميع (admin و entry)
    return render_template('add.html', scanned_data=None)

@app.route('/scan', methods=['POST'])
def scan():
    if not session.get('logged_in'): return redirect(url_for('login'))
    file = request.files.get('file')
    scanned = {
        "vendor": "مورد غير معروف", "inv_no": "REF-"+datetime.now().strftime("%M%S"), 
        "amount": "0.00", "category": "أخرى", 
        "date": datetime.now().strftime("%Y-%m-%d"), 
        "time": datetime.now().strftime("%H:%M"),
        "filename": "" 
    }
    if file and file.filename != '':
        path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(path)
        scanned["filename"] = file.filename
        try:
            img = cv2.imread(path)
            text = pytesseract.image_to_string(img, lang='eng+ara')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if lines: scanned["vendor"] = lines[0]
            amt = re.findall(r'[\d,]+\.\d{2}', text)
            if amt: scanned["amount"] = max(amt)
        except: pass
    return render_template('add.html', scanned_data=scanned)

@app.route('/save', methods=['POST'])
def save():
    if not session.get('logged_in'): return redirect(url_for('login'))
    d = request.form
    conn = get_db_connection()
    conn.execute("INSERT INTO sales (vendor, inv_no, amount, category, date, time) VALUES (?, ?, ?, ?, ?, ?)",
                 (d.get('vendor'), d.get('inv_no'), d.get('amount'), d.get('category'), d.get('date'), d.get('time')))
    conn.commit()
    conn.close()
    # إذا كان مدخل بيانات يرجع لصفحة الإضافة، وإذا مدير يروح للسجل
    if session.get('role') == 'entry':
        return redirect(url_for('add'))
    return redirect(url_for('logs'))

@app.route('/delete/<int:id>')
def delete(id):
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute("DELETE FROM sales WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('logs'))

# --- ميزة تصدير الإكسل (CSV) للمدير فقط ---
@app.route('/export_csv')
def export_csv():
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    sales = conn.execute("SELECT date, time, vendor, category, amount, inv_no FROM sales ORDER BY id DESC").fetchall()
    conn.close()

    def generate():
        # إضافة BOM عشان الإكسل يدعم اللغة العربية بدون مشاكل
        yield '\ufeff' 
        yield 'التاريخ,الوقت,المورد,الفئة,المبلغ,رقم الفاتورة\n'
        for row in sales:
            yield f"{row['date']},{row['time']},{row['vendor']},{row['category']},{row['amount']},{row['inv_no']}\n"

    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=sales_report.csv'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)