# =================== SILENCE TF & MEDIAPIPE ===================
import os
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"
os.environ["MEDIAPIPE_DISABLE_GPU"] = "1"

# ==============================================================
import logging
logging.getLogger("tensorflow").setLevel(logging.ERROR)
logging.getLogger("mediapipe").setLevel(logging.ERROR)

# =================== IMPORT YANG DIPERLUKAN ===================


from datetime import datetime, date, time, timedelta
import math
import json
import pandas as pd
from io import BytesIO
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask import flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Employee, ShiftSetting, FaceEncoding, Attendance, LeaveRequest
from face_engine import get_face_engine
from flask_migrate import Migrate

# ==============================================================

# Initialize Flask app
from config import get_config, Config

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # Ambil config sesuai environment
    config_class = get_config()
    app.config.from_object(config_class)

    app.config["SQLALCHEMY_DATABASE_URI"] = config_class.build_database_uri()


    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Init config tambahan
    config_class.init_app(app)

    return app


app = create_app()

# ========== CONTEXT PROCESSOR FOR TEMPLATES ==========
@app.context_processor
def utility_processor():
    """Make utility functions available in all templates"""
    def now():
        return datetime.now()
    
    def today():
        return date.today()
    
    return dict(now=now, today=today, datetime=datetime, date=date)
# ======================================================

# ========== HELPER FUNCTIONS ==========
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in meters using Haversine formula"""
    if None in [lat1, lon1, lat2, lon2]:
        return float('inf')
    
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000  # Radius of Earth in meters
    return c * r

def is_within_radius(lat1, lon1, lat2, lon2, radius_meters=50):
    """Check if two points are within specified radius"""
    distance = calculate_distance(lat1, lon1, lat2, lon2)
    return distance <= radius_meters

def get_attendance_status(check_in_time, shift_start_time, tolerance_minutes=5):
    """Determine attendance status based on check-in time"""
    if check_in_time is None:
        return 'ALPA'
    
    # Convert times to minutes since midnight
    check_in_minutes = check_in_time.hour * 60 + check_in_time.minute
    shift_start_minutes = shift_start_time.hour * 60 + shift_start_time.minute
    
    if check_in_minutes <= shift_start_minutes + tolerance_minutes:
        return 'HADIR'
    else:
        return 'TERLAMBAT'

def generate_employee_code():
    """Generate kode karyawan: EMP-YYMM-XXXX"""
    year_month = datetime.now().strftime("%y%m")
    
    # Query terakhir
    last_emp = Employee.query.filter(
        Employee.kode.like(f"EMP-{year_month}-%")
    ).order_by(Employee.kode.desc()).first()
    
    if last_emp:
        last_num = int(last_emp.kode.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1
    
    return f"EMP-{year_month}-{new_num:04d}"

# ========== AUTHENTICATION DECORATORS ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'OWNER':
            flash('Akses ditolak. Hanya owner yang dapat mengakses halaman ini.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ========== ROUTES ==========

@app.route('/')
def index():
    """Redirect to appropriate page based on login status"""
    if 'user_id' in session:
        if session.get('role') == 'OWNER':
            return redirect(url_for('dashboard'))
        elif session.get('role') == 'KARYAWAN':
            return redirect(url_for('absen_page'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login for owner only"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['email'] = user.email
            session['role'] = user.role
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Email atau password salah!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

# ========== PUBLIC PAGES (NO LOGIN REQUIRED) ==========

@app.route('/absen')
def absen_page():
    """Attendance page for employees (no login required)"""
    return render_template('absen.html')

# ========== PUBLIC APIs FOR ABSEN PAGE ==========

@app.route('/api/public/dashboard-stats')
def public_dashboard_stats():
    """Public dashboard stats (no login required)"""
    try:
        # Basic stats for public display
        total_employees = Employee.query.filter_by(aktif=True).count()
        today = date.today()
        
        # Count today's attendance
        today_attendance = Attendance.query.filter_by(tanggal=today).count()
        
        # Count late arrivals today
        late_today = Attendance.query.filter_by(
            tanggal=today, 
            status='TERLAMBAT'
        ).count()
        
        # Count check-ins today (check_in is not null)
        check_in_count = Attendance.query.filter(
            Attendance.tanggal == today,
            Attendance.check_in != None
        ).count()
        
        # Count check-outs today (check_out is not null)
        check_out_count = Attendance.query.filter(
            Attendance.tanggal == today,
            Attendance.check_out != None
        ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_employees': total_employees,
                'today_attendance': today_attendance,
                'late_today': late_today,
                'check_in_count': check_in_count,
                'check_out_count': check_out_count
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/public/attendance-today')
def public_today_attendance():
    """Public today's attendance (no login required)"""
    try:
        today = date.today()
        
        attendance = Attendance.query\
            .join(Employee, Attendance.employee_id == Employee.id)\
            .add_columns(
                Employee.nama,
                Attendance.check_in,
                Attendance.check_out,
                Attendance.status,
                Attendance.similarity
            )\
            .filter(Attendance.tanggal == today)\
            .order_by(Attendance.dibuat.desc())\
            .limit(10)\
            .all()
        
        data = []
        for record in attendance:
            data.append({
                'nama': record.nama,
                'check_in': record.check_in.strftime('%H:%M') if record.check_in else '-',
                'check_out': record.check_out.strftime('%H:%M') if record.check_out else '-',
                'status': record.status,
                'similarity': f"{record.similarity:.1%}" if record.similarity else '-'
            })
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== ROUTE ABSEN UTAMA (FACE RECOGNITION + GPS) ==========

