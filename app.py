import re
import os

from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    balance = db.Column(db.Float, default=0.0)

class Auction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    starting_price = db.Column(db.Float, nullable=False)
    bids = db.relationship('Bid', backref='auction', cascade='all, delete-orphan')

class Bid(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    auction_id = db.Column(db.Integer, db.ForeignKey('auction.id', name='fk_bid_auction'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_bid_user'), nullable=False)
    user = db.relationship('User', backref=db.backref('bids', lazy=True))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/users')
def list_users():
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['username'] = user.username
            if user.role == 'Admin':
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('buyer'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form['role']

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
        elif len(password) < 7 or not re.search(r'\d', password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            flash('Password must be at least 7 characters long, contain at least one number and one special character', 'danger')
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(username=username, password=hashed_password, role=role)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/admin')
def admin():
    auctions = Auction.query.all()
    return render_template('admin.html', auctions=auctions)

@app.route('/buyer')
def buyer():
    user = User.query.filter_by(username=session['username']).first()
    auctions = Auction.query.all()
    for auction in auctions:
        auction.has_ended = auction.end_date < datetime.utcnow()
        if auction.has_ended and auction.bids:
            auction.winner = auction.bids[-1].user.username
        else:
            auction.winner = None
    db.session.commit()  # Commit the changes to the database
    return render_template('buyer.html', auctions=auctions, balance=user.balance)

@app.route('/create_auction', methods=['GET', 'POST'])
def create_auction():
    if request.method == 'POST':
        if 'image' not in request.files:
            return redirect(request.url)
        file = request.files['image']
        if file.filename == '':
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            description = request.form['description']
            end_date_str = request.form['end_date']
            starting_price = float(request.form['starting_price'])

            if starting_price < 0:
                return redirect(request.url)

            end_date = datetime.fromisoformat(end_date_str)

            new_auction = Auction(image=image_url, description=description, end_date=end_date, starting_price=starting_price)
            db.session.add(new_auction)
            db.session.commit()
            return redirect(url_for('admin'))
    return render_template('create_auction.html')

@app.route('/edit_auction/<int:id>', methods=['GET', 'POST'])
def edit_auction(id):
    auction = Auction.query.get_or_404(id)
    if request.method == 'POST':
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                auction.image = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        auction.description = request.form['description']
        end_date_str = request.form['end_date']
        starting_price = float(request.form['starting_price'])

        if starting_price < 0:
            return redirect(request.url)

        auction.end_date = datetime.fromisoformat(end_date_str)
        auction.starting_price = starting_price

        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('edit_auction.html', auction=auction)

@app.route('/view_auction/<int:id>', methods=['GET', 'POST'])
def view_auction(id):
    auction = Auction.query.get_or_404(id)
    user = User.query.filter_by(username=session['username']).first()
    if request.method == 'POST':
        bid_amount = float(request.form['bid_amount'])
        last_bid = Bid.query.filter_by(auction_id=auction.id, user_id=user.id).order_by(Bid.timestamp.desc()).first()
        highest_bid = auction.bids[-1].amount if auction.bids else auction.starting_price

        if last_bid:
            total_bid = last_bid.amount + bid_amount
            amount_to_deduct = bid_amount
        else:
            total_bid = bid_amount
            amount_to_deduct = bid_amount

        if total_bid > highest_bid:
            if user.balance >= amount_to_deduct:
                new_bid = Bid(amount=total_bid, auction_id=auction.id, user_id=user.id)
                user.balance -= amount_to_deduct
                db.session.add(new_bid)
                db.session.commit()
            else:
                flash('', 'danger')
        else:
            flash('', 'danger')
    return render_template('view_auction.html', auction=auction, balance=user.balance)

@app.route('/delete_auction/<int:id>', methods=['POST'])
def delete_auction(id):
    auction = Auction.query.get_or_404(id)
    db.session.delete(auction)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/add_money', methods=['POST'])
def add_money():
    user = User.query.filter_by(username=session['username']).first()
    amount = float(request.form['amount'])
    if user.balance is None:
        user.balance = 0.0
    user.balance += amount
    db.session.commit()
    return {'success': True, 'new_balance': user.balance}

if __name__ == '__main__':
    app.run()