import functools
from flask import (Blueprint, flash, g, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from . import es_mappings as es

bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='templates/auth')


# (KASNIJE) odma da se proveri da li moze username
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        error = 'Already logged in.'
        flash(error)
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        s = es.User.search().query('term', username__raw=username)
        s = s.source(False)
        response = s.execute()
        error = None

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif not email:
            error = 'Email is required.'
        elif response.hits.total.value > 0:
            error = 'User already exists.'

        if error is None:
            user = es.User()
            user.email = email
            user.username = username
            user.password = generate_password_hash(password)
            user.save()
            return redirect(url_for('auth.login'))

        flash(error)

    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        error = 'Already logged in.'
        flash(error)
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        error = None
        s = es.User.search().query('term', username__raw=username)
        response = s.execute()

        user = None
        if response.hits.total.value > 0:
            user = response.hits[0]

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user.meta.id
            flash("Successfully logged in as " + user.username + ".")
            return redirect(url_for('index'))

        flash(error)

    return render_template('login.html')


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = es.User.get(user_id)


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(request.referrer)


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view


# napravi da radi kako treba, nije bitno trenutno
def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None or g.user['username'] != 'Bluebell':
            # da se ispise greska pre nego sto se preusmeri
            return redirect(url_for('index'))

        return view(**kwargs)

    return wrapped_view
