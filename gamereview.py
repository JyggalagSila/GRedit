from flask import (Blueprint, flash, g, redirect, render_template, request, url_for, session)
from werkzeug.exceptions import abort
from werkzeug.security import check_password_hash, generate_password_hash
from .auth import login_required
from . import es_mappings as es
from elasticsearch import exceptions
from elasticsearch import *
from elasticsearch_dsl.query import Q
from math import ceil
from . import __init__


bp = Blueprint('base', __name__)
bpg = Blueprint('game', __name__, url_prefix='/game', template_folder='templates/games')
bpr = Blueprint('review', __name__, url_prefix='/review', template_folder='templates/reviews')
bpu = Blueprint('user', __name__, url_prefix='/user', template_folder='templates/users')


# BASE #################################################################################################################
# top 10 po ocenu, ne mora sad
# SVE OSIM RESPONSE JE REALNO NEPOTREBO! PREBACI U JS IZRACUJAVANJA
# HIGHLIGHT SEARCH RESULT, COMPLETE SUGGEST, ADD FUZZY
@bp.route('/', methods=['GET'])
def index():
    page = 1
    page_size = 12
    essearch = None
    tags = None
    sort = 'def'
    s = es.Game.search()

    if request.args.get('page'):
        page = int(request.args.get('page'))
    if request.args.get('page_size'):
        page_size = int(request.args.get('page_size'))
    if request.args.get('tags'):
        tags = request.args.getlist('tags')
        for tag in tags:
            s = s.query('match', tags=tag)
    if request.args.get('essearch'):
        essearch = request.args.get('essearch')
        q = Q('match', title={'query': essearch, 'boost': 10, 'fuzziness': 'auto'})\
            | Q('match_phrase', description={'query': essearch, 'slop': 5}) | Q('prefix', title=essearch) |\
            Q('match', developer=essearch) | Q('match', publisher=essearch)
        s = s.query(q)
    if request.args.get('sort'):
        sort = request.args.get('sort')
        if sort == 'title_asc':
            s = s.sort('title.raw')
        elif sort == 'title_desc':
            s = s.sort('-title.raw')
        elif sort == 'publisher_asc':
            s = s.sort('publisher.raw')
        elif sort == 'publisher_desc':
            s = s.sort('-publisher.raw')
        elif sort == 'developer_asc':
            s = s.sort('developer.raw')
        elif sort == 'developer_desc':
            s = s.sort('-developer.raw')
        elif sort == 'date_asc':
            s = s.sort('release_date')
        elif sort == 'date_desc':
            s = s.sort('-release_date')
        else:
            s = s.sort()

    s = s[page_size * (page - 1):page_size * page]
    s.aggs.bucket('types', es.A('terms', field='tags.raw', size=100, order={'_key': 'asc'}))
    response = s.execute()
    total_pages = ceil(response.hits.total.value / page_size)
    return render_template('games/index.html', response=response, page=page,
                           page_size=page_size, total_pages=total_pages, essearch=essearch, tags=tags, sort=sort)


