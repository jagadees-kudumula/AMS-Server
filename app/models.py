from app import db

class Student(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    department = db.Column(db.String(50), nullable=False, index=True)
    section = db.Column(db.String(10), nullable=False, index=True)
    binding_id = db.Column(db.String(200), unique=True, index=True)


class Faculty(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)


class Subject(db.Model):
    subject_code = db.Column(db.String(10), primary_key=True)
    subject_mnemonic = db.Column(db.String(100), nullable=False)
    subject_name = db.Column(db.String(200), nullable=False)
    subject_type = db.Column(db.String(10), nullable=False)

    assignments = db.relationship('FacultyAssignment', lazy=True)       # This rule means: If a Subject is deleted, delete all related FacultyAssignment rows.



# 🔑 New Table: Faculty teaches what and to whom
class FacultyAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.String(20), db.ForeignKey('faculty.id'), nullable=False, index=True)
    subject_code = db.Column(db.String(10), db.ForeignKey('subject.subject_code', ondelete='CASCADE'), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    department = db.Column(db.String(50), nullable=False, index=True)
    section = db.Column(db.String(10), nullable=False, index=True)

    faculty = db.relationship('Faculty', backref='faculty_assignments')
    subject = db.relationship('Subject', overlaps="assignments")
    default_schedule = db.relationship('DefaultSchedule', backref='assignment_link', lazy=True)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('faculty_assignment.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    status = db.Column(db.Boolean, default=False, index=True)
    venue = db.Column(db.String(50))
    otp=db.Column(db.String(6) ,nullable=True)
    otp_created_at = db.Column(db.DateTime, nullable=True)
    topic_discussed = db.Column(db.String(100))

    assignment = db.relationship('FacultyAssignment', backref='schedules')


class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), db.ForeignKey('student.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False, index=True)
    status = db.Column(db.Boolean, nullable=False)

    student = db.relationship('Student', backref='attendance_record')
    schedule = db.relationship('Schedule', backref='attendance_record')


class DefaultSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('faculty_assignment.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.String(10), nullable=False)  # e.g., 'Monday'
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    venue = db.Column(db.String(25), nullable=False)

class CR(db.Model):
    student_id = db.Column(db.String(20), db.ForeignKey('student.id', ondelete='CASCADE'), primary_key=True)
    mobile = db.Column(db.String(15), nullable=False)

    student = db.relationship('Student', backref='cr_role')


class FCMToken(db.Model):
    __tablename__ = 'fcm_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    student_email = db.Column(db.String(255), nullable=False, index=True)
    fcm_token = db.Column(db.Text, nullable=False)
    device_type = db.Column(db.String(50))  # 'ios' or 'android'
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Unique constraint on email and device_type combination
    __table_args__ = (
        db.UniqueConstraint('student_email', 'device_type', name='unique_email_device'),
    )


class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    cr_email = db.Column(db.String(255), nullable=False, index=True)
    title = db.Column(db.String(255))
    message = db.Column(db.Text, nullable=False)
    recipient_count = db.Column(db.Integer)
    sent_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    status = db.Column(db.String(50))  # 'success', 'failed', 'partial'

