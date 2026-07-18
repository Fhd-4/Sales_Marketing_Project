# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
import os
import re
import cv2
import pytesseract
from datetime import datetime

# استيراد إعدادات قاعدة البيانات والدوال المساعدة من ملف database.py
import database

app = Flask(__name__)
# مفتاح تشفير الجلسة لتأمين كوكيز المستخدمين
app.secret_key = 'smart_sales_analytics_final_2026' 

# تحديد مجلد رفع الصور وتأكيد وجوده
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# تكوين مسار محرك Tesseract OCR الخاص باستخراج النصوص من الصور
# لقد قمنا بتحديد المسار الصحيح على جهازك ليعمل النظام بدون أي مشاكل
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- دوال المساعدة للتحقق من الصلاحيات ---

def is_logged_in():
    """التحقق مما إذا كان المستخدم قد سجل الدخول أم لا"""
    return session.get('logged_in') is True

def get_user_role():
    """الحصول على دور المستخدم الحالي (admin أو entry)"""
    return session.get('role')

# --- مسارات الواجهة الأمامية (HTML Pages) ---

@app.route('/')
@app.route('/dashboard')
def dashboard():
    """عرض لوحة التحكم الرئيسية للمدير (إحصائيات المبيعات)"""
    if not is_logged_in():
        return redirect(url_for('login_page'))
    
    # حظر مدخل البيانات من الدخول للوحة التحكم وتوجيهه لصفحة إضافة الفواتير
    if get_user_role() != 'admin':
        return redirect(url_for('add_page'))
        
    # جلب إحصائيات المبيعات لعرضها في القالب
    conn = database.get_db_connection()
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

@app.route('/login')
def login_page():
    """عرض صفحة تسجيل الدخول"""
    if is_logged_in():
        return redirect(url_for('dashboard') if get_user_role() == 'admin' else url_for('add_page'))
    return render_template('login.html')

@app.route('/register')
def register_page():
    """عرض صفحة إنشاء حساب جديد"""
    if is_logged_in():
        return redirect(url_for('dashboard') if get_user_role() == 'admin' else url_for('add_page'))
    return render_template('register.html')

@app.route('/add')
def add_page():
    """عرض صفحة مسح وإضافة فواتير جديدة (متاحة للمدير ومدخل البيانات)"""
    if not is_logged_in():
        return redirect(url_for('login_page'))
    return render_template('add.html')

@app.route('/logs')
def logs_page():
    """عرض صفحة السجلات والبحث (خاصة بالمدير فقط)"""
    if not is_logged_in():
        return redirect(url_for('login_page'))
    if get_user_role() != 'admin':
        return redirect(url_for('add_page'))
        
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', 'all') 
    
    conn = database.get_db_connection()
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

@app.route('/logout')
def logout():
    """تسجيل خروج المستخدم ومسح الجلسة"""
    session.clear()
    return redirect(url_for('login_page'))

