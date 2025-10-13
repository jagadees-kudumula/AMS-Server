from flask import Flask, request, jsonify, Blueprint,current_app
from app import db
from app.models import CR, Student, Faculty, FacultyAssignment, Subject, DefaultSchedule, Schedule, AttendanceRecord, FCMToken, NotificationLog
import pandas as pd
import io
import json
from datetime import datetime, date, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
from sqlalchemy import or_,not_, func
from sqlalchemy.orm import joinedload, contains_eager
from threading import Timer
import time

routes = Blueprint('main', __name__)
batchToYear = {'E1':1,'E2':2,'E3':3,'E4':4}
yearToBatch = {1:'E1', 2:'E2', 3:'E3', 4:'E4'}

@routes.route('/students/upload', methods=['POST'])
def upload_students():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    batch = request.form['year']
    year = batchToYear[batch]
    isreplace = request.form['replace']
    department = request.form['department']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        if isreplace == 'true':
            try:
                Student.query.filter_by(year=year, department=department).delete(synchronize_session=False)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return jsonify({'message': str(e)}), 500

        # Read Excel into a DataFrame
        df = pd.read_excel(file)

        # Prepare bulk insert list
        students_to_add = []
        for _, row in df.iterrows():
            students_to_add.append(Student(
                id=row['id'],
                name=row['name'],
                email=row['id'].lower() + "@rguktrkv.ac.in",
                year=year,
                department=department,
                section=row['section']
            ))
        
        # Bulk insert all students
        if students_to_add:
            db.session.bulk_save_objects(students_to_add)
        
        db.session.commit()
        return jsonify({'success':True,'message': f'{len(df)} students added successfully.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': "Students are already int the table."}), 500