@app.route('/api/absen', methods=['POST'])
def absen():
    """Handle attendance check-in/check-out (Railway safe)"""
    try:
        print("=== ABSEN REQUEST STARTED ===")

        # LAZY SAFE IMPORT
        try:
            from face_engine import get_face_engine
            cv2 = __import__("cv2")
            import numpy as np
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Face recognition engine not available'
            }), 503

        # 1. CHECK IMAGE
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image provided'}), 400

        image_file = request.files['image']
        image_bytes = image_file.read()

        if not image_bytes:
            return jsonify({'success': False, 'message': 'Empty image'}), 400

        # 2. DECODE IMAGE
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            return jsonify({'success': False, 'message': 'Invalid image'}), 400

        # 3. FACE RECOGNITION
        try:
            face_engine = get_face_engine()
            result = face_engine.process_attendance(image)
        except Exception as e:
            print(f"[FACE ERROR] {e}")
            return jsonify({
                'success': False,
                'action': 'REJECTED',
                'message': 'Face recognition failed'
            }), 400

        # 4. VALIDATION
        if not result.get('liveness_ok'):
            return jsonify({
                'success': False,
                'action': 'REJECTED',
                'message': 'Liveness check failed'
            }), 400

        employee_id = result.get('employee_id')
        if not employee_id:
            return jsonify({
                'success': False,
                'action': 'REJECTED',
                'message': 'Face not recognized'
            }), 400

        # 5. DATABASE
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404

        today = date.today()
        now = datetime.now()

        attendance = Attendance.query.filter_by(
            employee_id=employee.id,
            tanggal=today
        ).first()

        lat = request.form.get('latitude')
        lon = request.form.get('longitude')

        lat = float(lat) if lat else None
        lon = float(lon) if lon else None

        if not attendance:
            new_attendance = Attendance(
                employee_id=employee.id,
                tanggal=today,
                check_in=now,
                status='HADIR',
                latitude=lat,
                longitude=lon,
                similarity=result.get('similarity', 0),
                liveness_ok=True
            )
            db.session.add(new_attendance)
            db.session.commit()

            return jsonify({
                'success': True,
                'action': 'CHECK_IN',
                'employee': employee.nama,
                'time': now.strftime('%H:%M:%S')
            })

        if attendance.check_in and not attendance.check_out:
            attendance.check_out = now
            attendance.latitude = lat
            attendance.longitude = lon
            db.session.commit()

            return jsonify({
                'success': True,
                'action': 'CHECK_OUT',
                'employee': employee.nama,
                'check_in': attendance.check_in.strftime('%H:%M:%S'),
                'check_out': now.strftime('%H:%M:%S')
            })

        return jsonify({
            'success': False,
            'message': 'Attendance already completed'
        }), 400

    except Exception as e:
        db.session.rollback()
        print("[CRITICAL ERROR]", e)
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500


# ========== OWNER PAGES (LOGIN REQUIRED) ==========

@app.route('/dashboard')
@login_required
@owner_required
def dashboard():
    """Owner dashboard"""
    # Get statistics
    total_employees = Employee.query.count()
    active_employees = Employee.query.filter_by(aktif=True).count()
    
    today = date.today()
    today_attendance = Attendance.query.filter_by(tanggal=today).count()
    
    # Get recent attendance
    recent_attendance = Attendance.query\
        .join(Employee, Attendance.employee_id == Employee.id)\
        .add_columns(
            Employee.nama,
            Attendance.tanggal,
            Attendance.check_in,
            Attendance.check_out,
            Attendance.status
        )\
        .order_by(Attendance.dibuat.desc())\
        .limit(10)\
        .all()
    
    # Get pending leave requests
    pending_leaves = LeaveRequest.query\
        .filter_by(status='PENDING')\
        .count()
    
    return render_template('dashboard.html',
                         total_employees=total_employees,
                         active_employees=active_employees,
                         today_attendance=today_attendance,
                         pending_leaves=pending_leaves,
                         recent_attendance=recent_attendance)

