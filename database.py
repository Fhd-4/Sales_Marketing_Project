import sqlite3
import hashlib

# مسار ملف قاعدة البيانات
DB_FILE = 'final_project.db'

def get_db_connection():
    """
    تأسيس اتصال بقاعدة بيانات SQLite وإرجاع كائن الاتصال.
    تم إعداد صفوف قاعدة البيانات ليتم استرجاعها كقواميس (Row factory) ليسهل التعامل مع الحقول بأسمائها.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """
    تشفير كلمة المرور باستخدام خوارزمية SHA-256 لتأمينها في قاعدة البيانات.
    """
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    """
    تهيئة قاعدة البيانات وإنشاء الجداول المطلوبة إذا لم تكن موجودة مسبقاً.
    يتم إنشاء جدول المبيعات (sales) وجدول المستخدمين (users).
    كما يتم إنشاء حسابات افتراضية (admin و user) إذا كانت قاعدة البيانات فارغة.
    """
    conn = get_db_connection()
    
    # 1. إنشاء جدول المبيعات (الفواتير)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            vendor TEXT, 
            inv_no TEXT, 
            amount TEXT, 
            category TEXT, 
            date TEXT, 
            time TEXT
        )
    ''')
    
    # 2. إنشاء جدول المستخدمين
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    
    # 3. إدخال الحسابات الافتراضية إذا كان جدول المستخدمين فارغاً
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # حساب المدير الافتراضي (admin / 1234)
        admin_pass = hash_password("1234")
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", admin_pass, "admin")
        )
        
        # حساب مدخل البيانات الافتراضي (user / 0000)
        user_pass = hash_password("0000")
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("user", user_pass, "entry")
        )
        
        conn.commit()
        print("تمت تهيئة الحسابات الافتراضية بنجاح.")
        
    conn.close()

def create_user(username, password, role):
    """
    إنشاء حساب مستخدم جديد وتشفير كلمة المرور الخاصة به.
    يرجع True في حال النجاح، و False في حال كان اسم المستخدم مسجلاً مسبقاً.
    """
    conn = get_db_connection()
    hashed = hash_password(password)
    try:
        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role)
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # اسم المستخدم مسجل مسبقاً (Unique constraint failed)
        success = False
    finally:
        conn.close()
    return success

def verify_user(username, password):
    """
    التحقق من صحة بيانات تسجيل الدخول للمستخدم.
    يرجع بيانات المستخدم (كـ Row) إذا كانت صحيحة، أو None إذا كانت خاطئة.
    """
    conn = get_db_connection()
    hashed = hash_password(password)
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username, hashed)
    )
    result = user.fetchone()
    conn.close()
    return result
