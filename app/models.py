from app import db

class Student(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    department = db.Column(db.String(50), nullable=False, index=True)
    section = db.Column(db.String(10), nullable=False, index=True)


class Faculty(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)


class Subject(db.Model):
    subject_code = db.Column(db.String(10), primary_key=True)
    subject_mnemonic = db.Column(db.String(100), nullable=False)
    subject_name = db.Column(db.String(200), nullable=False)


# 🔑 New Table: Faculty teaches what and to whom
class FacultyAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.String(20), db.ForeignKey('faculty.id'), nullable=False)
    subject_code = db.Column(db.String(10), db.ForeignKey('subject.subject_code'), nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    department = db.Column(db.String(50), nullable=False, index=True)
    section = db.Column(db.String(10), nullable=False, index=True)

    faculty = db.relationship('Faculty', backref='assignments')
    subject = db.relationship('Subject', backref='assignments')


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('faculty_assignment.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    timing = db.Column(db.Time, nullable=False)
    status = db.Column(db.Boolean, default=False)
    venue = db.Column(db.String(50))

    assignment = db.relationship('FacultyAssignment', backref='schedules')


class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), db.ForeignKey('student.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    status = db.Column(db.Boolean, nullable=False)

    student = db.relationship('Student', backref='attendance_records')
    schedule = db.relationship('Schedule', backref='attendance_records')


class DefaultSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('faculty_assignment.id'), nullable=False)
    day_of_week = db.Column(db.String(10), nullable=False)  # e.g., 'Monday'
    timing = db.Column(db.Time, nullable=False)

    assignment = db.relationship('FacultyAssignment', backref='default_schedules')

class CR(db.Model):
    student_id = db.Column(db.String(20), db.ForeignKey('student.id'), primary_key=True)
    mobile = db.Column(db.String(15), nullable=False)

    student = db.relationship('Student', backref='CR')