# --- واجهات برمجة التطبيقات (REST APIs) وتوثيق Swagger ---

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """
    API لتسجيل حساب مستخدم جديد.
    يتوقع بيانات بصيغة JSON تحتوي على اسم المستخدم، كلمة المرور، والدور.
    """
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'entry') # القيمة الافتراضية مدخل بيانات (entry)
    
    if not username or not password:
        return jsonify({"success": False, "message": "يجب إدخال اسم المستخدم وكلمة المرور"}), 400
        
    if role not in ['admin', 'entry']:
        return jsonify({"success": False, "message": "الدور المحدد غير صالح (يجب أن يكون admin أو entry)"}), 400
        
    success = database.create_user(username, password, role)
    if success:
        return jsonify({"success": True, "message": "تم تسجيل الحساب بنجاح!"}), 201
    else:
        return jsonify({"success": False, "message": "اسم المستخدم مسجل بالفعل!"}), 400

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """
    API لتسجيل الدخول.
    يتحقق من صحة البيانات ويقوم بإنشاء جلسة Flask للمستخدم.
    """
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"success": False, "message": "يجب إدخال اسم المستخدم وكلمة المرور"}), 400
        
    user = database.verify_user(username, password)
    if user:
        session['logged_in'] = True
        session['role'] = user['role']
        session['username'] = user['username']
        return jsonify({
            "success": True, 
            "message": "تم تسجيل الدخول بنجاح!",
            "role": user['role'],
            "username": user['username']
        }), 200
    else:
        return jsonify({"success": False, "message": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    """جلب إحصائيات لوحة التحكم كـ JSON (خاص بالمدير)"""
    if not is_logged_in() or get_user_role() != 'admin':
        return jsonify({"success": False, "message": "غير مصرح بالدخول"}), 403
        
    conn = database.get_db_connection()
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
    return jsonify({
        "success": True,
        "total": total,
        "aov": aov,
        "count": len(rows),
        "top_vendor": top_vendor,
        "top_category": top_category
    }), 200

@app.route('/api/logs', methods=['GET'])
def api_logs():
    """جلب قائمة الفواتير مع البحث والفلترة كـ JSON (خاص بالمدير)"""
    if not is_logged_in() or get_user_role() != 'admin':
        return jsonify({"success": False, "message": "غير مصرح بالدخول"}), 403
        
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', 'all') 
    
    conn = database.get_db_connection()
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
    
    # تحويل الصفوف لقائمة قواميس لإرسالها كـ JSON
    sales_list = []
    for r in data:
        sales_list.append({
            "id": r["id"],
            "vendor": r["vendor"],
            "inv_no": r["inv_no"],
            "amount": r["amount"],
            "category": r["category"],
            "date": r["date"],
            "time": r["time"]
        })
        
    return jsonify(sales_list), 200

@app.route('/api/scan', methods=['POST'])
def api_scan():
    """
    API لمعالجة صورة الفاتورة واستخراج نصوصها باستخدام تقنية OCR.
    يأخذ الصورة المرفوعة ويقوم بمعالجتها وإرجاع البيانات المستخرجة كـ JSON.
    """
    if not is_logged_in():
        return jsonify({"success": False, "message": "يجب تسجيل الدخول أولاً"}), 401
        
    file = request.files.get('file')
    # تهيئة البيانات الافتراضية للفاتورة
    scanned = {
        "vendor": "مورد غير معروف", 
        "inv_no": "REF-" + datetime.now().strftime("%M%S"), 
        "amount": "0.00", 
        "category": "أخرى", 
        "date": datetime.now().strftime("%Y-%m-%d"), 
        "time": datetime.now().strftime("%H:%M"),
        "filename": "" 
    }
    
    if file and file.filename != '':
        path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(path)
        scanned["filename"] = file.filename
        try:
            # قراءة الصورة باستخدام OpenCV
            img = cv2.imread(path)
            # استخراج النص من الصورة باستخدام pytesseract مع دعم اللغتين الإنجليزية والعربية
            text = pytesseract.image_to_string(img, lang='eng+ara')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # محاولة تخمين اسم المورد من السطر الأول
            if lines: 
                scanned["vendor"] = lines[0]
            
            # استخدام تعبير منتظم (Regular Expression) للبحث عن قيمة الفاتورة الرقمية
            amt = re.findall(r'[\d,]+\.\d{2}', text)
            if amt: 
                scanned["amount"] = max(amt)
        except Exception as e:
            # إرجاع الخطأ في حال حدوث فشل في معالجة الصور
            return jsonify({"success": False, "message": f"حدث خطأ أثناء معالجة الصورة: {str(e)}"}), 500
            
    return jsonify(scanned), 200

@app.route('/api/save', methods=['POST'])
def api_save():
    """
    API لحفظ بيانات الفاتورة المعتمدة في قاعدة البيانات.
    """
    if not is_logged_in():
        return jsonify({"success": False, "message": "يجب تسجيل الدخول أولاً"}), 401
        
    data = request.get_json() or {}
    vendor = data.get('vendor')
    inv_no = data.get('inv_no')
    amount = data.get('amount')
    category = data.get('category', 'أخرى')
    date = data.get('date') or datetime.now().strftime("%Y-%m-%d")
    time = data.get('time') or datetime.now().strftime("%H:%M")
    
    if not vendor or not amount:
        return jsonify({"success": False, "message": "يجب إدخال اسم المورد والمبلغ"}), 400
        
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO sales (vendor, inv_no, amount, category, date, time) VALUES (?, ?, ?, ?, ?, ?)",
        (vendor, inv_no, amount, category, date, time)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "تم حفظ الفاتورة بنجاح!"}), 201

