from app import create_app, db
from app.models import Student

app = create_app()

with app.app_context():
    app.run(debug=True)
    print("Tables created successfully!")