@app.route('/api/dashboard/late-today')
@login_required
@owner_required
def get_late_employees_today():
    """Get employees who are late today"""
    try:
        today = date.today()
        
        # Query untuk karyawan terlambat hari ini
        late_employees = Attendance.query\
            .join(Employee, Attendance.employee_id == Employee.id)\
            .join(ShiftSetting, Employee.shift_id == ShiftSetting.id, isouter=True)\
            .filter(
                Attendance.tanggal == today,
                Attendance.status == 'TERLAMBAT',
                Attendance.check_in.isnot(None)
            )\
            .add_columns(
                Employee.kode,
                Employee.nama,
                Employee.posisi,
                ShiftSetting.jam_masuk,
                Attendance.check_in,
                Attendance.status
            )\
            .order_by(Attendance.check_in)\
            .all()
        
        data = []
        for emp in late_employees:
            # Hitung keterlambatan dalam menit
            if emp.jam_masuk and emp.check_in:
                shift_start_minutes = emp.jam_masuk.hour * 60 + emp.jam_masuk.minute
                check_in_minutes = emp.check_in.hour * 60 + emp.check_in.minute
                terlambat_menit = check_in_minutes - shift_start_minutes
            else:
                terlambat_menit = 0
            
            data.append({
                'kode': emp.kode,
                'nama': emp.nama,
                'posisi': emp.posisi if hasattr(emp, 'posisi') else '-',
                'jam_masuk': emp.jam_masuk.strftime('%H:%M') if emp.jam_masuk else '-',
                'check_in': emp.check_in.strftime('%H:%M') if emp.check_in else '-',
                'terlambat_menit': max(0, terlambat_menit)
            })
        
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/karyawan')
@login_required
@owner_required
def karyawan():
    """Employee management page"""
    employees = Employee.query\
        .join(ShiftSetting, Employee.shift_id == ShiftSetting.id, isouter=True)\
        .add_columns(
            Employee.id,
            Employee.kode,
            Employee.nama,
            Employee.email,
            Employee.aktif,
            Employee.foto_profil,
            ShiftSetting.nama.label('shift_nama'),
            Employee.dibuat
        )\
        .order_by(Employee.dibuat.desc())\
        .all()
    
    shifts = ShiftSetting.query.filter_by(aktif=True).all()
    return render_template('karyawan.html', employees=employees, shifts=shifts)

@app.route('/register-face-general')
@login_required
@owner_required
def register_face_general():
    """General face registration page"""
    employees = Employee.query.filter_by(aktif=True).all()
    return render_template('register_face_general.html', employees=employees)

@app.route('/register-face')
@login_required
@owner_required
def register_face_page():
    """Page for registering face for specific employee"""
    employee_id = request.args.get('employee_id', type=int)
    if not employee_id:
        return redirect(url_for('karyawan'))
    
    employee = Employee.query.get(employee_id)
    if not employee:
        flash('Karyawan tidak ditemukan', 'danger')
        return redirect(url_for('karyawan'))
    
    return render_template('register_face.html', employee=employee)

@app.route('/shift')
@login_required
@owner_required
def shift_management():
    """Shift management page"""
    shifts = ShiftSetting.query.order_by(ShiftSetting.dibuat.desc()).all()
    return render_template('shift.html', shifts=shifts)

@app.route('/izin')
@login_required
@owner_required
def leave_management():
    """Leave request management page"""
    leaves = LeaveRequest.query\
        .join(Employee, LeaveRequest.employee_id == Employee.id)\
        .add_columns(
            LeaveRequest.id,
            LeaveRequest.alasan,
            LeaveRequest.tanggal_mulai,
            LeaveRequest.tanggal_selesai,
            LeaveRequest.status,
            LeaveRequest.bukti_foto,
            LeaveRequest.dibuat,
            Employee.kode,
            Employee.nama
        )\
        .order_by(LeaveRequest.dibuat.desc())\
        .all()
    
    return render_template('izin.html', leaves=leaves)

@app.route('/laporan')
@login_required
@owner_required
def reports():
    """Report generation page"""
    employees = Employee.query.filter_by(aktif=True).all()
    return render_template('laporan.html', employees=employees)

# ========== OWNER APIs (LOGIN REQUIRED) ==========

