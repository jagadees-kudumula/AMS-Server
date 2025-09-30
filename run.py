from app import create_app, db
from app.models import Student

app = create_app()

with app.app_context():
    app.run(host="0.0.0.0", port=5000, debug=True)