@bp.route('/advanced', methods=['GET', 'POST'])
def advanced_search():
    if request.method == 'GET':
        s = es.Game.search()
        s.aggs.bucket('types', es.A('terms', field='tags.raw', size=100, order={'_key': 'asc'}))
        s = s[0:0]
        response = s.execute()
        return render_template('games/advanced.html', response=response)

    if request.method == 'POST':
        query = request.form['query']
        s = es.Game.search()

        if query != '':
            option = request.form['option']
            if option == 'title':
                s = s.query('match', title={'query': query, 'boost': 10, 'fuzziness': 'auto'})
            elif option == 'description':
                s = s.query('match_phrase', description={'query': query, 'slop': 5})
            elif option == 'both':
                q = Q('match', title={'query': query, 'boost': 10, 'fuzziness': 'auto'})\
                    | Q('match_phrase', description={'query': query, 'slop': 5})
                s = s.query(q)

        if request.form.getlist('include_tags'):
            include_tags = request.form.getlist('include_tags')
            for tag in include_tags:
                q = Q('match', tags=tag)
                s = s.query(q)
        if request.form.getlist('exclude_tags'):
            exclude_tags = request.form.getlist('exclude_tags')
            for tag in exclude_tags:
                q = ~Q('match', tags=tag)
                s = s.query(q)

        if request.form.get('publisher'):
            publisher = request.form['publisher']
            s = s.query('match', publisher=publisher)
        if request.form.get('developer'):
            developer = request.form['developer']
            s = s.query('match', developer=developer)

        date_start = request.form['date_start']
        date_end = request.form['date_end']
        s = s.query('range', release_date={'gte': date_start, 'lte': date_end})

        sort = request.form['sort']
        if sort == 'title_asc':
            s = s.sort('title.raw')
        elif sort == 'title_desc':
            s = s.sort('-title.raw')
        elif sort == 'publisher_asc':
            s = s.sort('publisher.raw')
        elif sort == 'publisher_desc':
            s = s.sort('-publisher.raw')
        elif sort == 'developer_asc':
            s = s.sort('developer.raw')
        elif sort == 'developer_desc':
            s = s.sort('-developer.raw')
        elif sort == 'date_asc':
            s = s.sort('release_date')
        elif sort == 'date_desc':
            s = s.sort('-release_date')
        else:
            s = s.sort()

        s.aggs.bucket('types', es.A('terms', field='tags.raw', size=100, order={'_key': 'asc'}))
        s = s[:100]
        response = s.execute()
        return render_template('games/advanced.html', response=response)


# GAME #################################################################################################################
# osvezavanje reviewovi nakon dodati RESI, resenje na kraj
# jos funkcija za igre, [ADD, EDIT] - ADMIN (nepotrebno za sad)
@bpg.route('/<title>', methods=['GET', 'POST'])
def view_game(title):
    sg = es.Game.search().query('term', title__raw=title)
    response = sg.execute()
    game = response.hits[0]

    a = es.A('avg', script='(doc[\'visuals\'].value + doc[\'gameplay\'].value'
                           ' + doc[\'difficulty\'].value + doc[\'narrative\'].value'
                           ' + doc[\'audio\'].value + doc[\'replayability\'].value'
                           ' + doc[\'enjoyment\'].value) / 7.0')
    sr = es.Review.search().query('match', game_id=game.title)
    sr.aggs.metric('average_score', a)

    page = 1
    page_size = 10
    if request.args.get('page'):
        page = int(request.args.get('page'))
    if request.args.get('page_size'):
        page_size = int(request.args.get('page_size'))

    sr = sr[page_size * (page - 1):page_size * page]
    response = sr.execute()
    total_pages = ceil(response.hits.total.value / page_size)
    reviews = response.hits
    score = response.aggs.average_score.value
    users = []
    if reviews:
        for review in reviews:
            users.append(review.user_id)
        return render_template('game.html', game=game, reviews=reviews, users=users, score=score, page=page,
                               page_size=page_size, total_pages=total_pages)
    else:
        return render_template('game.html', game=game)


@bpg.route('/<id>/add', methods=['POST'])
@login_required
def add_game_to_library(id):
    game = es.Game.get(id)
    user = g.user
    user.add_game(game.title)
    flash('Now following this game!')
    return redirect(url_for('game.view_game', title=game.title))


@bpg.route('/<id>/delete', methods=['POST'])
@login_required
def delete_game_from_library(id):
    game = es.Game.get(id)
    user = g.user
    user.delete_game(game.title)
    flash('No longer following this game!')
    return redirect(url_for('game.view_game', title=game.title))


# REVIEW ###############################################################################################################
@bpr.route('/<id>', methods=['GET'])
def view_review(id):
    review = get_review(id, False)
    return render_template('review.html', review=review, user=review.user_id, game=review.game_id)


