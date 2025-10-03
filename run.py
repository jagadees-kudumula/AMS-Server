from app import create_app, db
from app.models import Student
from app.routes import start_daily_scheduler

app = create_app()

with app.app_context():
    start_daily_scheduler(app)
    app.run(host="0.0.0.0", port=5000, debug=True)