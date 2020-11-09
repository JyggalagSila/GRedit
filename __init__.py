from flask import Flask
# import atexit
# from apscheduler.schedulers.background import BackgroundScheduler


# scheduler = BackgroundScheduler()


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(SECRET_KEY='BLUEBELLSAMA')

    from . import auth
    app.register_blueprint(auth.bp)

    from . import gamereview
    app.register_blueprint(gamereview.bp)
    app.register_blueprint(gamereview.bpg)
    app.register_blueprint(gamereview.bpr)
    app.register_blueprint(gamereview.bpu)
    app.add_url_rule('/', endpoint='index')

    # scheduler.start()
    # atexit.register(lambda: scheduler.shutdown())

    @app.route('/hello')
    def hello():
        return 'Hello, World!'

    return app
