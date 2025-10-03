from flask import Flask, request, jsonify, Blueprint,current_app
from app import db
from app.models import CR, Student, Faculty, FacultyAssignment, Subject, DefaultSchedule,Schedule
import pandas as pd
import io
import json
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

from threading import Timer

routes = Blueprint('main', __name__)
batchToYear = {'E1':1,'E2':2,'E3':3,'E4':4}

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
        print("Error 1")
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

        # Expected columns: id, name, email, year, department, section

        for index, row in df.iterrows():
            student = Student(
                id=row['id'],
                name=row['name'],
                email=row['id'].lower() + "@rguktrkv.ac.in",
                year=year,
                department=department,
                section=row['section']
            )
            db.session.add(student)
        

        db.session.commit()
        return jsonify({'success':True,'message': f'{len(df)} students added successfully.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': "Students are already int the table."}), 500

@routes.route('/crs', methods=['GET', 'POST'])
def handle_crs():
    if request.method == 'GET':
        # Get all CRs with student details
        try:
            crs = CR.query.all()
            cr_data = []
            
            for cr in crs:
                student = Student.query.get(cr.student_id)
                if student:
                    cr_data.append({
                        'id': cr.student_id,
                        'name': student.name,
                        'email': student.email,
                        'year': student.year,
                        'branch': student.department,
                        'section': student.section,
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
        print(e)
        return jsonify({'success': False, 'message': 'Server error, could not remove CR.'}), 500

@routes.route('/crs/add', methods=['POST'])
def add_cr():
    data = request.form
    student_id = data['id']
    mobile = data['mobile']

    print(student_id, mobile)

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
        print(e)
        return jsonify({'success': False, 'message': 'Server error, could not add CR.'}), 500

@routes.route('/faculties', methods=['GET'])
def get_faculties():
    try:
        
        faculty_assignments = FacultyAssignment.query.all()
        faculty_list = []

        for fa in faculty_assignments:
            faculty_details = {
                'subject_code': fa.subject_code,
                'year': fa.year,
                'department': fa.department,
                'section': fa.section,
                'assignment_id': fa.id
            }

            faculty = Faculty.query.get(fa.faculty_id)

            faculty_details.update({
                'id': faculty.id,
                'name': faculty.name,
                'email': faculty.email
            })     
        
            faculty_list.append(faculty_details)
    
        return jsonify({'success': True, 'faculties': faculty_list}), 200
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Server error, could not fetch faculties.'}), 500

@routes.route('/faculties/upload_faculty', methods=['POST'])
def upload_faculty():

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    
    try:
        df = pd.read_excel(file)
        
        for index,row in df.iterrows():
            faculty_id = row['FacultyId']
            faculty_name = row['FacultyName']
            subject_code = row['SubjectCode']
            department = row['Department']
            year = batchToYear[row['Year']]
            section = row['Section']
            
            faculty = Faculty.query.filter_by(id=faculty_id).first()

            if not faculty:
                email = f"{faculty_id}@rguktrkv.ac.in"
                faculty = Faculty(
                    id=faculty_id,
                    name=faculty_name,
                    email=email
                )
                db.session.add(faculty)
            
            existing_assignment = FacultyAssignment.query.filter_by(
                    faculty_id=faculty_id,
                    subject_code=subject_code,
                    year=year,
                    department=department,
                    section=section
                ).first()
            
            if existing_assignment:
                return jsonify({'success': False, 'message': 'The assignment already exists'}), 201
            
            faculty_assignment = FacultyAssignment(
                faculty_id=faculty_id,
                subject_code=subject_code,
                year=year,
                department=department,
                section=section
            )

            db.session.add(faculty_assignment)

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
        print(f"Error adding faculty: {str(e)}")
        return jsonify({'success': False, 'message': 'Server error, could not add faculty.'}), 500

@routes.route('/faculties/remove/<int:assignment_id>', methods=['DELETE'])
def remove_faculty_assignment(assignment_id):
    # Find the FacultyAssignment record in the database using the assignment_id
    assignment_to_remove = FacultyAssignment.query.get(assignment_id)

    # If the assignment doesn't exist, return a 404 Not Found error
    if not assignment_to_remove:
        return jsonify({'success': False, 'message': 'Faculty assignment not found.'}), 404
        # Check if the faculty has any other assignments

    try:
        # Delete the record from the database session
        db.session.delete(assignment_to_remove)
       

        faculty_id = assignment_to_remove.faculty_id
        other_assignments = FacultyAssignment.query.filter(FacultyAssignment.faculty_id == faculty_id, FacultyAssignment.id != assignment_id).all()

        # If no other assignments exist, delete the faculty from the Faculty table
        if not other_assignments:
            faculty_to_remove = Faculty.query.get(faculty_id)
            if faculty_to_remove:
                db.session.delete(faculty_to_remove)

        # Commit the change to the database
        db.session.commit()
        
        # Return a success message
        return jsonify({'success': True, 'message': 'Faculty assignment removed successfully'}), 200
    except Exception as e:
        # If any database error occurs, roll back the session
        db.session.rollback()
        print(e)
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
        print(e)
        return jsonify({'success': False, 'message': 'Server error, could not update faculty assignment.'}), 500

@routes.route('/subjects/upload', methods=['POST'])
def upload_subjects():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    isreplace = request.form['replace']

    if file.filename == '':
        print("Error 1")
        return jsonify({'error': 'No selected file'}), 400

    try:
        if isreplace == 'true':
            try:
                Subject.query.filter_by().delete(synchronize_session=False)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(str(e))
                return jsonify({'message': str(e)}), 500

        # Read Excel into a DataFrame
        df = pd.read_excel(file)

        # Expected columns: id, name, email, year, department, section

        for index, row in df.iterrows():
            subject = Subject(
                subject_code=row['code'],
                subject_mnemonic=row['mnemonic'],
                subject_name=row['name'],
                subject_type=row['type']
            )
            db.session.add(subject)
        

        db.session.commit()
        return jsonify({'message': f'{len(df)} subjects added successfully.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': "Subjects are already int the table."}), 500


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

     # 3. Handle Replace Flag (Clear existing schedules for this group)
    if isreplace == 'true':
        try:
            # 1. Find all FacultyAssignment IDs (assignment_id) matching the year and department.
            assignment_ids_to_clear = db.session.query(FacultyAssignment.id).filter(
                FacultyAssignment.year == year,
                FacultyAssignment.department == department
            ).subquery()
            
            # 2. Delete the corresponding DefaultSchedule records using the found IDs.
            # This is the corrected and safe delete operation.
            db.session.query(DefaultSchedule).filter(
                DefaultSchedule.assignment_id.in_(assignment_ids_to_clear.select())
            ).delete(synchronize_session='fetch')
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': f'Failed to clear old schedules: {e}'}), 500

    try:
        df = pd.read_excel(file)

        for index, row in df.iterrows():

            day_of_week = row['Day']
            section = row['Section']
            period = row['Period']
            subject_code = row['SubjectCode']
            faculty_id = row['FacultyId']
            venue = row['Venue']

            subject_type = db.session.query(Subject.subject_type).filter(Subject.subject_code == subject_code).scalar()

            if subject_type.lower() == "lab":
                start_time = PERIOD_TIMES[period][0]
                end_period = period + LAB_DURATION - 1
                if end_period not in PERIOD_TIMES:
                    raise ValueError(f"Lab starting at period {period} exceeds available periods")
                end_time = PERIOD_TIMES[end_period][1]
            else:
                start_time, end_time = PERIOD_TIMES[period]
            
            # the use of .scalar() method is to Return the first element of the first result or None if no rows present. If multiple rows are returned, raises
            assignment_id = db.session.query(FacultyAssignment.id).filter(
                        FacultyAssignment.department == department, 
                        FacultyAssignment.subject_code == subject_code, 
                        FacultyAssignment.section == section,
                        FacultyAssignment.year == year, 
                        FacultyAssignment.faculty_id == faculty_id).scalar()

            defaultSchedule = DefaultSchedule(
                day_of_week = day_of_week,
                start_time = start_time,
                end_time = end_time,
                assignment_id = assignment_id,
                venue = venue
            )

            db.session.add(defaultSchedule)

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
                'status': schedule.status
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
        print(f"Error fetching faculty schedule: {str(e)}")
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
        print(f"Error fetching faculty subjects: {str(e)}")
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

        # Get all schedules for this group on the given date
        existing_schedules = db.session.query(Schedule)\
            .join(FacultyAssignment, Schedule.assignment_id == FacultyAssignment.id)\
            .filter(
                FacultyAssignment.year == year,
                FacultyAssignment.department == department,
                FacultyAssignment.section == section,
                Schedule.date == target_date
            ).all()

        print(f"Found {len(existing_schedules)} existing schedules for conflict checking")

        if subject_type == "lab":
            # Lab: 3-hour slots (consecutive periods)
            for i in range(len(all_slots) - 2):
                slot_start = all_slots[i][0]
                slot_end = all_slots[i + 2][1]
                # Skip slots that would include 12:30 to 13:30
                if slot_start < '12:30' < slot_end:
                    continue
                conflict = False
                for existing in existing_schedules:
                    # Check if time slots overlap
                    if not (slot_end <= existing.start_time or slot_start >= existing.end_time):
                        conflict = True
                        print(f"Conflict found: {slot_start}-{slot_end} vs {existing.start_time}-{existing.end_time}")
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
                for existing in existing_schedules:
                    if not (slot_end <= existing.start_time or slot_start >= existing.end_time):
                        conflict = True
                        print(f"Conflict found: {slot_start}-{slot_end} vs {existing.start_time}-{existing.end_time}")
                        break
                if not conflict:
                    available_slots.append({
                        'start_time': slot_start,
                        'end_time': slot_end
                    })

        print(f"Available slots: {available_slots}")

        return jsonify({
            'success': True,
            'available_slots': available_slots,
            'total_slots': len(available_slots)
        }), 200

    except Exception as e:
        print(f"Error fetching available slots: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
# Create Schedule Endpoint
@routes.route('/schedule', methods=['POST'])
def create_schedule():
    try:
        data = request.get_json()
        print(f"📥 Received schedule creation request: {data}")
        
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
        
        print(f"🔍 Looking for faculty assignment with: faculty_id={data['faculty_id']}, year={year}, department={data['department']}, section={data['section']}")
        
        # Find the faculty assignment
        assignment = FacultyAssignment.query.filter_by(
            faculty_id=data['faculty_id'],
            year=year,  # Use the actual year number
            department=data['department'],
            section=data['section']
        ).first()
        
        if not assignment:
            # Debug: Check what assignments actually exist for this faculty
            faculty_assignments = FacultyAssignment.query.filter_by(
                faculty_id=data['faculty_id']
            ).all()
            
            print(f"❌ No assignment found. Available assignments for faculty {data['faculty_id']}:")
            for fa in faculty_assignments:
                print(f"  - Year: {fa.year}, Department: {fa.department}, Section: {fa.section}")
            
            return jsonify({
                'success': False, 
                'error': f'No faculty assignment found for {batch_display} {data["department"]} - {data["section"]}. Faculty may not be assigned to this class.'
            }), 400
        
        print(f"✅ Found faculty assignment: {assignment.id}")
        
        target_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        # Enhanced conflict checking
        existing_conflicts = Schedule.query\
            .join(FacultyAssignment)\
            .filter(
                Schedule.date == target_date,
                FacultyAssignment.faculty_id == data['faculty_id']
            )\
            .all()
        
        print(f"🔍 Checking conflicts: Found {len(existing_conflicts)} existing schedules")
        
        # Check each existing schedule for time overlap
        for existing in existing_conflicts:
            if (data['start_time'] < existing.end_time and 
                data['end_time'] > existing.start_time):
                return jsonify({
                    'success': False, 
                    'error': f'Time conflict with {existing.start_time}-{existing.end_time} at {existing.venue}'
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
        
        print(f"✅ Schedule created successfully: ID {new_schedule.id}")
        
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
        print(f"❌ Error creating schedule: {str(e)}")
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
        print(f"Error deleting schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500



#Automation of Moving Schedules Daily at 17:58
scheduler = None

def start_daily_scheduler(app):
    
    global scheduler
    
    # Create scheduler
    scheduler = BackgroundScheduler(daemon=True)
    
    # Add the job to run daily at 17:58
    scheduler.add_job(
        func=move_tomorrow_schedules_auto,
        args=[app],
        trigger=CronTrigger(hour=17, minute=58),
        id='daily_schedule_move',
        name='Move tomorrow schedules daily at 5:58 PM'
    )
   
    # Start the scheduler
    scheduler.start()
    print("✅ Daily scheduler started - will run at 17:58 every day")
    
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
            target_date = date.today()  + timedelta(days=1)
            day_name = target_date.strftime('%a').upper()
            
            print(f"🤖 AUTO: Moving schedules for TOMORROW - {day_name} ({target_date})")
            
            # Get all default schedules for that day
            default_schedules = DefaultSchedule.query\
                .filter_by(day_of_week=day_name)\
                .all()
            
            created_count = 0
            skipped_count = 0
            
            for default_schedule in default_schedules:
                # Check if schedule already exists for target date
                existing_schedule = Schedule.query.filter_by(
                    assignment_id=default_schedule.assignment_id,
                    date=target_date
                ).first()
                
                if existing_schedule:
                    skipped_count += 1
                    continue
                    
                # Create new schedule entry
                new_schedule = Schedule(
                    assignment_id=default_schedule.assignment_id,
                    date=target_date,
                    start_time=default_schedule.start_time,
                    end_time=default_schedule.end_time,
                    venue=default_schedule.venue,
                    status=False
                )
                db.session.add(new_schedule)
                created_count += 1
            
            db.session.commit()
            
            print(f"✅ AUTO: Created {created_count} schedules for {day_name}, skipped {skipped_count}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ AUTO: Error moving schedules: {str(e)}")

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
        print(f"Error fetching server time: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to fetch server time'}), 500
    
@routes.route('/generate-otp', methods=['POST'])
def generate_otp():
    data = request.get_json()
    schedule_id = data.get('schedule_id')
    faculty_id = data.get('faculty_id')
    otp = data.get('otp')

    if not all([schedule_id, faculty_id, otp]):
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({'success': False, 'message': 'Schedule not found'}), 404

    assignment = FacultyAssignment.query.get(schedule.assignment_id)
    if not assignment or assignment.faculty_id != faculty_id:
        return jsonify({'success': False, 'message': 'Faculty not authorized for this schedule'}), 403

    # Store OTP and mark attendance as completed
    schedule.otp = otp
    schedule.status = True
    db.session.commit()

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

    print(f"⏰ OTP removal scheduled for schedule {schedule_id} at {run_date}")
    return jsonify({'success': True, 'otp': otp, 'schedule_id': schedule_id}), 200

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
                db.session.commit()
                print(f"✅ OTP cleared for schedule {schedule_id}")
            else:
                print(f"❌ Schedule {schedule_id} not found during OTP removal")
                
    except Exception as e:
        print(f"❌ Error removing OTP for schedule {schedule_id}: {str(e)}")


