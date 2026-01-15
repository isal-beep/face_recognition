from app import app, db, Attendance, Employee
from datetime import date

with app.app_context():
    today = date.today()
    
    # Cari attendance hari ini
    att_today = Attendance.query.filter_by(tanggal=today).all()
    print(f"Attendance hari ini: {len(att_today)} records")
    
    for att in att_today:
        employee = Employee.query.get(att.employee_id)
        emp_name = employee.nama if employee else f"ID:{att.employee_id}"
        print(f"  - {emp_name}: {att.check_in} to {att.check_out}")
    
    # Hapus jika ingin test ulang
    confirm = input("Hapus semua attendance hari ini? (y/n): ")
    
    if confirm.lower() == 'y':
        for att in att_today:
            db.session.delete(att)
        db.session.commit()
        print(f"✅ {len(att_today)} attendance records dihapus")
    else:
        print("❌ Tidak dihapus")