@routes.route('/crs', methods=['GET', 'POST'])
def handle_crs():
    if request.method == 'GET':
        # Get all CRs with student details using JOIN to avoid N+1 queries
        try:
            # Use joinedload to eagerly load student data
            crs = CR.query.options(joinedload(CR.student)).all()
            cr_data = []
            
            for cr in crs:
                if cr.student:  # student is already loaded via joinedload
                    cr_data.append({
                        'id': cr.student_id,
                        'name': cr.student.name,
                        'email': cr.student.email,
                        'year': cr.student.year,
                        'branch': cr.student.department,
                        'section': cr.student.section,
                        'phone': cr.mobile  # Include mobile from CR table
                    })
            
            return jsonify({
                'success': True,
                'crs': cr_data,
                'count': len(cr_data)
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

@routes.route('/crs/remove/<string:student_id>', methods=['DELETE'])
def remove_cr(student_id):
    # Find the CR record in the database using the student_id
    cr_to_remove = CR.query.filter_by(student_id=student_id).first()

    # If the CR doesn't exist, return a 404 Not Found error
    if not cr_to_remove:
        return jsonify({'success': False, 'message': 'CR not found.'}), 404

    try:
        # Delete the record from the database session
        db.session.delete(cr_to_remove)
        # Commit the change to the database
        db.session.commit()
        
        # Return a success message
        return jsonify({'success': True, 'message': 'CR removed successfully'}), 200
    except Exception as e:
        # If any database error occurs, roll back the session
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error, could not remove CR.'}), 500

@routes.route('/crs/add', methods=['POST'])
def add_cr():
    data = request.form
    student_id = data['id']
    mobile = data['mobile']

    # Check if the student exists
    student = Student.query.get(student_id)
    if not student:
        return jsonify({'success': False, 'message': 'Student not found.'}), 404

    # Check if the CR already exists
    existing_cr = CR.query.filter_by(student_id=student_id).first()
    
    if existing_cr:
        return jsonify({'success': False, 'message': 'CR already exists.'}), 400

    try:
        # Create a new CR record
        new_cr = CR(student_id=student_id, mobile=mobile)
        db.session.add(new_cr)
        db.session.commit()

        new_cr = {'id': student_id,
                  'name': student.name,
                  'email': student.email,
                  'year': student.year,
                  'branch': student.department,
                  'section': student.section,
                  'phone': mobile}

        return jsonify({'success': True, 'message': 'CR added successfully.', 'newcr' : new_cr}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error, could not add CR.'}), 500

@routes.route('/faculties', methods=['GET'])
def get_faculties():
    try:
        # Use joinedload to eagerly load faculty data, avoiding N+1 queries
        faculty_assignments = FacultyAssignment.query.options(
            joinedload(FacultyAssignment.faculty)
        ).all()
        faculty_list = []

        for fa in faculty_assignments:
            faculty_details = {
                'subject_code': fa.subject_code,
                'year': fa.year,
                'department': fa.department,
                'section': fa.section,
                'assignment_id': fa.id,
                'id': fa.faculty.id,
                'name': fa.faculty.name,
                'email': fa.faculty.email
            }     
        
            faculty_list.append(faculty_details)
    
        return jsonify({'success': True, 'faculties': faculty_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error, could not fetch faculties.'}), 500

@routes.route('/faculties/upload_faculty', methods=['POST'])
def upload_faculty():

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    
    try:
        df = pd.read_excel(file)
        
        # Batch fetch all existing faculties and assignments in one query
        faculty_ids = df['FacultyId'].unique().tolist()
        existing_faculties = {f.id: f for f in Faculty.query.filter(Faculty.id.in_(faculty_ids)).all()}
        
        # Build assignment tuples for checking duplicates
        assignment_keys = []
        for _, row in df.iterrows():
            year = batchToYear[row['Year']]
            assignment_keys.append((
                row['FacultyId'],
                row['SubjectCode'],
                year,
                row['Department'],
                row['Section']
            ))
        
        # Fetch existing assignments in bulk
        existing_assignments_query = db.session.query(
            FacultyAssignment.faculty_id,
            FacultyAssignment.subject_code,
            FacultyAssignment.year,
            FacultyAssignment.department,
            FacultyAssignment.section
        ).filter(
            FacultyAssignment.faculty_id.in_(faculty_ids)
        ).all()
        
        existing_assignments_set = set(existing_assignments_query)
        
        # Prepare bulk insert lists
        faculties_to_add = []
        assignments_to_add = []
        
        for _, row in df.iterrows():
            faculty_id = row['FacultyId']
            faculty_name = row['FacultyName']
            subject_code = row['SubjectCode']
            department = row['Department']
            year = batchToYear[row['Year']]
            section = row['Section']
            
            # Check if faculty needs to be created
            if faculty_id not in existing_faculties:
                email = f"{faculty_id}@rguktrkv.ac.in"
                faculties_to_add.append(Faculty(
                    id=faculty_id,
                    name=faculty_name,
                    email=email
                ))
                existing_faculties[faculty_id] = True  # Mark as added
            
            # Check for duplicate assignment
            assignment_tuple = (faculty_id, subject_code, year, department, section)
            if assignment_tuple in existing_assignments_set:
                return jsonify({'success': False, 'message': 'The assignment already exists'}), 201
            
            # Add to bulk insert list
            assignments_to_add.append(FacultyAssignment(
                faculty_id=faculty_id,
                subject_code=subject_code,
                year=year,
                department=department,
                section=section
            ))
            existing_assignments_set.add(assignment_tuple)
        
        # Bulk insert all faculties and assignments
        if faculties_to_add:
            db.session.bulk_save_objects(faculties_to_add)
        if assignments_to_add:
            db.session.bulk_save_objects(assignments_to_add)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Successfully processed faculty assignments'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error, could not add faculty.'}), 500

@routes.route('/faculties/add', methods=['POST'])
def add_faculty():
    try:
        # Get JSON data directly from request
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        faculty_id = data.get('id')
        name = data.get('name')
        department = data.get('department')
        section = data.get('section')
        year = data.get('year')
        subject_code = data.get('subject_code')

        # Validate required fields
        if not all([faculty_id, name, department, section, year, subject_code]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Convert year using your mapping (same as in your working update)
        year = batchToYear.get(year, year)  # Use your existing batchToYear mapping

        # Check if faculty already exists
        faculty = Faculty.query.get(faculty_id)
        if not faculty:
            # Add new faculty
            faculty = Faculty(
                id=faculty_id, 
                name=name, 
                email=faculty_id.lower() + "@rguktrkv.ac.in"
            )
            db.session.add(faculty)

        # Check if the faculty assignment already exists
        existing_assignment = FacultyAssignment.query.filter_by(
            faculty_id=faculty_id,
            subject_code=subject_code,
            year=year,
            department=department,
            section=section
        ).first()
        
        if existing_assignment:
            return jsonify({'success': False, 'message': 'The assignment already exists'}), 409

        # Add faculty assignment
        faculty_assignment = FacultyAssignment(
            faculty_id=faculty_id,
            subject_code=subject_code,
            year=year,
            department=department,
            section=section
        )

        db.session.add(faculty_assignment)
        db.session.commit()

        # Fetch the newly added faculty assignment details
        new_faculty_assignment = {
            'id': faculty.id,
            'name': faculty.name,
            'email': faculty.email,
            'subject_code': faculty_assignment.subject_code,
            'year': faculty_assignment.year,
            'department': faculty_assignment.department,
            'section': faculty_assignment.section,
            'assignment_id': faculty_assignment.id
        }

        return jsonify({
            'success': True, 
            'message': 'Faculty and assignment added successfully.', 
            'faculty': new_faculty_assignment
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error, could not add faculty.'}), 500

@routes.route('/faculties/remove/<int:assignment_id>', methods=['DELETE'])
def remove_faculty_assignment(assignment_id):
    # Find the FacultyAssignment record in the database using the assignment_id
    assignment_to_remove = FacultyAssignment.query.get(assignment_id)

    # If the assignment doesn't exist, return a 404 Not Found error
    if not assignment_to_remove:
        return jsonify({'success': False, 'message': 'Faculty assignment not found.'}), 404

    try:
        faculty_id = assignment_to_remove.faculty_id
        
        # Delete the assignment
        db.session.delete(assignment_to_remove)
        
        # ✅ OPTIMIZED: Use exists() instead of fetching all assignments
        # Check if faculty has any other assignments (more efficient than .all())
        has_other_assignments = db.session.query(
            db.session.query(FacultyAssignment).filter(
                FacultyAssignment.faculty_id == faculty_id,
                FacultyAssignment.id != assignment_id
            ).exists()
        ).scalar()

        # If no other assignments exist, delete the faculty from the Faculty table
        if not has_other_assignments:
            Faculty.query.filter_by(id=faculty_id).delete(synchronize_session=False)

        # Commit the change to the database
        db.session.commit()
        
        # Return a success message
        return jsonify({'success': True, 'message': 'Faculty assignment removed successfully'}), 200
    except Exception as e:
        # If any database error occurs, roll back the session
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error, could not remove faculty assignment.'}), 500

@routes.route('/faculties/update/<int:assignment_id>', methods=['PUT'])
def update_faculty_assignment(assignment_id):

    data = request.form.get("faculty")
    data = json.loads(data)  # convert string -> dict

    subject_code = data.get('subject_code')
    batch = data.get('year')
    year = batchToYear[batch]
    department = data.get('department')
    section = data.get('section')
    name = data.get('name')

    try:
        faculty = Faculty.query.get(data.get('id'))

        if not faculty:
            return jsonify({'success': False, 'message': 'Faculty not found.'}), 404
        
        if name:
            faculty.name = name

        # Find the FacultyAssignment record in the database using the assignment_id
        assignment_to_update = FacultyAssignment.query.get(assignment_id)

        # If the assignment doesn't exist, return a 404 Not Found error
        if not assignment_to_update:
            return jsonify({'success': False, 'message': 'Faculty assignment not found.'}), 404

        # Update the fields if they are provided in the request
        if subject_code:
            assignment_to_update.subject_code = subject_code
        if year:
            assignment_to_update.year = year
        if department:
            assignment_to_update.department = department
        if section:
            assignment_to_update.section = section

        # Commit the changes to the database
        db.session.commit()

        faculty_assignment_details = {
            'id': faculty.id,
            'name': faculty.name,
            'email': faculty.email,
            'subject_code': assignment_to_update.subject_code,
            'year': assignment_to_update.year,
            'department': assignment_to_update.department,
            'section': assignment_to_update.section,
            'assignment_id': assignment_to_update.id
        }

        # Return a success message
        return jsonify({'success': True, 'message': 'Faculty assignment updated successfully', 'faculty':faculty_assignment_details}), 200
    except Exception as e:
        # If any database error occurs, roll back the session
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Server error, could not update faculty assignment.'}), 500

@routes.route('/subjects/upload', methods=['POST'])
def upload_subjects():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    isreplace = request.form['replace']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        if isreplace == 'true':
            try:
                Subject.query.delete(synchronize_session=False)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return jsonify({'message': str(e)}), 500

        # Read Excel into a DataFrame
        df = pd.read_excel(file)

        # Prepare bulk insert list
        subjects_to_add = []
        for _, row in df.iterrows():
            subjects_to_add.append(Subject(
                subject_code=row['code'],
                subject_mnemonic=row['mnemonic'],
                subject_name=row['name'],
                subject_type=row['type']
            ))
        
        # Bulk insert all subjects
        if subjects_to_add:
            db.session.bulk_save_objects(subjects_to_add)

        db.session.commit()
        return jsonify({'message': f'{len(df)} subjects added successfully.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': "Subjects are already in the table."}), 500


@routes.route('/defacultschedules/upload', methods=['POST'])
def upload_default_schedules():
    
    PERIOD_TIMES = {
        1: ("08:30", "09:30"),
        2: ("09:30", "10:30"),
        3: ("10:30", "11:30"),
        4: ("11:30", "12:30"),
        5: ("13:40", "14:40"),
        6: ("14:40", "15:40"),
        7: ("15:40", "16:40"),
    }

    LAB_DURATION = 3

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    batch = request.form['year']
    year = batchToYear[batch]
    department = request.form['department']
    isreplace = request.form['replace']

    # Handle Replace Flag (Clear existing schedules for this group)
    if isreplace == 'true':
        try:
            # Find all FacultyAssignment IDs matching the year and department
            assignment_ids_to_clear = db.session.query(FacultyAssignment.id).filter(
                FacultyAssignment.year == year,
                FacultyAssignment.department == department
            ).subquery()
            
            # Delete the corresponding DefaultSchedule records using the found IDs
            db.session.query(DefaultSchedule).filter(
                DefaultSchedule.assignment_id.in_(assignment_ids_to_clear.select())
            ).delete(synchronize_session='fetch')
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': f'Failed to clear old schedules: {e}'}), 500

    try:
        df = pd.read_excel(file)

        # Fetch all subject types in one query
        subject_codes = df['SubjectCode'].unique().tolist()
        subject_types_dict = {
            s.subject_code: s.subject_type 
            for s in db.session.query(Subject.subject_code, Subject.subject_type)
                .filter(Subject.subject_code.in_(subject_codes))
                .all()
        }

        # Fetch all relevant faculty assignment IDs in one query
        faculty_ids = df['FacultyId'].unique().tolist()
        sections = df['Section'].unique().tolist()
        
        assignments_query = db.session.query(
            FacultyAssignment.id,
            FacultyAssignment.faculty_id,
            FacultyAssignment.subject_code,
            FacultyAssignment.section
        ).filter(
            FacultyAssignment.department == department,
            FacultyAssignment.year == year,
            FacultyAssignment.faculty_id.in_(faculty_ids),
            FacultyAssignment.section.in_(sections),
            FacultyAssignment.subject_code.in_(subject_codes)
        ).all()
        
        # Create a lookup dictionary for fast assignment_id retrieval
        assignment_lookup = {}
        for assignment in assignments_query:
            key = (assignment.faculty_id, assignment.subject_code, assignment.section)
            assignment_lookup[key] = assignment.id

        # Prepare bulk insert list
        schedules_to_add = []
        
        for _, row in df.iterrows():
            day_of_week = row['Day']
            section = row['Section']
            period = row['Period']
            subject_code = row['SubjectCode']
            faculty_id = row['FacultyId']
            venue = row['Venue']

            # Get subject type from preloaded dictionary
            subject_type = subject_types_dict.get(subject_code)
            if not subject_type:
                raise ValueError(f"Subject code {subject_code} not found")

            # Calculate time based on subject type
            if subject_type.lower() == "lab":
                start_time = PERIOD_TIMES[period][0]
                end_period = period + LAB_DURATION - 1
                if end_period not in PERIOD_TIMES:
                    raise ValueError(f"Lab starting at period {period} exceeds available periods")
                end_time = PERIOD_TIMES[end_period][1]
            else:
                start_time, end_time = PERIOD_TIMES[period]
            
            # Get assignment_id from preloaded lookup
            assignment_key = (faculty_id, subject_code, section)
            assignment_id = assignment_lookup.get(assignment_key)
            
            if not assignment_id:
                raise ValueError(f"No assignment found for faculty {faculty_id}, subject {subject_code}, section {section}")

            schedules_to_add.append(DefaultSchedule(
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                assignment_id=assignment_id,
                venue=venue
            ))

        # Bulk insert all schedules
        if schedules_to_add:
            db.session.bulk_save_objects(schedules_to_add)
        
        db.session.commit()
        return jsonify({'message': 'Default schedules uploaded successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500


# Faculty Schedule Endpoint    
@routes.route('/faculty/<faculty_id>/schedule', methods=['GET'])
def get_faculty_schedule(faculty_id):
    try:
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'success': False, 'error': 'Date parameter is required'}), 400
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get schedules for this faculty on the specific date
        schedules = db.session.query(Schedule, FacultyAssignment, Subject)\
            .join(FacultyAssignment, Schedule.assignment_id == FacultyAssignment.id)\
            .join(Subject, FacultyAssignment.subject_code == Subject.subject_code)\
            .filter(
                FacultyAssignment.faculty_id == faculty_id,
                Schedule.date == target_date
            )\
            .all()
        
        schedule_list = []
        for schedule, assignment, subject in schedules:
            schedule_data = {
                'id': schedule.id,
                'subject_name': subject.subject_name,
                'year': assignment.year,
                'department': assignment.department,
                'section': assignment.section,
                'start_time': schedule.start_time,
                'end_time': schedule.end_time,
                'venue': schedule.venue or '',
                'status': schedule.status,
                'otp': schedule.otp or ''
            }
            schedule_list.append(schedule_data)
        
        # Get faculty info
        faculty = Faculty.query.get(faculty_id)
        
        return jsonify({
            'success': True,
            'faculty_name': faculty.name if faculty else 'Faculty',
            'today_date': target_date.isoformat(),
            'schedules': schedule_list,
            'total_classes': len(schedule_list)
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to fetch schedule'}), 500
    
#Subjects of facultyId   
@routes.route('/faculty/<faculty_id>/subjects', methods=['GET'])
def get_faculty_subjects(faculty_id):
    try:
        # Get all subjects assigned to this faculty
        subjects = db.session.query(Subject)\
            .join(FacultyAssignment, Subject.subject_code == FacultyAssignment.subject_code)\
            .filter(FacultyAssignment.faculty_id == faculty_id)\
            .distinct()\
            .all()
        
        subject_list = []
        for subject in subjects:
            subject_list.append({
                'subject_code': subject.subject_code,
                'subject_name': subject.subject_name,
                'subject_type': subject.subject_type
            })
        
        return jsonify({
            'success': True,
            'subjects': subject_list
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to fetch subjects'}), 500

# Available Time Slots Endpoint
@routes.route('/faculty/<faculty_id>/available-slots', methods=['GET'])
def get_available_slots(faculty_id):
    try:
        date_str = request.args.get('date')
        batch = request.args.get('year')  # This is actually batch (E1, E2, etc.)
        department = request.args.get('department')
        section = request.args.get('section')
        subject_type = request.args.get('subject_type')  # Now subject_type is provided

        if not all([date_str, batch, department, section, subject_type]):
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        year = batchToYear.get(batch)  # Convert batch to year number

        if not year:
            return jsonify({'success': False, 'error': 'Invalid batch format'}), 400

        subject_type = subject_type.lower()

        # Define all possible time slots (skip 12:30 to 13:30)
        all_slots = [
            ('08:30', '09:30'), ('09:30', '10:30'), ('10:30', '11:30'),
            ('11:30', '12:30'), ('13:40', '14:40'), ('14:40', '15:40'),
            ('15:40', '16:40')
        ]

        available_slots = []

        # ✅ OPTIMIZED: Fetch only start_time and end_time, not entire objects
        existing_schedules = db.session.query(
            Schedule.start_time,
            Schedule.end_time
        ).join(FacultyAssignment, Schedule.assignment_id == FacultyAssignment.id)\
        .filter(
            FacultyAssignment.year == year,
            FacultyAssignment.department == department,
            FacultyAssignment.section == section,
            Schedule.date == target_date
        ).all()
        
        if subject_type == "lab":
            # Lab: 3-hour slots (consecutive periods)
            for i in range(len(all_slots) - 2):
                slot_start = all_slots[i][0]
                slot_end = all_slots[i + 2][1]
                # Skip slots that would include 12:30 to 13:30
                if slot_start < '12:30' < slot_end:
                    continue
                conflict = False
                for existing_start, existing_end in existing_schedules:
                    # Check if time slots overlap
                    if not (slot_end <= existing_start or slot_start >= existing_end):
                        conflict = True
                        break
                if not conflict:
                    available_slots.append({
                        'start_time': slot_start,
                        'end_time': slot_end
                    })
        else:
            # Normal: 1-hour slots
            for slot_start, slot_end in all_slots:
                conflict = False
                for existing_start, existing_end in existing_schedules:
                    if not (slot_end <= existing_start or slot_start >= existing_end):
                        conflict = True
                        break
                if not conflict:
                    available_slots.append({
                        'start_time': slot_start,
                        'end_time': slot_end
                    })

        return jsonify({
            'success': True,
            'available_slots': available_slots,
            'total_slots': len(available_slots)
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
# Create Schedule Endpoint
@routes.route('/schedule', methods=['POST'])
def create_schedule():
    try:
        data = request.get_json()
        
        # Handle both batch codes (E1, E2) and actual years (1, 2)
        year_input = data['year']
        if year_input in batchToYear:
            # It's a batch code, convert to year number
            year = batchToYear[year_input]
            batch_display = year_input
        else:
            try:
                # It might already be a year number
                year = int(year_input)
                # Convert back to batch for display
                batch_display = f'E{year}' if 1 <= year <= 4 else year_input
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid year format'}), 400
        
        # Find the faculty assignment
        assignment = FacultyAssignment.query.filter_by(
            faculty_id=data['faculty_id'],
            year=year,  # Use the actual year number
            department=data['department'],
            section=data['section']
        ).first()
        
        if not assignment:
            return jsonify({
                'success': False, 
                'error': f'No faculty assignment found for {batch_display} {data["department"]} - {data["section"]}. Faculty may not be assigned to this class.'
            }), 400
        
        target_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        # ✅ OPTIMIZED: Single query to check for conflicts (combines both faculty and time conflicts)
        conflict = db.session.query(Schedule.id)\
            .join(FacultyAssignment)\
            .filter(
                Schedule.date == target_date,
                FacultyAssignment.faculty_id == data['faculty_id'],
                Schedule.start_time < data['end_time'],
                Schedule.end_time > data['start_time']
            )\
            .first()
        
        if conflict:
            # Get conflict details for error message
            conflict_schedule = db.session.query(
                Schedule.start_time, 
                Schedule.end_time, 
                Schedule.venue
            ).filter(Schedule.id == conflict[0]).first()
            
            return jsonify({
                'success': False, 
                'error': f'Time conflict with {conflict_schedule.start_time}-{conflict_schedule.end_time} at {conflict_schedule.venue}'
            }), 400
        
        # Create new schedule
        new_schedule = Schedule(
            assignment_id=assignment.id,
            date=target_date,
            start_time=data['start_time'],
            end_time=data['end_time'],
            venue=data.get('venue', 'TBA'),
            status=False
        )
        
        db.session.add(new_schedule)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Class scheduled successfully for {batch_display} {data["department"]} - {data["section"]} on {target_date}',
            'schedule_id': new_schedule.id,
            'schedule_details': {
                'date': target_date.isoformat(),
                'time': f'{data["start_time"]} - {data["end_time"]}',
                'venue': data.get('venue', 'TBA')
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    

# Delete Schedule Endpoint
@routes.route('/schedule/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    try:
        schedule = Schedule.query.get(schedule_id)
        if not schedule:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404
        
        db.session.delete(schedule)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Schedule deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@routes.route('/faculty/dashboard/<faculty_id>', methods=['GET'])
def get_faculty_dashboard(faculty_id):
    """
    Get faculty dashboard with statistics for all assigned classes.
    
    This endpoint returns:
    1. Faculty information
    2. List of all assigned subjects/classes
    3. Statistics for each class (ONLY completed sessions where status=True)
    4. Overall aggregated statistics
    
    Key Metrics Explained:
    - completedSessions: Number of classes where status=True (attendance was taken)
    - classAttendanceAvg: Average attendance % for THIS specific class
    - overallAttendanceAvg: Average attendance % across ALL classes taught by faculty
    
    Args:
        faculty_id: Faculty identifier (e.g., 'F001')
    
    Returns:
        JSON with faculty info, classes data, and aggregated statistics
    """
    try:
        # Step 1: Verify faculty exists
        faculty = Faculty.query.get(faculty_id)
        if not faculty:
            return jsonify({
                'success': False,
                'message': 'Faculty not found'
            }), 404

        # Step 2: Get all class assignments with subjects eagerly loaded
        assignments = FacultyAssignment.query.options(
            joinedload(FacultyAssignment.subject)
        ).filter_by(faculty_id=faculty_id).all()
        
        if not assignments:
            return jsonify({
                'success': True,
                'message': 'No classes assigned',
                'faculty': {
                    'id': faculty.id,
                    'name': faculty.name,
                    'email': faculty.email
                },
                'classes': [],
                'stats': {
                    'totalAssignments': 0,
                    'totalCompletedSessions': 0,
                    'overallAttendanceAvg': 0
                }
            })

        # Step 3: Get all assignment IDs for batch querying
        assignment_ids = [a.id for a in assignments]
        
        # Step 4: Batch query all completed schedules for all assignments
        # Use subquery to get attendance stats efficiently
        attendance_stats = db.session.query(
            Schedule.assignment_id,
            Schedule.id.label('schedule_id'),
            Schedule.date,
            Schedule.topic_discussed,
            func.count(AttendanceRecord.id).label('total_students'),
            func.sum(func.cast(AttendanceRecord.status, db.Integer)).label('present_students')
        ).outerjoin(
            AttendanceRecord, Schedule.id == AttendanceRecord.session_id
        ).filter(
            Schedule.assignment_id.in_(assignment_ids),
            Schedule.status == True
        ).group_by(
            Schedule.assignment_id,
            Schedule.id,
            Schedule.date,
            Schedule.topic_discussed
        ).all()
        
        # Organize stats by assignment_id
        assignment_stats_map = {}
        for stat in attendance_stats:
            if stat.assignment_id not in assignment_stats_map:
                assignment_stats_map[stat.assignment_id] = []
            assignment_stats_map[stat.assignment_id].append(stat)

        # Step 5: Process each assignment and calculate statistics
        classes_data = []
        total_completed_sessions_count = 0
        total_attendance_sum = 0
        classes_with_sessions = 0

        for assignment in assignments:
            subject = assignment.subject  # Already loaded via joinedload
            
            # Get stats for this assignment
            assignment_schedule_stats = assignment_stats_map.get(assignment.id, [])
            completed_sessions_count = len(assignment_schedule_stats)
            
            if completed_sessions_count == 0:
                # Still include in response but with zero stats
                class_data = {
                    'assignmentId': assignment.id,
                    'subjectCode': subject.subject_code,
                    'subjectName': subject.subject_name,
                    'subjectMnemonic': subject.subject_mnemonic,
                    'section': assignment.section,
                    'department': assignment.department,
                    'year': assignment.year,
                    'yearBatch': yearToBatch.get(assignment.year, 'Unknown'),
                    'completedSessions': 0,
                    'classAttendanceAvg': 0,
                    'lastClassDate': None,
                    'lastClassTopic': None
                }
                classes_data.append(class_data)
                continue
            
            # Calculate attendance statistics from batch-loaded data
            total_present_students = 0
            total_students_across_sessions = 0
            last_class_date = None
            last_class_topic = None
            
            for stat in assignment_schedule_stats:
                present_count = stat.present_students or 0
                total_count = stat.total_students or 0
                
                total_present_students += present_count
                total_students_across_sessions += total_count
                
                # Track the most recent class
                if not last_class_date or stat.date > last_class_date:
                    last_class_date = stat.date
                    last_class_topic = stat.topic_discussed
            
            # Calculate attendance percentage for this class
            if total_students_across_sessions > 0:
                class_attendance_avg = round(
                    (total_present_students / total_students_across_sessions) * 100, 
                    2
                )
            else:
                class_attendance_avg = 0
            
            # Add to totals for overall calculation
            if completed_sessions_count > 0:
                total_attendance_sum += class_attendance_avg
                classes_with_sessions += 1
            
            total_completed_sessions_count += completed_sessions_count
            
            # Prepare class data
            class_data = {
                'assignmentId': assignment.id,
                'subjectCode': subject.subject_code,
                'subjectName': subject.subject_name,
                'subjectMnemonic': subject.subject_mnemonic,
                'section': assignment.section,
                'department': assignment.department,
                'year': assignment.year,
                'yearBatch': yearToBatch.get(assignment.year, 'Unknown'),
                'completedSessions': completed_sessions_count,
                'classAttendanceAvg': class_attendance_avg,
                'lastClassDate': last_class_date.strftime('%Y-%m-%d') if last_class_date else None,
                'lastClassTopic': last_class_topic
            }
            
            classes_data.append(class_data)
        
        # Step 6: Calculate overall statistics
        overall_attendance_avg = round(
            total_attendance_sum / classes_with_sessions, 
            2
        ) if classes_with_sessions > 0 else 0
        
        # Step 7: Prepare response
        response_data = {
            'success': True,
            'faculty': {
                'id': faculty.id,
                'name': faculty.name,
                'email': faculty.email
            },
            'classes': classes_data,
            'stats': {
                'totalAssignments': len(assignments),
                'totalCompletedSessions': total_completed_sessions_count,
                'overallAttendanceAvg': overall_attendance_avg
            }
        }

        return jsonify(response_data), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e)
        }), 500
    
@routes.route('/faculty/class-attendance/<int:assignment_id>', methods=['GET'])
def get_class_attendance(assignment_id):
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 10, type=int)  # 10 sessions per request
        include_students = request.args.get('include_students', 'false').lower() == 'true'
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Get total count
        total_sessions = Schedule.query.filter_by(assignment_id=assignment_id, status=True).count()
        
        # Single optimized query with joins
        sessions = db.session.query(
            Schedule,
            db.func.count(AttendanceRecord.id).filter(AttendanceRecord.status == True).label('present_count'),
            db.func.count(AttendanceRecord.id).label('total_records')
        ).outerjoin(
            AttendanceRecord, Schedule.id == AttendanceRecord.session_id
        ).filter(
            Schedule.assignment_id == assignment_id,
            Schedule.status == True  # Only completed sessions
        ).group_by(
            Schedule.id
        ).order_by(
            Schedule.date.desc()
        ).offset(offset).limit(limit).all()
        
        attendance_data = {}
        
        for schedule, present_count, total_records in sessions:
            date_str = schedule.date.strftime('%d/%m/%Y')
            
            # Only fetch student details if explicitly requested
            students = []
            if include_students:
                student_records = db.session.query(
                    Student.id, Student.name, AttendanceRecord.status
                ).join(
                    AttendanceRecord, Student.id == AttendanceRecord.student_id
                ).filter(
                    AttendanceRecord.session_id == schedule.id
                ).all()
                
                students = [{
                    'student_id': student_id,
                    'student_name': student_name,
                    'status': status
                } for student_id, student_name, status in student_records]
            
            session_data = {
                'session_id': schedule.id,
                'date': date_str,
                'start_time': schedule.start_time,
                'end_time': schedule.end_time,
                'topic': schedule.topic_discussed or '',
                'venue': schedule.venue or '',
                'status': schedule.status,
                'present_count': present_count or 0,
                'absent_count': (total_records or 0) - (present_count or 0),
                'total_students': total_records or 0,
                'students': students  # Empty array if not requested
            }
            
            if date_str not in attendance_data:
                attendance_data[date_str] = []
            
            attendance_data[date_str].append(session_data)
        
        return jsonify({
            'success': True,
            'attendanceData': attendance_data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_sessions': total_sessions,
                'has_more': (offset + limit) < total_sessions
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

@routes.route('/attendance/session/<int:session_id>/students', methods=['GET'])
def get_session_students(session_id):
    try:
        students = db.session.query(
            Student.id, Student.name, AttendanceRecord.status
        ).join(
            AttendanceRecord, Student.id == AttendanceRecord.student_id
        ).filter(
            AttendanceRecord.session_id == session_id
        ).all()
        
        student_data = [{
            'student_id': student_id,
            'student_name': student_name,
            'status': status
        } for student_id, student_name, status in students]
        
        return jsonify({
            'success': True,
            'students': student_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

@routes.route('/faculty/update-attendance', methods=['POST'])
def update_attendance():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        student_id = data.get('student_id')
        status = data.get('status')
        
        # Find the attendance record
        attendance_record = AttendanceRecord.query.filter_by(
            session_id=session_id, 
            student_id=student_id
        ).first()
        
        if attendance_record:
            attendance_record.status = status
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Attendance updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Attendance record not found'
            }), 404
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

@routes.route('/faculty/attendance-report/<int:assignment_id>', methods=['GET'])
def get_attendance_report(assignment_id):
    try:
        # Get total sessions count
        total_sessions = Schedule.query.filter_by(assignment_id=assignment_id).count()
        
        if total_sessions == 0:
            return jsonify({
                'success': True,
                'reportData': {
                    'class_summary': {
                        'total_sessions': 0,
                        'total_present': 0,
                        'total_absent': 0,
                        'overall_percentage': 0,
                        'trend': 'stable',
                        'avg_students_present': 0,
                        'avg_students_absent': 0
                    },
                    'students': []
                }
            })

        # Get all sessions for this assignment
        sessions = Schedule.query.filter_by(assignment_id=assignment_id).all()
        session_ids = [session.id for session in sessions]

        # Calculate average students present and absent per session
        attendance_by_session = db.session.query(
            Schedule.id,
            db.func.count(db.case((AttendanceRecord.status == True, 1))).label('present_count'),
            db.func.count(db.case((AttendanceRecord.status == False, 1))).label('absent_count')
        ).outerjoin(
            AttendanceRecord, Schedule.id == AttendanceRecord.session_id
        ).filter(
            Schedule.id.in_(session_ids)
        ).group_by(
            Schedule.id
        ).all()

        total_present_all_sessions = 0
        total_absent_all_sessions = 0
        valid_sessions_count = 0

        for session in attendance_by_session:
            total_present_all_sessions += session.present_count or 0
            total_absent_all_sessions += session.absent_count or 0
            valid_sessions_count += 1

        # Calculate averages
        avg_students_present = round(total_present_all_sessions / valid_sessions_count, 2) if valid_sessions_count > 0 else 0
        avg_students_absent = round(total_absent_all_sessions / valid_sessions_count, 2) if valid_sessions_count > 0 else 0

        # Calculate overall statistics (total counts across all sessions)
        total_present = db.session.query(db.func.count(AttendanceRecord.id))\
            .join(Schedule)\
            .filter(
                Schedule.assignment_id == assignment_id,
                AttendanceRecord.status == True
            ).scalar() or 0

        total_absent = db.session.query(db.func.count(AttendanceRecord.id))\
            .join(Schedule)\
            .filter(
                Schedule.assignment_id == assignment_id,
                AttendanceRecord.status == False
            ).scalar() or 0

        overall_percentage = round((total_present / (total_present + total_absent)) * 100, 2) if (total_present + total_absent) > 0 else 0

        # Get student-wise attendance
        students_attendance = db.session.query(
            Student.id,
            Student.name,
            db.func.sum(db.case((AttendanceRecord.status == True, 1), else_=0)).label('present_count'),
            db.func.sum(db.case((AttendanceRecord.status == False, 1), else_=0)).label('absent_count')
        ).join(
            AttendanceRecord, Student.id == AttendanceRecord.student_id
        ).join(
            Schedule, AttendanceRecord.session_id == Schedule.id
        ).filter(
            Schedule.assignment_id == assignment_id
        ).group_by(
            Student.id, Student.name
        ).all()

        students = []
        for student_id, student_name, present_count, absent_count in students_attendance:
            total_student_sessions = present_count + absent_count
            attendance_percentage = round((present_count / total_student_sessions) * 100, 2) if total_student_sessions > 0 else 0
            
            students.append({
                'student_id': student_id,
                'student_name': student_name,
                'present_count': present_count,
                'absent_count': absent_count,
                'total_sessions': total_student_sessions,
                'attendance_percentage': attendance_percentage
            })

        # Determine trend (simplified - you can implement more sophisticated logic)
        trend = 'stable'
        if overall_percentage > 75:
            trend = 'improving'
        elif overall_percentage < 60:
            trend = 'declining'

        report_data = {
            'class_summary': {
                'total_sessions': total_sessions,
                'total_present': total_present,
                'total_absent': total_absent,
                'overall_percentage': overall_percentage,
                'trend': trend,
                'avg_students_present': avg_students_present,
                'avg_students_absent': avg_students_absent
            },
            'students': students
        }

        return jsonify({
            'success': True,
            'reportData': report_data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

#Automation of Moving Schedules Daily at 00:58
scheduler = None

def start_daily_scheduler(app):
    
    global scheduler
    
    # Create scheduler
    scheduler = BackgroundScheduler(daemon=True)
    
    # Add the job to run daily at 00:58
    scheduler.add_job(
        func=move_tomorrow_schedules_auto,
        args=[app],
        trigger=CronTrigger(hour=00, minute=58),
        id='daily_schedule_move',
        name='Move tomorrow schedules daily at 12:58 AM'
    )

    start_cleanup_scheduler(app)

   
    # Start the scheduler
    scheduler.start()

    
    # Proper shutdown when app stops
    atexit.register(lambda: scheduler.shutdown())
    
    return scheduler

def move_tomorrow_schedules_auto(app):
    """
    Automated version that moves TOMORROW's schedules
    This runs automatically every day at 17:58
    """
    with app.app_context():
        try:
            # Use TOMORROW's date instead of today
            target_date = date.today() + timedelta(days=1)
            day_name = target_date.strftime('%a').upper()
            
            # ✅ OPTIMIZED: Get all default schedules for that day
            default_schedules = DefaultSchedule.query\
                .filter_by(day_of_week=day_name)\
                .all()
            
            if not default_schedules:
                return
            
            # ✅ OPTIMIZED: Get all existing schedule assignment_ids for target date in one query
            existing_assignment_ids = set(
                db.session.query(Schedule.assignment_id)
                .filter(Schedule.date == target_date)
                .all()
            )
            existing_assignment_ids = {aid[0] for aid in existing_assignment_ids}
            
            # ✅ OPTIMIZED: Prepare bulk insert (only for non-existing schedules)
            schedules_to_add = []
            for default_schedule in default_schedules:
                # Skip if already exists
                if default_schedule.assignment_id in existing_assignment_ids:
                    continue
                
                schedules_to_add.append({
                    'assignment_id': default_schedule.assignment_id,
                    'date': target_date,
                    'start_time': default_schedule.start_time,
                    'end_time': default_schedule.end_time,
                    'venue': default_schedule.venue,
                    'status': False
                })
            
            # ✅ OPTIMIZED: Bulk insert all schedules at once
            if schedules_to_add:
                db.session.bulk_insert_mappings(Schedule, schedules_to_add)
                db.session.commit()
            
        except Exception as e:
            db.session.rollback()

@routes.route('/time', methods=['GET'])
def get_server_time():
    try:
        now = datetime.now()
        current_time = now.strftime('%H:%M:%S')
        current_date = now.strftime('%Y-%m-%d')
        # Optionally, include timezone info if needed
        return jsonify({
            'success': True,
            'datetime': f"{current_date}T{current_time}",
            'date': current_date,
            'time': current_time,
            'timezone': 'Asia/Kolkata'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to fetch server time'}), 500
    

@routes.route('/generate-otp', methods=['POST'])
def generate_otp():
    data = request.get_json()
    schedule_id = data.get('schedule_id')
    faculty_id = data.get('faculty_id')
    otp = data.get('otp')
    topic_discussed = data.get('topic_discussed') 

    if not all([schedule_id, faculty_id, otp]):
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    # topic_discussed is now required
    if not topic_discussed or not topic_discussed.strip():
        return jsonify({'success': False, 'message': 'Attendance topic_discussed is required'}), 400

    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({'success': False, 'message': 'Schedule not found'}), 404

    # Get the assignment to check authorization and get class info
    assignment = FacultyAssignment.query.get(schedule.assignment_id)
    if not assignment or assignment.faculty_id != faculty_id:
        return jsonify({'success': False, 'message': 'Faculty not authorized for this schedule'}), 403

    # Store OTP (without timestamp yet), topic_discussed, and mark attendance as completed
    schedule.otp = otp
    schedule.status = True
    schedule.topic_discussed = topic_discussed.strip()
    
    # Create attendance records for all students in that year, department, and section
    try:
        # ✅ OPTIMIZED: Get only student IDs (faster than loading full objects)
        student_ids = db.session.query(Student.id).filter_by(
            year=assignment.year,
            department=assignment.department,
            section=assignment.section
        ).all()
        
        # Extract IDs from tuples
        student_ids = [sid[0] for sid in student_ids]
        
        # ✅ OPTIMIZED: Check existing records in a single query
        existing_student_ids = set(
            db.session.query(AttendanceRecord.student_id)
            .filter(
                AttendanceRecord.session_id == schedule_id,
                AttendanceRecord.student_id.in_(student_ids)
            )
            .all()
        )
        existing_student_ids = {sid[0] for sid in existing_student_ids}
        
        # ✅ OPTIMIZED: Prepare bulk insert data (only for new records)
        new_attendance_records = [
            {
                'student_id': student_id,
                'session_id': schedule_id,
                'status': False  # Default to absent, will be updated when they submit OTP
            }
            for student_id in student_ids
            if student_id not in existing_student_ids
        ]
        
        # ✅ OPTIMIZED: Bulk insert (100x faster than individual inserts)
        if new_attendance_records:
            db.session.bulk_insert_mappings(AttendanceRecord, new_attendance_records)
        
        db.session.commit()
        
        # ⏰ CRITICAL: Set OTP timestamp AFTER all database operations are complete
        # This ensures the 45-second countdown starts from when data is ready, not when OTP generation started
        schedule.otp_created_at = datetime.now(timezone.utc)
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error creating attendance records: {str(e)}'}), 500

    # Schedule OTP removal after 45 seconds
    run_date = datetime.now() + timedelta(seconds=45)
    scheduler.add_job(
        func=remove_otp_job,
        trigger='date',
        run_date=run_date,
        args=[schedule_id],
        id=f'remove_otp_{schedule_id}',
        name=f'Remove OTP for schedule {schedule_id}'
    )

    return jsonify({
        'success': True, 
        'otp': otp, 
        'schedule_id': schedule_id,
        'topic_discussed': topic_discussed.strip(),
        'attendance_records_created': len(new_attendance_records) if new_attendance_records else 0,
        'total_students': len(student_ids)
    }), 200

def remove_otp_job(schedule_id):
    """Background job to remove OTP after 45 seconds"""
    try:
        # Import inside function to avoid circular imports
        from app import create_app,db
        from app.models import Schedule
        
        # Create app instance and context
        app = create_app()
        
        with app.app_context():
            schedule = Schedule.query.get(schedule_id)
            if schedule:
                schedule.otp = ""
                schedule.otp_created_at = None  # Clear timestamp when OTP is removed
                db.session.commit()
                
    except Exception as e:
        pass

@routes.route('/api/student/schedule', methods=['GET'])
def get_student_schedule():
    """Get today's and tomorrow's schedule for a student (only actual schedules)"""
    try:
        # Get student email from query parameters
        student_email = request.args.get('email')
        if not student_email:
            return jsonify({'error': 'Student email is required'}), 400

        # Find student details
        student = Student.query.filter_by(email=student_email).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        today = date.today()
        tomorrow = today + timedelta(days=1)

        # ✅ OPTIMIZED: Query for actual schedules with all needed data
        schedules = db.session.query(
            Schedule.id,
            Schedule.date,
            Schedule.start_time,
            Schedule.end_time,
            Schedule.venue,
            Schedule.status,
            Schedule.otp,
            Schedule.otp_created_at,
            Subject.subject_name,
            Subject.subject_code,
            Subject.subject_mnemonic,
            Subject.subject_type,
            Faculty.name.label('faculty_name')
        ).join(FacultyAssignment, Schedule.assignment_id == FacultyAssignment.id)\
         .join(Subject, FacultyAssignment.subject_code == Subject.subject_code)\
         .join(Faculty, FacultyAssignment.faculty_id == Faculty.id)\
         .filter(
            FacultyAssignment.year == student.year,
            FacultyAssignment.department == student.department,
            FacultyAssignment.section == student.section,
            or_(Schedule.date == today, Schedule.date == tomorrow)
        ).all()
        
        # ✅ OPTIMIZED: Bulk query for all attendance records (single query)
        schedule_ids = [s.id for s in schedules]
        attendance_records = {}
        
        if schedule_ids:
            records = db.session.query(
                AttendanceRecord.session_id,
                AttendanceRecord.status
            ).filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.session_id.in_(schedule_ids)
            ).all()
            
            # Create lookup dictionary for O(1) access
            attendance_records = {r.session_id: r.status for r in records}

        # ✅ OPTIMIZED: Build response (no queries in loop!)
        schedule_data = []
        for s in schedules:
            # Lookup attendance from dictionary (no query!)
            attendance_marked = s.id in attendance_records
            attendance_status = attendance_records.get(s.id)

            schedule_data.append({
                'id': str(s.id),
                'subject': s.subject_name,  # ✅ From join, not extra query
                'subject_code': s.subject_code,
                'subject_mnemonic': s.subject_mnemonic,
                'subject_type': s.subject_type,
                'time': f"{format_time_12hr(s.start_time)} - {format_time_12hr(s.end_time)}",
                'location': s.venue,
                'date': s.date.isoformat(),
                'faculty_name': s.faculty_name,
                'status': s.status,
                'otp': s.otp,
                'otp_created_at': s.otp_created_at.isoformat() + 'Z' if s.otp_created_at else None,
                'attendance_marked': attendance_marked,
                'attendance_status': attendance_status,
                'start_time': s.start_time,  # Raw format: "08:30"
                'end_time': s.end_time,      # Raw format: "09:30"
            })

        # Separate today and tomorrow schedules
        today_schedule = [s for s in schedule_data if s['date'] == today.isoformat()]
        tomorrow_schedule = [s for s in schedule_data if s['date'] == tomorrow.isoformat()]

        return jsonify({
            'today_schedule': today_schedule,
            'tomorrow_schedule': tomorrow_schedule,
            'student_info': {
                'name': student.name,
                'year': student.year,
                'department': student.department,
                'section': student.section
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@routes.route('/api/student/check-cr', methods=['GET'])
def check_student_cr():
    """Check if a student is a Class Representative"""
    try:
        student_email = request.args.get('email')
        if not student_email:
            return jsonify({'error': 'Student email is required'}), 400

        # Find student details
        student = Student.query.filter_by(email=student_email).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        # Check if student is a CR
        cr_record = CR.query.filter_by(student_id=student.id).first()
        
        return jsonify({
            'is_cr': cr_record is not None,
            'student_id': student.id,
            'mobile': cr_record.mobile if cr_record else None
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@routes.route('/api/student/cr-info', methods=['GET'])
def get_cr_info():
    """Get CR's student details (year, department, section)"""
    try:
        student_email = request.args.get('email')
        if not student_email:
            return jsonify({'error': 'Student email is required'}), 400

        # Find student details
        student = Student.query.filter_by(email=student_email).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        return jsonify({
            'year': student.year,
            'department': student.department,
            'section': student.section,
            'name': student.name
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes.route('/api/cr/subjects', methods=['GET'])
def get_cr_subjects():
    """Get subjects for CR's class (year, department, section)"""
    try:
        student_email = request.args.get('email')
        if not student_email:
            return jsonify({'error': 'Student email is required'}), 400

        # Find student details
        student = Student.query.filter_by(email=student_email).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        # Check if student is CR
        cr_record = CR.query.filter_by(student_id=student.id).first()
        if not cr_record:
            return jsonify({'error': 'Only CR can access this endpoint'}), 403

        # Get subjects assigned to this class with eager loading of related data
        assignments = FacultyAssignment.query.options(
            joinedload(FacultyAssignment.subject),
            joinedload(FacultyAssignment.faculty)
        ).filter_by(
            year=student.year,
            department=student.department,
            section=student.section
        ).all()

        subject_list = []
        for assignment in assignments:
            subject_list.append({
                'subject_code': assignment.subject.subject_code,
                'subject_name': assignment.subject.subject_name,
                'subject_type': assignment.subject.subject_type,
                'faculty_name': assignment.faculty.name,
                'faculty_id': assignment.faculty_id,
                'assignment_id': assignment.id
            })
        
        return jsonify(subject_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes.route('/api/cr/schedule-class', methods=['POST'])
def schedule_class():
    """Schedule a new class by CR with comprehensive conflict checking"""
    try:
        data = request.get_json()
        
        # Required fields
        required_fields = ['subject_code', 'date', 'start_time', 'end_time', 'venue', 'student_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400

        # Get CR's student details
        student = Student.query.filter_by(email=data['student_email']).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        # Check if student is CR
        cr_record = CR.query.filter_by(student_id=student.id).first()
        if not cr_record:
            return jsonify({'error': 'Only CR can schedule classes'}), 403

        # ✅ OPTIMIZED: Load assignment with eager loading of subject and faculty
        assignment = FacultyAssignment.query.options(
            joinedload(FacultyAssignment.subject),
            joinedload(FacultyAssignment.faculty)
        ).filter_by(
            subject_code=data['subject_code'],
            year=student.year,
            department=student.department,
            section=student.section
        ).first()

        if not assignment:
            return jsonify({'error': 'No faculty assigned for this subject and class'}), 400

        # Parse date
        class_date = datetime.strptime(data['date'], '%Y-%m-%d').date()

        # Pre-validation checks (fast, no DB queries needed)
        # Check 1: Validate date is not in the past
        if class_date < date.today():
            return jsonify({'error': 'Cannot schedule classes in the past'}), 400

        # Check 2: Validate that the time slot doesn't cross lunch break
        if data['start_time'] < '12:30' and data['end_time'] > '13:40':
            return jsonify({'error': 'Class cannot span across lunch break (12:30-13:40)'}), 400

        # Check 3: Validate time slot (should be one of the predefined slots)
        valid_time_slots = [
            ('08:30', '09:30'), ('09:30', '10:30'), ('10:30', '11:30'), ('11:30', '12:30'),
            ('13:40', '14:40'), ('14:40', '15:40'), ('15:40', '16:40'),
            ('08:30', '11:30'), ('09:30', '12:30'), ('13:40', '16:40')  # Lab slots
        ]
        
        time_valid = any(
            data['start_time'] == start and data['end_time'] == end 
            for start, end in valid_time_slots
        )
        
        if not time_valid:
            return jsonify({'error': 'Invalid time slot selected'}), 400

        # Check 4: Validate duration based on subject type
        subject = assignment.subject  # Already loaded via joinedload
        start_dt = datetime.strptime(data['start_time'], '%H:%M')
        end_dt = datetime.strptime(data['end_time'], '%H:%M')
        duration = (end_dt - start_dt).total_seconds() / 3600  # Convert to hours
        
        if subject.subject_type.lower() == 'lab':
            if duration != 3:
                return jsonify({'error': 'Lab classes must be exactly 3 hours long'}), 400
        else:
            if duration != 1:
                return jsonify({'error': 'Regular classes must be exactly 1 hour long'}), 400

        # ✅ OPTIMIZED: Combined conflict checking with single query
        # Check both class time conflict AND faculty conflict in one query
        conflicts = db.session.query(
            Schedule.id,
            Schedule.start_time,
            Schedule.end_time,
            FacultyAssignment.year,
            FacultyAssignment.department,
            FacultyAssignment.section,
            FacultyAssignment.faculty_id,
            Subject.subject_name,
            Faculty.name.label('faculty_name')
        ).join(FacultyAssignment, Schedule.assignment_id == FacultyAssignment.id)\
        .join(Subject, FacultyAssignment.subject_code == Subject.subject_code)\
        .join(Faculty, FacultyAssignment.faculty_id == Faculty.id)\
        .filter(
            Schedule.date == class_date,
            Schedule.start_time < data['end_time'],
            Schedule.end_time > data['start_time'],
            db.or_(
                # Class conflict: same year, dept, section
                db.and_(
                    FacultyAssignment.year == student.year,
                    FacultyAssignment.department == student.department,
                    FacultyAssignment.section == student.section
                ),
                # Faculty conflict: same faculty
                FacultyAssignment.faculty_id == assignment.faculty_id
            )
        ).first()

        if conflicts:
            # Determine type of conflict
            is_class_conflict = (
                conflicts.year == student.year and
                conflicts.department == student.department and
                conflicts.section == student.section
            )
            
            if is_class_conflict:
                return jsonify({
                    'error': f'Time conflict: {conflicts.subject_name} ({conflicts.faculty_name}) is already scheduled for {conflicts.start_time}-{conflicts.end_time}'
                }), 400
            else:
                # Faculty conflict
                conflict_class = f"E{conflicts.year} {conflicts.department}-{conflicts.section}"
                return jsonify({
                    'error': f'Faculty conflict: {assignment.faculty.name} is already teaching {conflicts.subject_name} for {conflict_class} at {conflicts.start_time}-{conflicts.end_time}'
                }), 400

        # Create new schedule
        new_schedule = Schedule(
            assignment_id=assignment.id,
            date=class_date,
            start_time=data['start_time'],
            end_time=data['end_time'],
            venue=data['venue'],
            status=False
        )

        db.session.add(new_schedule)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Class scheduled successfully',
            'schedule_id': new_schedule.id,
            'schedule': {
                'id': new_schedule.id,
                'subject': subject.subject_name,  # From eager loaded data
                'date': class_date.isoformat(),
                'time': f"{data['start_time']} - {data['end_time']}",
                'venue': data['venue'],
                'faculty': assignment.faculty.name  # From eager loaded data
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes.route('/update-venue', methods=['POST'])
def update_venue():
    try:
        # Get data from request
        data = request.get_json()
        schedule_id = data.get('schedule_id')
        venue = data.get('venue')
        
        if not schedule_id or not venue:
            return jsonify({'success': False, 'error': 'Schedule ID and venue are required'}), 400
        
        # Find the schedule
        schedule = Schedule.query.get(schedule_id)
        
        if not schedule:
            return jsonify({'success': False, 'error': 'Schedule not found'}), 404
        
        # Update venue
        old_venue = schedule.venue
        schedule.venue = venue
        
        # Commit changes to database
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Venue updated successfully',
            'updated_schedule': {
                'id': schedule.id,
                'venue': schedule.venue
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@routes.route('/api/attendance/verify-otp', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        schedule_id = data.get('scheduleId')
        otp = data.get('otp')

        # Validate input
        if not schedule_id or not otp:
            return jsonify({
                'success': False,
                'message': 'Schedule ID and OTP are required'
            }), 400

        # Find the schedule with the provided ID
        schedule = Schedule.query.get(schedule_id)
        
        if not schedule:
            return jsonify({
                'success': False,
                'message': 'Schedule not found'
            }), 404

        # Check if OTP matches
        if schedule.otp != otp:
            return jsonify({
                'success': False,
                'message': 'Invalid OTP'
            }), 400

        # OTP is valid
        return jsonify({
            'success': True,
            'message': 'OTP verified successfully'
        })

    except Exception as error:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500
    

@routes.route('/api/attendance/mark', methods=['POST'])
def mark_attendance():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email')
        session_id = data.get('session_id')
        
        if not email or not session_id:
            return jsonify({'error': 'Email and session_id are required'}), 400
        
        # Extract student ID from email
        student_id = email.split('@')[0].upper()
        
        # Check if attendance record exists
        attendance_record = AttendanceRecord.query.filter_by(
            student_id=student_id, 
            session_id=session_id
        ).first()
        
        if not attendance_record:
            return jsonify({'error': 'Attendance record not found for this session'}), 404
        
        # Check if already marked present
        if attendance_record.status:
            return jsonify({
                'error': 'Attendance already marked for this session',
                'already_marked': True
            }), 409
        
        # Update from False to True
        attendance_record.status = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Attendance marked successfully',
            'student_id': student_id,
            'session_id': session_id,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to mark attendance: {str(e)}'}), 500


@routes.route('/student/attendance/<student_id>', methods=['GET'])
def get_student_attendance(student_id):
    try:
        # Get student's class info
        student = db.session.query(Student).filter(Student.id == student_id).first()
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404

        # Single optimized query - no redundant filters needed
        subject_attendance_data = db.session.query(
            Subject.subject_code,
            Subject.subject_name,
            # Count distinct sessions from attendance records
            db.func.count(db.distinct(AttendanceRecord.session_id)).label('total_classes'),
            # Count present records
            db.func.sum(
                db.case(
                    (AttendanceRecord.status == True, 1),
                    else_=0
                )
            ).label('attended_classes')
        ).join(FacultyAssignment, Subject.subject_code == FacultyAssignment.subject_code)\
        .join(Schedule, FacultyAssignment.id == Schedule.assignment_id)\
        .join(AttendanceRecord,
            db.and_(
                Schedule.id == AttendanceRecord.session_id,
                AttendanceRecord.student_id == student_id
            )
        )\
        .filter(
            FacultyAssignment.year == student.year,
            FacultyAssignment.department == student.department,
            FacultyAssignment.section == student.section
        )\
        .group_by(Subject.subject_code, Subject.subject_name)\
        .all()

        # Get all subjects for the student's class
        all_subjects = db.session.query(
            Subject.subject_code,
            Subject.subject_name
        ).join(FacultyAssignment, Subject.subject_code == FacultyAssignment.subject_code)\
        .filter(
            FacultyAssignment.year == student.year,
            FacultyAssignment.department == student.department,
            FacultyAssignment.section == student.section
        ).all()

        # Build final result
        attendance_dict = {
            subject_code: {
                'subject': subject_name,
                'total': total_classes,
                'attended': attended_classes or 0
            }
            for subject_code, subject_name, total_classes, attended_classes in subject_attendance_data
        }

        total_all_classes = 0
        total_attended_classes = 0
        subject_attendance = []

        for subject_code, subject_name in all_subjects:
            if subject_code in attendance_dict:
                data = attendance_dict[subject_code]
                subject_attendance.append(data)
                total_all_classes += data['total']
                total_attended_classes += data['attended']
            else:
                subject_attendance.append({
                    'subject': subject_name,
                    'total': 0,
                    'attended': 0
                })

        overall_percentage = round((total_attended_classes / total_all_classes) * 100, 2) if total_all_classes > 0 else 0

        return jsonify({
            'success': True,
            'subjects': subject_attendance,
            'overall': overall_percentage
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to fetch attendance'}), 500

@routes.route('/student/profile/<student_id>', methods=['GET'])
def get_student_profile(student_id):
    """Get student profile information (year, department, section)"""
    try:
        # Find student by ID
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        return jsonify({
            'success': True,
            'id': student.id,
            'name': student.name,
            'email': student.email,
            'year': yearToBatch[student.year],
            'department': student.department,
            'section': student.section
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to fetch student profile'
        }), 500

@routes.route('/student/history/<student_id>', methods=['GET'])
def get_student_history(student_id):
    try:
        # Get date from query parameter
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'success': False, 'error': 'Date parameter is required'}), 400
        
        # Parse the date
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Check if student exists
        student = db.session.query(Student).filter(Student.id == student_id).first()
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # First, get all attendance records for this student on the given date
        # by joining with Schedule to filter by date
        attendance_records = db.session.query(
            AttendanceRecord.session_id,
            AttendanceRecord.status
        ).join(Schedule, AttendanceRecord.session_id == Schedule.id)\
        .filter(
            AttendanceRecord.student_id == student_id,
            Schedule.date == target_date
        ).all()
        
        # If no attendance records found for this date, return empty history
        if not attendance_records:
            return jsonify({
                'success': True,
                'history': []
            }), 200
        
        # Extract session IDs
        session_ids = [record.session_id for record in attendance_records]
        
        # Create a mapping of session_id to status for quick lookup
        status_map = {record.session_id: record.status for record in attendance_records}
        
        # Now fetch the schedule and subject details for these session IDs
        attendance_history = db.session.query(
            Subject.subject_code,
            Subject.subject_name,
            Schedule.id.label('session_id'),
            Schedule.start_time,
            Schedule.end_time,
            Schedule.venue,
            Schedule.topic_discussed,
            Faculty.name.label('faculty_name')
        ).join(FacultyAssignment, Subject.subject_code == FacultyAssignment.subject_code)\
        .join(Faculty, FacultyAssignment.faculty_id == Faculty.id)\
        .join(Schedule, FacultyAssignment.id == Schedule.assignment_id)\
        .filter(Schedule.id.in_(session_ids))\
        .order_by(Schedule.start_time)\
        .all()
        
        # Format the response
        history = []
        for record in attendance_history:
            # Combine start and end times into single formatted string
            start_formatted = format_time_12hr(record.start_time)
            end_formatted = format_time_12hr(record.end_time)
            time_range = f"{start_formatted} - {end_formatted}"
            
            history.append({
                'subjectCode': record.subject_code,
                'subject': record.subject_name,
                'time': time_range,
                'venue': record.venue,
                'topicDiscussed': record.topic_discussed,
                'status': status_map.get(record.session_id),
                'facultyName': record.faculty_name
            })
        return jsonify({
            'success': True,
            'history': history
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to fetch student history'}), 500

#To clean the schedules automatically for every 100 days at 5:00PM
def cleanup_old_schedules(app):
    
    with app.app_context():
        try:            
            cutoff_date = date.today() - timedelta(days=100)
            
            # Delete schedules older than 100 days
            deleted_count = Schedule.query.filter(Schedule.date < cutoff_date).delete()
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()

# Helper function to convert 24hr to 12hr format
def format_time_12hr(time_str):
    """Convert '08:30' to '08:30 AM' or '14:30' to '02:30 PM'"""
    try:
        time_obj = datetime.strptime(time_str, '%H:%M')
        return time_obj.strftime('%I:%M %p')
    except:
        return time_str

def cleanup_expired_schedules():
    """Automatically delete schedules that have expired (end_time + 30 minutes)"""
    try:
        from app import create_app, db
        from app.models import Schedule
        from datetime import datetime, timedelta
        
        app = create_app()
        
        with app.app_context():
            current_datetime = datetime.now()
            current_date = current_datetime.date()
            current_time = current_datetime.time()
            
            # ✅ OPTIMIZED: Use a single DELETE query instead of loading all schedules
            # Calculate time 30 minutes ago
            time_threshold = (current_datetime - timedelta(minutes=30)).time()
            
            # Delete schedules where:
            # 1. Date is before today (already expired)
            # 2. OR date is today AND end_time + 30min is before current time
            # 3. AND status is False (not completed)
            # 4. AND OTP is empty or null (not active)
            deleted_count = db.session.query(Schedule).filter(
                Schedule.status == False,
                db.or_(Schedule.otp == "", Schedule.otp.is_(None)),
                db.or_(
                    # Past dates
                    Schedule.date < current_date,
                    # Today but time has passed (end_time < current_time - 30min)
                    db.and_(
                        Schedule.date == current_date,
                        Schedule.end_time < time_threshold.strftime('%H:%M')
                    )
                )
            ).delete(synchronize_session='fetch')
            
            db.session.commit()
            
    except Exception as e:
        pass

# Add this to your scheduler
def start_cleanup_scheduler(app):
    """Start scheduler for automatic cleanup of expired schedules"""
    global scheduler
    
    # Add cleanup job to run every 5 minutes
    scheduler.add_job(
        func=cleanup_expired_schedules,
        trigger='interval',
        minutes=5,
        id='cleanup_expired_schedules',
        name='Clean up expired schedules every 5 minutes'
    )





# ==================== PUSH NOTIFICATION ROUTES ====================

@routes.route('/api/notifications/register-token', methods=['POST'])
def register_fcm_token():
    """Register or update FCM token for a student"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        email = data.get('email')
        fcm_token = data.get('fcm_token')
        device_type = data.get('device_type', 'android')  # default to android
        
        # Validate required fields
        if not email or not fcm_token:
            return jsonify({
                'success': False,
                'error': 'Email and FCM token are required'
            }), 400
        
        # Validate email domain
        if not email.endswith('@rguktrkv.ac.in'):
            return jsonify({
                'success': False,
                'error': 'Invalid email domain. Must be @rguktrkv.ac.in'
            }), 400
        
        # Check if student exists
        student = Student.query.filter_by(email=email).first()
        if not student:
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        # Check if token already exists for this email and device
        existing_token = FCMToken.query.filter_by(
            student_email=email,
            device_type=device_type
        ).first()
        
        if existing_token:
            # Update existing token
            existing_token.fcm_token = fcm_token
            existing_token.updated_at = datetime.now()
        else:
            # Create new token entry
            new_token = FCMToken(
                student_email=email,
                fcm_token=fcm_token,
                device_type=device_type
            )
            db.session.add(new_token)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'FCM token registered successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routes.route('/api/notifications/remove-token', methods=['POST'])
def remove_fcm_token():
    """Remove FCM token for a student (when permission is revoked)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        email = data.get('email')
        fcm_token = data.get('fcm_token')  # May be null if permission already revoked
        device_type = data.get('device_type', 'android')  # default to android
        
        # Validate required fields
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Check if student exists
        student = Student.query.filter_by(email=email).first()
        if not student:
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        # Remove token based on email and device type
        # If fcm_token is provided, match it as well for extra safety
        if fcm_token:
            deleted_count = FCMToken.query.filter_by(
                student_email=email,
                device_type=device_type,
                fcm_token=fcm_token
            ).delete()
        else:
            # If no token provided, remove all tokens for this email and device type
            deleted_count = FCMToken.query.filter_by(
                student_email=email,
                device_type=device_type
            ).delete()
        
        db.session.commit()
        
        if deleted_count > 0:
            return jsonify({
                'success': True,
                'message': 'FCM token removed successfully'
            }), 200
        else:
            # Token not found, but that's okay - the end result is the same
            return jsonify({
                'success': True,
                'message': 'FCM token removed successfully'
            }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routes.route('/api/cr/send-notification', methods=['POST'])
def send_class_notification():
    """CR sends notification to all students in their class"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        cr_email = data.get('cr_email')
        title = data.get('title', 'Class Update')
        message_body = data.get('message')
        
        # Validate required fields
        if not cr_email or not message_body:
            return jsonify({
                'success': False,
                'error': 'CR email and message are required'
            }), 400
        
        # 1. Verify CR status and get student info
        student = Student.query.filter_by(email=cr_email).first()
        if not student:
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        # Check if student is a CR
        cr_record = CR.query.filter_by(student_id=student.id).first()
        if not cr_record:
            return jsonify({
                'success': False,
                'error': 'Not authorized. Only CRs can send notifications'
            }), 403
        
        # 2. Get all students in the same class (excluding the CR)
        classmates = Student.query.filter(
            Student.year == student.year,
            Student.department == student.department,
            Student.section == student.section,
            Student.email != cr_email
        ).all()
        
        if not classmates:
            return jsonify({
                'success': False,
                'error': 'No students found in your class'
            }), 404
        
        student_emails = [s.email for s in classmates]
        
        # 3. Get FCM tokens for these students
        fcm_records = FCMToken.query.filter(
            FCMToken.student_email.in_(student_emails)
        ).all()
        
        if not fcm_records:
            return jsonify({
                'success': False,
                'error': 'No students with registered devices found'
            }), 404
        
        tokens = [record.fcm_token for record in fcm_records]
        
        # 4. Send FCM notification using Firebase Admin SDK
        try:
            # Import Firebase Admin SDK (lazy import)
            from firebase_admin import messaging
            
            successful = 0
            failed = 0
            
            # Split tokens into batches of 500 (FCM limit)
            batch_size = 500
            for i in range(0, len(tokens), batch_size):
                batch_tokens = tokens[i:i + batch_size]
                
                # Create FCM message
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title=title,
                        body=message_body,
                    ),
                    data={
                        'type': 'class_update',
                        'cr_name': student.name,
                        'cr_email': cr_email,
                        'timestamp': str(int(time.time())),
                        'year': str(student.year),
                        'department': student.department,
                        'section': student.section
                    },
                    tokens=batch_tokens,
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            channel_id='class_updates',
                            sound='default',
                            priority='high'
                        )
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                sound='default',
                                badge=1
                            )
                        )
                    )
                )
                
                # Send the message
                response = messaging.send_each_for_multicast(message)
                successful += response.success_count
                failed += response.failure_count
            
            # 5. Log the notification
            notification_log = NotificationLog(
                cr_email=cr_email,
                title=title,
                message=message_body,
                recipient_count=len(tokens),
                status='success' if failed == 0 else ('partial' if successful > 0 else 'failed')
            )
            db.session.add(notification_log)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Notification sent to {successful} students',
                'details': {
                    'total_students': len(classmates),
                    'registered_devices': len(tokens),
                    'successful': successful,
                    'failed': failed
                }
            }), 200
            
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'Firebase Admin SDK not installed. Please install: pip install firebase-admin'
            }), 500
        except Exception as fcm_error:
            return jsonify({
                'success': False,
                'error': f'Failed to send notification: {str(fcm_error)}'
            }), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routes.route('/api/notifications/history', methods=['GET'])
def get_notification_history():
    """Get notification history for a CR"""
    try:
        cr_email = request.args.get('cr_email')
        
        if not cr_email:
            return jsonify({
                'success': False,
                'error': 'CR email is required'
            }), 400
        
        # Verify CR
        student = Student.query.filter_by(email=cr_email).first()
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        cr_record = CR.query.filter_by(student_id=student.id).first()
        if not cr_record:
            return jsonify({'success': False, 'error': 'Not authorized as CR'}), 403
        
        # Get notification history
        notifications = NotificationLog.query.filter_by(
            cr_email=cr_email
        ).order_by(NotificationLog.sent_at.desc()).limit(50).all()
        
        history = []
        for notif in notifications:
            history.append({
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'recipient_count': notif.recipient_count,
                'sent_at': notif.sent_at.isoformat() if notif.sent_at else None,
                'status': notif.status
            })
        
        return jsonify({
            'success': True,
            'notifications': history
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# DEVICE BINDING ENDPOINTS
# ============================================================================

@routes.route('/student/device-binding/<string:student_id>', methods=['GET'])
def get_device_binding(student_id):
    """
    Get the stored binding_id for a student
    
    Returns:
        200: { "success": true, "binding_id": "bind_xxx" } or { "success": true, "binding_id": null }
        404: { "success": false, "message": "Student not found" }
        500: { "success": false, "message": "Server error" }
    """
    try:
        # Query database for student
        student = Student.query.filter_by(id=student_id).first()
        
        # Check if student exists
        if not student:
            return jsonify({
                'success': False,
                'message': 'Student not found'
            }), 404
        
        # Return binding_id (can be None/null)
        return jsonify({
            'success': True,
            'binding_id': student.binding_id
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Server error'
        }), 500


@routes.route('/student/bind-device/<string:student_id>', methods=['POST'])
def bind_device(student_id):
    """
    Save/update the binding_id for a student (used on first login)
    
    Request Body:
        { "binding_id": "bind_a3f5c89d_1696854321000" }
    
    Returns:
        200: { "success": true, "message": "Device bound successfully" }
        400: { "success": false, "message": "binding_id is required" }
        404: { "success": false, "message": "Student not found" }
        500: { "success": false, "message": "Server error" }
    """
    try:
        # Get binding_id from request body
        data = request.get_json()
        
        if not data or 'binding_id' not in data:
            return jsonify({
                'success': False,
                'message': 'binding_id is required'
            }), 400
        
        binding_id = data['binding_id']
        
        if not binding_id:
            return jsonify({
                'success': False,
                'message': 'binding_id is required'
            }), 400
        
        # Check if student exists
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return jsonify({
                'success': False,
                'message': 'Student not found'
            }), 404
        
        # Update binding_id
        student.binding_id = binding_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Device bound successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@routes.route('/admin/reset-device-binding/<string:student_id>', methods=['POST'])
def reset_device_binding(student_id):
    """
    Admin endpoint to reset a student's device binding (sets binding_id to NULL)
    
    Note: In production, add authentication middleware to verify admin access
    
    Returns:
        200: { "success": true, "message": "Device binding reset successfully" }
        404: { "success": false, "message": "Student not found" }
        500: { "success": false, "message": "Server error" }
    """
    try:
        # TODO: Add admin authentication check here
        # Example: verify JWT token, check if user has admin role, etc.
        
        # Find student
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return jsonify({
                'success': False,
                'message': 'Student not found'
            }), 404
        
        # Reset binding_id to NULL
        old_binding = student.binding_id
        student.binding_id = None
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Device binding reset successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Server error'
        }), 500