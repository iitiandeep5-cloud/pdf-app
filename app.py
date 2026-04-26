import os
import requests
import cloudinary
import cloudinary.uploader
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, Response)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from models import db, User, PDFFile

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pdfs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username=os.getenv('ADMIN_USERNAME', 'admin')).first():
        admin = User(
            username=os.getenv('ADMIN_USERNAME', 'admin'),
            password=generate_password_hash(os.getenv('ADMIN_PASSWORD', 'password'))
        )
        db.session.add(admin)
        db.session.commit()

# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ── Main routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    files = PDFFile.query.order_by(PDFFile.upload_date.desc()).all()
    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('No file selected.')
        return redirect(url_for('index'))

    file = request.files['file']
    description = request.form.get('description', '')

    if file.filename == '' or not file.filename.endswith('.pdf'):
        flash('Please select a valid PDF file.')
        return redirect(url_for('index'))

    result = cloudinary.uploader.upload(
        file,
        resource_type='raw',
        folder='pdf_library',
        use_filename=True,
        unique_filename=True
    )

    pdf = PDFFile(
        filename=secure_filename(file.filename),
        original_name=file.filename,
        description=description,
        file_size=result.get('bytes', 0),
        cloudinary_url=result.get('secure_url', ''),
        cloudinary_id=result.get('public_id', '')
    )
    db.session.add(pdf)
    db.session.commit()
    flash(f'"{file.filename}" uploaded successfully!')
    return redirect(url_for('index'))

@app.route('/delete/<int:pdf_id>', methods=['POST'])
@login_required
def delete(pdf_id):
    pdf = PDFFile.query.get_or_404(pdf_id)
    if pdf.cloudinary_id:
        cloudinary.uploader.destroy(pdf.cloudinary_id, resource_type='raw')
    db.session.delete(pdf)
    db.session.commit()
    flash(f'"{pdf.filename}" deleted.')
    return redirect(url_for('index'))

@app.route('/view/<int:pdf_id>')
def view(pdf_id):
    pdf = PDFFile.query.get_or_404(pdf_id)
    return render_template('view.html', pdf=pdf)

@app.route('/download/<int:pdf_id>')
def download(pdf_id):
    pdf = PDFFile.query.get_or_404(pdf_id)
    response = requests.get(pdf.cloudinary_url)
    return Response(
        response.content,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{pdf.original_name}"'
        }
    )

if __name__ == '__main__':
    app.run(debug=True)