@bpr.route('/<title>/create', methods=['GET', 'POST'])
@login_required
def create_review(title):
    if request.method == 'POST':
        rtitle = request.form['title']
        visuals = request.form['visuals']
        gameplay = request.form['gameplay']
        difficulty = request.form['difficulty']
        narrative = request.form['narrative']
        audio = request.form['audio']
        replayability = request.form['replayability']
        enjoyment = request.form['enjoyment']
        description = request.form['description']

        s = es.Review.search()
        s.query = Q('bool', must=[Q('match', user_id=g.user.username), Q('match', game_id=title)])
        s = s.source(False)
        response = s.execute()
        error = None

        if not rtitle:
            error = 'Review title is missing.'
        elif not visuals or not gameplay or not difficulty or not narrative or not audio or \
                not replayability or not enjoyment:
            error = 'Some review scoremarks are missing.'
        elif not description:
            error = 'Review description is missing.'
        elif response.hits.total.value > 0:
            error = 'You have already written review for this game.'

        if error is not None:
            flash(error)
        else:
            review = es.Review()
            review.title = rtitle
            review.visuals = visuals
            review.gameplay = gameplay
            review.difficulty = difficulty
            review.narrative = narrative
            review.audio = audio
            review.replayability = replayability
            review.enjoyment = enjoyment
            review.description = description
            review.game_id = title
            review.user_id = g.user.username
            review.save()

            flash('Review successfully added for the game ' + title + ' !')
            return redirect(url_for('index'))

    return render_template('reviews/create.html')


def get_review(id, check_author=True):
    review = None
    try:
        review = es.Review.get(id)
    except exceptions.NotFoundError:
        pass

    if review is None:
        abort(404, f'Post id {id} doesn\'t exist.')

    if check_author and review.user_id != g.user.username:
        abort(403)

    return review


@bpr.route('/<id>/update', methods=['GET', 'POST'])
@login_required
def update_review(id):
    review = get_review(id)

    if request.method == 'POST':
        title = request.form['title']
        visuals = request.form['visuals']
        gameplay = request.form['gameplay']
        difficulty = request.form['difficulty']
        narrative = request.form['narrative']
        audio = request.form['audio']
        replayability = request.form['replayability']
        enjoyment = request.form['enjoyment']
        description = request.form['description']

        error = None

        if not title:
            error = 'Review title is missing.'
        elif not visuals or not gameplay or not difficulty or not narrative or not audio or \
                not replayability or not enjoyment:
            error = 'Some review scoremarks are missing.'
        elif not description:
            error = 'Review description is missing.'

        if error is not None:
            flash(error)
        else:
            change = {'title': title,
                      'visuals': visuals,
                      'gameplay': gameplay,
                      'difficulty': difficulty,
                      'narrative': narrative,
                      'audio': audio,
                      'replayability': replayability,
                      'enjoyment': enjoyment,
                      'description': description}
            review.change(**change)
            flash('Review successfully updated!')
            return redirect(url_for('review.view_review', id=review.meta.id))

    return render_template('reviews/updater.html', review=review)


@bpr.route('/<id>/delete', methods=['POST'])
@login_required
def delete_review(id):
    review = get_review(id, True)
    review.delete()
    flash('Review successfully deleted!')
    return redirect(url_for('index'))


# USER #################################################################################################################
@bpu.route('/<username>', methods=['GET', 'POST'])
def view_user(username):
    s = es.User.search().query('term', username__raw=username)
    response = s.execute()
    user = response.hits[0]

    a = es.A('avg', script='(doc[\'visuals\'].value + doc[\'gameplay\'].value'
                           ' + doc[\'difficulty\'].value + doc[\'narrative\'].value'
                           ' + doc[\'audio\'].value + doc[\'replayability\'].value'
                           ' + doc[\'enjoyment\'].value) / 7.0')
    sr = es.Review.search().query('term', user_id__raw=user.username)
    sr.aggs.metric('average_score', a)

    page_game = 1
    page_size_game = 10
    page_review = 1
    page_size_review = 10
    if request.args.get('page_game'):
        page_game = int(request.args.get('page_game'))
    if request.args.get('page_size_game'):
        page_size_game = int(request.args.get('page_size_game'))
    if request.args.get('page_review'):
        page_review = int(request.args.get('page_review'))
    if request.args.get('page_size_review'):
        page_size_review = int(request.args.get('page_size_review'))

    sr = sr[page_size_review * (page_review - 1):page_size_review * page_review]
    response = sr.execute()
    total_pages_reviews = ceil(response.hits.total.value / page_size_review)
    reviews = response.hits
    score = response.aggs.average_score.value
    games = []
    total_pages_games = None
    if user.game_ids:
        sg = es.Game.search().query('terms', title__raw=user.game_ids)
        sg = sg.source(['title'])
        sg = sg[page_size_game * (page_game - 1):page_size_game * page_game]
        response = sg.execute()
        games = response.hits
        total_pages_games = ceil(len(games) / page_size_game)
    return render_template('user.html', user=user, games=games, reviews=reviews,
                           score=score, page_game=page_game, page_size_game=page_size_game,
                           total_pages_games=total_pages_games, page_review=page_review,
                           page_size_review=page_size_review, total_pages_reviews=total_pages_reviews)