@app.route('/api/karyawan', methods=['POST'])
@login_required
@owner_required
def add_employee():
    """Add new employee with AUTO-GENERATED code"""
    try:
        # AUTO-GENERATE KODE
        kode = generate_employee_code()
        
        nama = request.form.get('nama')
        email = request.form.get('email')
        shift_id = request.form.get('shift_id')
        
        if not nama:
            return jsonify({'success': False, 'message': 'Nama wajib diisi'})
        
        # Validasi shift hanya PAGI/SIANG
        if shift_id:
            shift = ShiftSetting.query.get(shift_id)
            if shift and shift.nama not in ['PAGI', 'SIANG']:
                return jsonify({
                    'success': False, 
                    'message': 'Hanya shift PAGI dan SIANG yang diperbolehkan'
                })
        
        employee = Employee(
            kode=kode,
            nama=nama,
            email=email or None,
            shift_id=int(shift_id) if shift_id else None,
            aktif=True,
            dibuat=datetime.utcnow()
        )
        
        db.session.add(employee)
        db.session.commit()
        
        # If face image was uploaded, register it
        if 'face_image' in request.files:
            image_data = request.files['face_image']
            if image_data:
                # Extract face encoding
                encoding = face_engine.extract_face_encoding(image_data.read())
                if encoding:
                    # Save face encoding
                    face_encoding = FaceEncoding(
                        employee_id=employee.id,
                        encoding=encoding,
                        dibuat=datetime.utcnow()
                    )
                    db.session.add(face_encoding)
                    # Update cache
                    face_engine.add_face_encoding(employee.id, encoding)
                    db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Karyawan berhasil ditambahkan. Kode: {kode}',
            'employee_id': employee.id,
            'kode': kode
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/karyawan/<int:employee_id>', methods=['PUT', 'DELETE'])
@login_required
@owner_required
def manage_employee(employee_id):
    """Update or delete employee"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        if request.method == 'PUT':
            # Update employee
            data = request.json
            employee.nama = data.get('nama', employee.nama)
            employee.email = data.get('email', employee.email)
            employee.shift_id = data.get('shift_id', employee.shift_id)
            employee.aktif = data.get('aktif', employee.aktif)
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Karyawan berhasil diperbarui'})
            
        elif request.method == 'DELETE':
            # Soft delete by setting aktif=False
            employee.aktif = False
            db.session.commit()
            return jsonify({'success': True, 'message': 'Karyawan berhasil dinonaktifkan'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/karyawan-with-face-status')
@login_required
@owner_required
def get_employees_with_face_status():
    """Get all employees with face registration status"""
    try:
        employees = Employee.query\
            .outerjoin(FaceEncoding, Employee.id == FaceEncoding.employee_id)\
            .add_columns(
                Employee.id,
                Employee.kode,
                Employee.nama,
                Employee.email,
                Employee.aktif,
                Employee.shift_id,
                FaceEncoding.id.label('face_encoding_id'),
                Employee.dibuat
            )\
            .order_by(Employee.nama)\
            .all()
        
        data = []
        for emp in employees:
            data.append({
                'id': emp.id,
                'kode': emp.kode,
                'nama': emp.nama,
                'email': emp.email or '',
                'aktif': emp.aktif,
                'shift_id': emp.shift_id,
                'face_registered': emp.face_encoding_id is not None,
                'dibuat': emp.dibuat.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/register-face', methods=['POST'])
@login_required
@owner_required
def register_face():
    """Register employee face"""
    try:
        employee_id = request.form.get('employee_id', type=int)
        image_data = request.files.get('image')
        
        if not employee_id or not image_data:
            return jsonify({'success': False, 'message': 'Employee ID dan gambar wajib'})
        
        # Check employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'message': 'Karyawan tidak ditemukan'})
        
        # Read image bytes
        image_bytes = image_data.read()
        
        # Extract face encoding
        encoding = face_engine.extract_face_encoding(image_bytes)
        if encoding is None:
            return jsonify({'success': False, 'message': 'Wajah tidak terdeteksi dalam gambar'})
        
        # Check if face encoding already exists
        existing = FaceEncoding.query.filter_by(employee_id=employee_id).first()
        
        if existing:
            # Update existing encoding
            existing.encoding = encoding
            existing.dibuat = datetime.utcnow()
        else:
            # Create new encoding
            face_encoding = FaceEncoding(
                employee_id=employee_id,
                encoding=encoding,
                dibuat=datetime.utcnow()
            )
            db.session.add(face_encoding)
        
        # Update cache
        face_engine.add_face_encoding(employee_id, encoding)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Wajah berhasil didaftarkan'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/shift', methods=['POST'])
@login_required
@owner_required
def add_shift():
    """Add new shift"""
    try:
        # Ambil data dari JSON (bukan form)
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'Data tidak valid'}), 400
        
        nama = data.get('nama')
        jam_masuk = data.get('jam_masuk')
        jam_pulang = data.get('jam_pulang')
        toleransi_menit = data.get('toleransi_menit', 5)
        aktif = data.get('aktif', True)
        
        print(f"Creating shift: nama={nama}, jam_masuk={jam_masuk}, jam_pulang={jam_pulang}")
        
        if not nama or not jam_masuk or not jam_pulang:
            return jsonify({'success': False, 'message': 'Semua field wajib diisi'}), 400
        
        # Validasi nama shift hanya PAGI atau SIANG
        if nama not in ['PAGI', 'SIANG']:
            return jsonify({
                'success': False, 
                'message': 'Nama shift hanya boleh PAGI atau SIANG'
            }), 400
        
        # Check if shift name exists
        existing = ShiftSetting.query.filter_by(nama=nama).first()
        if existing:
            return jsonify({'success': False, 'message': 'Nama shift sudah digunakan'}), 400
        
        # Parse waktu - handle format HH:MM atau HH:MM:SS
        try:
            if len(jam_masuk) == 5:  # HH:MM
                jam_masuk_time = datetime.strptime(jam_masuk, '%H:%M').time()
            else:  # HH:MM:SS
                jam_masuk_time = datetime.strptime(jam_masuk, '%H:%M:%S').time()
                
            if len(jam_pulang) == 5:  # HH:MM
                jam_pulang_time = datetime.strptime(jam_pulang, '%H:%M').time()
            else:  # HH:MM:SS
                jam_pulang_time = datetime.strptime(jam_pulang, '%H:%M:%S').time()
        except ValueError as e:
            return jsonify({'success': False, 'message': f'Format waktu tidak valid: {str(e)}'}), 400
        
        shift = ShiftSetting(
            nama=nama,
            jam_masuk=jam_masuk_time,
            jam_pulang=jam_pulang_time,
            toleransi_menit=toleransi_menit,
            aktif=aktif,
            dibuat=datetime.utcnow()
        )
        
        db.session.add(shift)
        db.session.commit()
        
        # Return data dengan format yang konsisten
        return jsonify({
            'success': True,
            'message': 'Shift berhasil ditambahkan',
            'data': {
                'id': shift.id,
                'nama': shift.nama,
                'jam_masuk': shift.jam_masuk.strftime('%H:%M:%S'),
                'jam_pulang': shift.jam_pulang.strftime('%H:%M:%S'),
                'toleransi_menit': shift.toleransi_menit,
                'aktif': shift.aktif,
                'dibuat': shift.dibuat.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in /api/shift POST: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/shift/<int:shift_id>', methods=['PUT', 'DELETE'])
@login_required
@owner_required
def manage_shift(shift_id):
    """Update or delete shift"""
    try:
        shift = ShiftSetting.query.get_or_404(shift_id)
        
        if request.method == 'PUT':
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'Data tidak valid'}), 400

            shift.nama = data.get('nama', shift.nama)

            if 'jam_masuk' in data:
                shift.jam_masuk = datetime.strptime(
                    data['jam_masuk'], '%H:%M:%S'
                ).time()

            if 'jam_pulang' in data:
                shift.jam_pulang = datetime.strptime(
                    data['jam_pulang'], '%H:%M:%S'
                ).time()

            if 'toleransi_menit' in data:
                shift.toleransi_menit = data['toleransi_menit']

            if 'aktif' in data:
                shift.aktif = data['aktif']

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Shift berhasil diperbarui'
            })

            
        elif request.method == 'DELETE':
            print(f"Deleting shift {shift_id}")
            
            # Cek apakah shift digunakan oleh karyawan
            employee_count = Employee.query.filter_by(shift_id=shift_id).count()
            if employee_count > 0:
                return jsonify({
                    'success': False, 
                    'message': f'Tidak dapat menghapus shift yang digunakan oleh {employee_count} karyawan'
                }), 400
            
            # Delete shift
            db.session.delete(shift)
            db.session.commit()
            
            print(f"Shift {shift_id} deleted successfully")
            return jsonify({
                'success': True, 
                'message': 'Shift berhasil dihapus'
            })
            
    except Exception as e:
        db.session.rollback()
        print(f"Error in /api/shift/{shift_id}: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/shifts', methods=['GET'])
@login_required
@owner_required
def get_shifts():
    """Get all shifts for dropdown"""
    try:
        shifts = ShiftSetting.query.order_by(ShiftSetting.nama).all()
        
        data = []
        for shift in shifts:
            data.append({
                'id': shift.id,
                'nama': shift.nama,
                'jam_masuk': shift.jam_masuk.strftime('%H:%M:%S'),  # PERUBAHAN: tambah :%S
                'jam_pulang': shift.jam_pulang.strftime('%H:%M:%S'),  # PERUBAHAN: tambah :%S
                'toleransi_menit': shift.toleransi_menit,
                'aktif': shift.aktif,
                'dibuat': shift.dibuat.strftime('%Y-%m-%d %H:%M:%S') if shift.dibuat else None
            })
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        print(f"Error in /api/shifts: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/shift/bulk-assign', methods=['POST'])
def bulk_assign():
    data = request.json
    shift_id = data['shift_id']
    employee_ids = data['employee_ids']

    Employee.query.filter(Employee.id.in_(employee_ids)) \
        .update({Employee.shift_id: shift_id}, synchronize_session=False)

    db.session.commit()
    return jsonify(success=True)


@app.route('/api/izin', methods=['POST'])
def submit_leave():
    """Submit leave request (employee without login)"""
    try:
        kode_karyawan = request.form.get('kode_karyawan')
        alasan = request.form.get('alasan')
        tanggal_mulai = request.form.get('tanggal_mulai')
        tanggal_selesai = request.form.get('tanggal_selesai')
        bukti_foto = request.files.get('bukti_foto')
        
        if not kode_karyawan or not alasan or not tanggal_mulai or not tanggal_selesai:
            return jsonify({'success': False, 'message': 'Semua field wajib diisi'})
        
        # Find employee
        employee = Employee.query.filter_by(kode=kode_karyawan, aktif=True).first()
        if not employee:
            return jsonify({'success': False, 'message': 'Karyawan tidak ditemukan atau tidak aktif'})
        
        # Validate dates
        tgl_mulai = datetime.strptime(tanggal_mulai, '%Y-%m-%d').date()
        tgl_selesai = datetime.strptime(tanggal_selesai, '%Y-%m-%d').date()
        
        if tgl_mulai > tgl_selesai:
            return jsonify({'success': False, 'message': 'Tanggal mulai tidak boleh setelah tanggal selesai'})
        
        # Handle file upload
        bukti_filename = None
        if bukti_foto:
            filename = secure_filename(f"izin_{employee.id}_{datetime.now().timestamp()}.jpg")
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'leaves', filename)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)
            bukti_foto.save(upload_path)
            bukti_filename = f"uploads/leaves/{filename}"
        
        # Create leave request
        leave = LeaveRequest(
            employee_id=employee.id,
            alasan=alasan,
            tanggal_mulai=tgl_mulai,
            tanggal_selesai=tgl_selesai,
            bukti_foto=bukti_filename,
            status='PENDING',
            dibuat=datetime.utcnow()
        )
        
        db.session.add(leave)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Permohonan izin berhasil diajukan'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/izin/<int:leave_id>', methods=['PUT'])
@login_required
@owner_required
def update_leave_status(leave_id):
    """Approve or reject leave request"""
    try:
        leave = LeaveRequest.query.get_or_404(leave_id)
        status = request.json.get('status')
        
        if status not in ['DISETUJUI', 'DITOLAK']:
            return jsonify({'success': False, 'message': 'Status tidak valid'})
        
        leave.status = status
        db.session.commit()
        
        # If approved, update attendance records
        if status == 'DISETUJUI':
            current_date = leave.tanggal_mulai
            while current_date <= leave.tanggal_selesai:
                attendance = Attendance.query.filter_by(
                    employee_id=leave.employee_id,
                    tanggal=current_date
                ).first()
                
                if not attendance:
                    # Create attendance record with IZIN status
                    attendance = Attendance(
                        employee_id=leave.employee_id,
                        tanggal=current_date,
                        status='IZIN',
                        dibuat=datetime.utcnow()
                    )
                    db.session.add(attendance)
                
                current_date += timedelta(days=1)
            
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Permohonan izin {status.lower()}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/leaves', methods=['GET'])
@login_required
@owner_required
def get_leaves():
    """Get all leave requests"""
    try:
        leaves = LeaveRequest.query\
            .join(Employee, LeaveRequest.employee_id == Employee.id)\
            .add_columns(
                LeaveRequest.id,
                LeaveRequest.alasan,
                LeaveRequest.tanggal_mulai,
                LeaveRequest.tanggal_selesai,
                LeaveRequest.status,
                LeaveRequest.bukti_foto,
                LeaveRequest.dibuat,
                Employee.kode,
                Employee.nama
            )\
            .order_by(LeaveRequest.dibuat.desc())\
            .all()
        
        data = []
        for leave in leaves:
            data.append({
                'id': leave.id,
                'kode': leave.kode,
                'nama': leave.nama,
                'alasan': leave.alasan,
                'tanggal_mulai': leave.tanggal_mulai.strftime('%Y-%m-%d'),
                'tanggal_selesai': leave.tanggal_selesai.strftime('%Y-%m-%d'),
                'status': leave.status,
                'bukti_foto': leave.bukti_foto or '',
                'dibuat': leave.dibuat.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/laporan', methods=['GET'])
@login_required
@owner_required
def generate_report():
    """Generate attendance report"""
    try:
        employee_id = request.args.get('employee_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export_type = request.args.get('export_type', 'json')
        
        # Build query
        query = Attendance.query\
            .join(Employee, Attendance.employee_id == Employee.id)\
            .join(ShiftSetting, Employee.shift_id == ShiftSetting.id, isouter=True)\
            .add_columns(
                Employee.kode,
                Employee.nama,
                Attendance.tanggal,
                Attendance.check_in,
                Attendance.check_out,
                Attendance.status,
                Attendance.latitude,
                Attendance.longitude,
                Attendance.similarity,
                Attendance.liveness_ok,
                ShiftSetting.nama.label('shift_nama'),
                ShiftSetting.jam_masuk,
                ShiftSetting.jam_pulang
            )
        
        # Apply filters
        if employee_id:
            query = query.filter(Attendance.employee_id == employee_id)
        
        if start_date:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.tanggal >= start_dt)
        
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.tanggal <= end_dt)
        
        # Execute query
        records = query.order_by(Attendance.tanggal.desc()).all()
        
        if export_type == 'json':
            # Return JSON data
            data = []
            for record in records:
                data.append({
                    'kode': record.kode,
                    'nama': record.nama,
                    'tanggal': record.tanggal.strftime('%Y-%m-%d'),
                    'check_in': record.check_in.strftime('%H:%M') if record.check_in else '',
                    'check_out': record.check_out.strftime('%H:%M') if record.check_out else '',
                    'status': record.status,
                    'shift': record.shift_nama,
                    'jam_masuk': record.jam_masuk.strftime('%H:%M') if record.jam_masuk else '',
                    'jam_pulang': record.jam_pulang.strftime('%H:%M') if record.jam_pulang else '',
                    'similarity': f"{record.similarity:.2f}" if record.similarity else '',
                    'liveness_ok': 'Ya' if record.liveness_ok else 'Tidak'
                })
            
            return jsonify({'success': True, 'data': data})
        
        elif export_type == 'excel':
            # Create Excel file
            df_data = []
            for record in records:
                df_data.append({
                    'Kode': record.kode,
                    'Nama': record.nama,
                    'Tanggal': record.tanggal.strftime('%Y-%m-%d'),
                    'Check In': record.check_in.strftime('%H:%M') if record.check_in else '',
                    'Check Out': record.check_out.strftime('%H:%M') if record.check_out else '',
                    'Status': record.status,
                    'Shift': record.shift_nama,
                    'Jam Masuk Shift': record.jam_masuk.strftime('%H:%M') if record.jam_masuk else '',
                    'Jam Pulang Shift': record.jam_pulang.strftime('%H:%M') if record.jam_pulang else '',
                    'Similarity': f"{record.similarity:.2f}" if record.similarity else '',
                    'Liveness OK': 'Ya' if record.liveness_ok else 'Tidak'
                })
            
            df = pd.DataFrame(df_data)
            
            # Create Excel in memory
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Laporan Absensi', index=False)
            
            output.seek(0)
            
            filename = f"laporan_absensi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/dashboard-stats')
@login_required
@owner_required
def dashboard_stats():
    """Get dashboard statistics (owner only)"""
    try:
        today = date.today()
        
        # Basic stats
        total_employees = Employee.query.filter_by(aktif=True).count()
        today_attendance = Attendance.query.filter_by(tanggal=today).count()
        pending_leaves = LeaveRequest.query.filter_by(status='PENDING').count()
        
        # Attendance by status today
        today_status = db.session.query(
            Attendance.status,
            db.func.count(Attendance.id)
        ).filter_by(tanggal=today)\
         .group_by(Attendance.status)\
         .all()
        
        status_data = {status: count for status, count in today_status}
        
        # Weekly attendance trend
        week_ago = today - timedelta(days=7)
        weekly_data = db.session.query(
            Attendance.tanggal,
            db.func.count(Attendance.id)
        ).filter(Attendance.tanggal >= week_ago)\
         .group_by(Attendance.tanggal)\
         .order_by(Attendance.tanggal)\
         .all()
        
        weekly_labels = [d[0].strftime('%d/%m') for d in weekly_data]
        weekly_counts = [d[1] for d in weekly_data]
        
        # Late arrivals today
        late_today = Attendance.query\
            .filter_by(tanggal=today, status='TERLAMBAT')\
            .count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_employees': total_employees,
                'today_attendance': today_attendance,
                'attendance_rate': round((today_attendance / total_employees * 100), 1) if total_employees > 0 else 0,
                'pending_leaves': pending_leaves,
                'late_today': late_today
            },
            'status_data': status_data,
            'weekly_labels': weekly_labels,
            'weekly_counts': weekly_counts
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/attendance-today')
@login_required
@owner_required
def today_attendance():
    """Get today's attendance details (owner only)"""
    try:
        today = date.today()
        
        attendance = Attendance.query\
            .join(Employee, Attendance.employee_id == Employee.id)\
            .join(ShiftSetting, Employee.shift_id == ShiftSetting.id, isouter=True)\
            .add_columns(
                Employee.kode,
                Employee.nama,
                Attendance.check_in,
                Attendance.check_out,
                Attendance.status,
                Attendance.similarity,
                Attendance.liveness_ok,
                ShiftSetting.nama.label('shift_nama')
            )\
            .filter(Attendance.tanggal == today)\
            .order_by(Attendance.check_in.desc() if Attendance.check_in else Attendance.dibuat.desc())\
            .all()
        
        data = []
        for record in attendance:
            data.append({
                'kode': record.kode,
                'nama': record.nama,
                'check_in': record.check_in.strftime('%H:%M') if record.check_in else '-',
                'check_out': record.check_out.strftime('%H:%M') if record.check_out else '-',
                'status': record.status,
                'shift': record.shift_nama,
                'similarity': f"{record.similarity:.1%}" if record.similarity else '-',
                'liveness_ok': '✅' if record.liveness_ok else '❌'
            })
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/face-cache-stats', methods=['GET'])
@login_required
@owner_required
def get_face_cache_stats():
    """Get face cache statistics"""
    try:
        # Get total cached faces from face_engine
        total_faces = len(face_engine.known_faces) if hasattr(face_engine, 'known_faces') else 0
        
        # Get employees with registered faces from database
        employees_with_face = FaceEncoding.query.count()
        
        # Get total active employees
        total_employees = Employee.query.filter_by(aktif=True).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_cached_faces': total_faces,
                'employees_with_face': employees_with_face,
                'total_employees': total_employees,
                'registration_rate': round((employees_with_face / total_employees * 100), 1) if total_employees > 0 else 0
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ✅ Add this route to app.py
@app.route('/api/clear-face-cache', methods=['POST'])
@login_required
@owner_required
def clear_face_cache():
    """Clear face cache"""
    try:
        # Clear face engine cache
        if hasattr(face_engine, 'clear_cache'):
            face_engine.clear_cache()
            
        return jsonify({
            'success': True,
            'message': 'Cache wajah berhasil dihapus'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/karyawan', methods=['GET'])
@login_required
@owner_required
def get_employees_api():
    """Get all employees for API (dropdown/select)"""
    try:
        employees = Employee.query.filter_by(aktif=True)\
            .order_by(Employee.nama)\
            .all()
        
        data = []
        for emp in employees:
            data.append({
                'id': emp.id,
                'kode': emp.kode,
                'nama': emp.nama,
                'email': emp.email or ''
            })
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== FILE UPLOADS ==========

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve uploaded files"""
    return send_from_directory('static', filename)

# ========== ERROR HANDLERS ==========

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Endpoint tidak ditemukan'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    return render_template('500.html'), 500

# ========== INITIALIZATION ==========

@app.route('/api/init-db')
def init_database():
    """Initialize database with default data (for first time setup)"""
    try:
        # Check if owner user exists
        owner = User.query.filter_by(email='owner@company.com').first()
        
        if not owner:
            # Create default owner user
            owner = User(
                email='owner@company.com',
                password_hash=generate_password_hash('admin123'),
                role='OWNER',
                created_at=datetime.utcnow()
            )
            db.session.add(owner)
            
            # Create default shifts
            shifts = [
                ShiftSetting(
                    nama='PAGI',
                    jam_masuk=time(8, 0),
                    jam_pulang=time(17, 0),
                    toleransi_menit=10,
                    aktif=True,
                    dibuat=datetime.utcnow()
                ),
                ShiftSetting(
                    nama='SIANG',
                    jam_masuk=time(13, 0),
                    jam_pulang=time(22, 0),
                    toleransi_menit=10,
                    aktif=True,
                    dibuat=datetime.utcnow()
                )
            ]
            
            for shift in shifts:
                db.session.add(shift)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Database initialized successfully',
                'owner_email': 'owner@company.com',
                'owner_password': 'admin123'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Database already initialized'
            })
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/debug/config')
def debug_config():
    """Debug endpoint to check current configuration"""
    return jsonify({
        'success': True,
        'config': {
            'gps_enabled': True,
            'company_latitude': app.config.get('COMPANY_LATITUDE'),
            'company_longitude': app.config.get('COMPANY_LONGITUDE'),
            'gps_radius_meters': app.config.get('GPS_RADIUS_METERS'),
            'environment': app.debug and 'development' or 'production',
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    })

# ========== MAIN ==========

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