@app.route('/api/delete/<int:id>', methods=['DELETE'])
def api_delete(id):
    """API لحذف فاتورة محددة (متاح للمدير فقط)"""
    if not is_logged_in() or get_user_role() != 'admin':
        return jsonify({"success": False, "message": "غير مصرح لك بحذف الفواتير"}), 403
        
    conn = database.get_db_connection()
    # التحقق من وجود السجل قبل حذفه
    record = conn.execute("SELECT id FROM sales WHERE id = ?", (id,)).fetchone()
    if not record:
        conn.close()
        return jsonify({"success": False, "message": "السجل غير موجود"}), 404
        
    conn.execute("DELETE FROM sales WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "تم حذف السجل بنجاح!"}), 200

# --- ميزة تصدير الإكسل (CSV) للمدير فقط ---
@app.route('/export_csv')
def export_csv():
    """تصدير تقرير المبيعات بصيغة CSV ملائم لبرنامج Excel يدعم اللغة العربية"""
    if not is_logged_in() or get_user_role() != 'admin': 
        return redirect(url_for('login_page'))
        
    conn = database.get_db_connection()
    sales = conn.execute("SELECT date, time, vendor, category, amount, inv_no FROM sales ORDER BY id DESC").fetchall()
    conn.close()

    def generate():
        # إضافة BOM (Byte Order Mark) للـ UTF-8 ليدعم Excel قراءة اللغة العربية بشكل سليم
        yield '\ufeff' 
        yield 'التاريخ,الوقت,المورد,الفئة,المبلغ,رقم الفاتورة\n'
        for row in sales:
            yield f"{row['date']},{row['time']},{row['vendor']},{row['category']},{row['amount']},{row['inv_no']}\n"

    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=sales_report.csv'})

# --- مسارات توثيق Swagger UI ---

@app.route('/api/docs')
def swagger_ui():
    """تقديم واجهة Swagger UI التفاعلية لتجربة الـ APIs"""
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="UTF-8">
      <title>توثيق واجهات برمجة التطبيقات (APIs)</title>
      <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3/swagger-ui.css" >
      <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin:0; background: #fafafa; font-family: sans-serif; }
        /* تغيير اتجاه النصوص لتوثيق أفضل */
        .swagger-ui { direction: ltr; }
      </style>
    </head>
    <body>
      <div id="swagger-ui"></div>
      <script src="https://unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js"> </script>
      <script src="https://unpkg.com/swagger-ui-dist@3/swagger-ui-standalone-preset.js"> </script>
      <script>
        window.onload = function() {
          const ui = SwaggerUIBundle({
            url: "/static/swagger.json",
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
              SwaggerUIBundle.presets.apis,
              SwaggerUIStandalonePreset
            ],
            plugins: [
              SwaggerUIBundle.plugins.DownloadUrl
            ],
            layout: "StandaloneLayout"
          });
          window.ui = ui;
        };
      </script>
    </body>
    </html>
    """

# --- تشغيل وتهيئة التطبيق ---

if __name__ == '__main__':
    # تهيئة جداول قاعدة البيانات وإدخال الحسابات الافتراضية
    database.init_db()
    # تشغيل الخادم على المنفذ 5000 مع تمكين وضع التطوير
    app.run(host='0.0.0.0', port=5000, debug=True)