@bpu.route('/<id>/update/<action>', methods=['POST'])
@login_required
def update_user(id, action):
    if id != g.user.meta.id:
        error = 'Can\'t change other user\'s info.'
        flash(error)
        return redirect(url_for('index'))

    if action == 'email':
        email_current = request.form['email_current']
        email_new = request.form['email_new']
        email_confirm = request.form['email_confirm']
        error = None
        user = g.user

        if email_current != g.user.email:
            error = 'Email is different from your current one.'
        elif email_current == email_new:
            error = 'Email is the same as your current one.'
        elif email_new != email_confirm:
            error = 'Email confirmation incorrect.'

        if error is not None:
            flash(error)
        else:
            user.change_email(email_new)
            flash('Email successfully updated!')

        return redirect(url_for('user.view_user', username=user.username))

    if action == 'password':
        password_current = request.form['password_current']
        password_new = request.form['password_new']
        password_confirm = request.form['password_confirm']
        error = None
        user = g.user

        if check_password_hash(g.user.password, password_current):
            error = 'Password is different from your current one.'
        elif password_current == password_new:
            error = 'Password is the same as your current one.'
        elif password_new != password_confirm:
            error = 'Password confirmation incorrect.'

        if error is not None:
            flash(error)
        else:
            user.change_password(generate_password_hash(password_new))
            flash('Password successfully updated!')

        return redirect(url_for('user.view_user', username=user.username))


@bpu.route('/<id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    if id != g.user.meta.id:
        error = 'Can\'t delete other users.'
        flash(error)
        return redirect(url_for('index'))

    user = g.user
    user.delete_reviews()
    user.delete()
    session.clear()
    flash('Account, along with all user written reviews, successfully deleted!')
    return redirect(url_for('index'))


@bpu.route('/<id>/watch', methods=['POST'])
@login_required
def watch_words(id):
    if id != g.user.meta.id:
        error = 'Can\'t access this.'
        flash(error)
        return redirect(url_for('index'))

    word = request.form['word']
    s = es.Game.search().query('match', description=word)
    response = s.execute()
    current = response.hits.total.value
    client = es.Elasticsearch()
    id = g.user.username + 'watcher'
    body = {
        'metadata': {
            'current': current
        },
        'trigger': {
            'schedule': {
                'daily': {'at': 'noon'}
            }
        },
        'input': {
            'search': {
                'request': {
                    'indices': ['games'],
                    'body': {
                        'query': {
                            'match': {'description': word}
                        }
                    }
                }
            }
        },
        'condition': {
            'script': {
                'source': 'return ctx.payload.hits.total > ctx.metadata.current'
            }
        },
        'actions': {
            'send_email': {
                'email': {
                    'to': g.user.email,
                    'subject': 'New game added with followed words',
                    'body': 'You are hereby informed that new game with the words you are following ('
                            + word + ') has been added!'
                }
            }
        }
    }

    client.watcher.put_watch(id, body=body)
    # __init__.scheduler.add_job(func=update_watcher(id, word), trigger="interval", hours=23, minutes=59)
    flash('Now following word(s) "' + word + '"!')
    return redirect(url_for('index'))


def update_watcher(id, word):
    client = es.Elasticsearch()
    watch = client.watcher.get_watch(id)
    s = es.Game.search().query('match', description=word)
    response = s.execute()
    current = response.hits.total.value
    body = {
        'metadata': {
            'current': current},
        'trigger': watch['watch']['trigger'],
        'input': watch['watch']['input'],
        'condition': watch['watch']['condition'],
        'actions': watch['watch']['actions']}
    client.watcher.put_watch(id, body)
