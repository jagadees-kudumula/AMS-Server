from flask import Flask, request, jsonify, Blueprint
from app import db
from app.models import CR, Student, Faculty, FacultyAssignment, Subject, DefaultSchedule
import pandas as pd
import io
import json

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

    faculty_json = request.form.get("faculty")  # get the string
    data = json.loads(faculty_json)  # convert string -> dict
 
    faculty_id = data['id']
    name = data['name']
    department = data['department']
    section = data['section']
    year = data['year']
    subject_code = data['subject_code']

    
    year = batchToYear[year]

    try:
        # Check if the faculty already exists
        faculty = Faculty.query.get(faculty_id)
        if not faculty:
            # Add new faculty
            faculty = Faculty(id=faculty_id, name=name, email=faculty_id.lower() + "@rguktrkv.ac.in")
            db.session.add(faculty)

        #Here we have to check if the faculty assignment already exists
            #This will be implemented later
        
        existing_assignment = FacultyAssignment.query.filter_by(
                    faculty_id=faculty_id,
                    subject_code=subject_code,
                    year=year,
                    department=department,
                    section=section
                ).first()
            
        if existing_assignment:
            return jsonify({'success': False, 'message': 'The assignment already exists'}), 201

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

        return jsonify({'success': True, 'message': 'Faculty and assignment added successfully.', 'faculty' : new_faculty_assignment}), 201
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
