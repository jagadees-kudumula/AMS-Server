from flask import Flask, request, jsonify, Blueprint
from app import db
from app.models import CR, Student
import pandas as pd
import io

routes = Blueprint('main', __name__)

@routes.route('/upload_students', methods=['POST'])
def upload_students():
    print("Upload endpoint hit")
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    year = request.form['year']
    department = request.form['departmentName']


    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
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
        return jsonify({'message': f'{len(df)} students added successfully.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

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