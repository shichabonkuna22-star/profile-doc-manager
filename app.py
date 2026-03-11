import os
import uuid
from datetime import datetime
import pytz
from flask import Flask, request, render_template, redirect, url_for, flash, send_from_directory, abort
from werkzeug.utils import secure_filename
from models import db, User, Document

app = Flask(__name__)

# Configuration from environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Handle database URL - Render provides 'postgres://' but SQLAlchemy needs 'postgresql://'
database_url = os.environ.get('DATABASE_URL', 'sqlite:///documents.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload folder - use a persistent disk path if set, otherwise local
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Subfolders for different file types
DOCUMENT_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'documents')
PROFILE_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')
os.makedirs(DOCUMENT_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_DOC_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'txt'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# South African timezone
SA_TZ = pytz.timezone('Africa/Johannesburg')

db.init_app(app)

# -------------------------------------------------------------------
# Context processor to inject current user (dummy user 1) into all templates
# -------------------------------------------------------------------
@app.context_processor
def inject_user():
    user = User.query.get(1)
    return dict(current_user=user)

# -------------------------------------------------------------------
# Template filter to convert UTC datetime to SA time
# -------------------------------------------------------------------
@app.template_filter('sast')
def sast_filter(dt):
    """Convert naive or UTC datetime to South African time."""
    if dt is None:
        return ''
    # If datetime is naive, assume it's UTC
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(SA_TZ).strftime('%Y-%m-%d %H:%M')

# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------
def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def get_user_by_id(user_id):
    return User.query.get(user_id)

def user_has_cv(user_id):
    return Document.query.filter_by(user_id=user_id, file_type='cv').first() is not None

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

# -------------------- Profile Image Upload --------------------
@app.route('/upload_profile_image/<int:user_id>', methods=['GET', 'POST'])
def upload_profile_image(user_id):
    user = get_user_by_id(user_id)
    if not user:
        abort(404, description="User not found")

    if request.method == 'POST':
        if 'profile_image' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['profile_image']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            # Delete old profile image if exists
            if user.profile_image:
                old_path = os.path.join(PROFILE_FOLDER, user.profile_image)
                if os.path.exists(old_path):
                    os.remove(old_path)

            # Save new image
            orig_filename = secure_filename(file.filename)
            ext = orig_filename.rsplit('.', 1)[1].lower()
            unique_name = f"user_{user_id}_{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(PROFILE_FOLDER, unique_name)
            file.save(filepath)

            user.profile_image = unique_name
            db.session.commit()
            flash('Profile image updated successfully.')
            return redirect(url_for('user_documents', user_id=user_id))
        else:
            flash('Invalid image type. Allowed: ' + ', '.join(ALLOWED_IMAGE_EXTENSIONS))
            return redirect(request.url)

    return render_template('upload_profile_image.html', user=user)

# -------------------- Document Upload --------------------
@app.route('/upload/<int:user_id>', methods=['GET', 'POST'])
def upload_document(user_id):
    user = get_user_by_id(user_id)
    if not user:
        abort(404, description="User not found")

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        doc_type = request.form.get('doc_type')
        if doc_type not in ['cv', 'transcript', 'qualification', 'other']:
            flash('Invalid document type')
            return redirect(request.url)

        if doc_type != 'cv' and not user_has_cv(user_id):
            flash('You must upload your CV first before adding other documents.')
            return redirect(request.url)

        if file and allowed_file(file.filename, ALLOWED_DOC_EXTENSIONS):
            orig_filename = secure_filename(file.filename)
            ext = orig_filename.rsplit('.', 1)[1].lower() if '.' in orig_filename else ''
            unique_name = f"{user_id}_{uuid.uuid4().hex}.{ext}" if ext else f"{user_id}_{uuid.uuid4().hex}"
            filepath = os.path.join(DOCUMENT_FOLDER, unique_name)
            file.save(filepath)

            new_doc = Document(
                filename=orig_filename,
                stored_name=unique_name,
                file_type=doc_type,
                user_id=user_id
            )
            db.session.add(new_doc)
            db.session.commit()

            flash('File uploaded successfully.')
            return redirect(url_for('user_documents', user_id=user_id))
        else:
            flash('File type not allowed. Allowed types: ' + ', '.join(ALLOWED_DOC_EXTENSIONS))
            return redirect(request.url)

    return render_template('upload.html', user_id=user_id)

# -------------------- List User's Documents --------------------
@app.route('/documents/<int:user_id>')
def user_documents(user_id):
    user = get_user_by_id(user_id)
    if not user:
        abort(404, description="User not found")
    docs = Document.query.filter_by(user_id=user_id).order_by(Document.upload_date.desc()).all()
    return render_template('profile.html', user=user, docs=docs)

# -------------------- Download a Document --------------------
@app.route('/download/<int:doc_id>')
def download_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    # Security: add ownership check later
    return send_from_directory(
        DOCUMENT_FOLDER,
        doc.stored_name,
        download_name=doc.filename,
        as_attachment=True
    )

# -------------------- Preview a Document --------------------
@app.route('/preview/<int:doc_id>')
def preview_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return render_template('preview.html', doc=doc)

# -------------------- Serve Document Files (for preview) --------------------
@app.route('/uploads/documents/<path:filename>')
def uploaded_document(filename):
    return send_from_directory(DOCUMENT_FOLDER, filename)

# -------------------- Serve Profile Images --------------------
@app.route('/uploads/profiles/<path:filename>')
def uploaded_profile(filename):
    return send_from_directory(PROFILE_FOLDER, filename)

# -------------------------------------------------------------------
# Create tables and a test user (only if using SQLite locally)
# For production, use a separate init script or Flask CLI command.
# -------------------------------------------------------------------
@app.cli.command('initdb')
def initdb_command():
    """Initialize the database."""
    db.create_all()
    if not User.query.first():
        dummy = User()
        db.session.add(dummy)
        db.session.commit()
        print('Created dummy user with id = 1')
    print('Initialized the database.')

if __name__ == '__main__':
    app.run(debug=True)