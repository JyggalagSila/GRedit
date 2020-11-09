from elasticsearch import *
from elasticsearch_dsl import *
from elasticsearch_dsl.aggs import *
from datetime import datetime

connections.create_connection(hosts=['localhost'], timeout=60)

# dodaj sinonimi na kraj
gr_analyzer = analyzer('gr_analyzer',
                       tokenizer='standard',
                       filter=['lowercase', 'trim', 'stemmer'],
                       char_filter=['html_strip'])


class Game(Document):
    title = Text(analyzer='standard', fields={'raw': Keyword()}, required=True)
    # suggest, complete, search-as-you-type: title
    description = Text(analyzer=gr_analyzer, required=True)
    release_date = Date(required=True)
    developer = Text(fields={'raw': Keyword()}, required=True)
    publisher = Text(fields={'raw': Keyword()}, required=True)
    tags = Text(analyzer='standard', fields={'raw': Keyword(multi=True)}, multi=True, required=True)

    class Index:
        name = 'games'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 2,
        }

    def add_tags(self, *tags):
        tags = list(tags)
        ubq = UpdateByQuery(index='games').query('term', title__raw=self.title)
        ubq = ubq.script(
            source='''
            if (ctx._source.tags == null)
            { ctx._source.tags = params.tags}
            else { for (tag in params.tags)
            {if (!ctx._source.tags.contains(tag))
            { ctx._source.tags.add(tag)}}}
            ''',
            lang='painless',
            params={
                'tags': tags
            }
        )

        return ubq.execute()

    def delete_tags(self, *tags):
        tags = list(tags)
        ubq = UpdateByQuery(index='games').query('term', title__raw=self.title)
        ubq = ubq.script(
            source='''
            for (tag in params.tag) {
            if (ctx._source.tags.contains(tag))
            { ctx._source.tags.remove(ctx._source.tags.indexOf(tag))}}
            if (ctx._source.tags == []) {ctx._source.remove('tags')}
            ''',
            lang='painless',
            params={
                'tag': tags
            }
        )

        return ubq.execute()


class Review(Document):
    title = Text(fields={'raw': Keyword()}, required=True)
    description = Text(analyzer=gr_analyzer, required=True)
    visuals = Integer(required=True)
    gameplay = Integer(required=True)
    difficulty = Integer(required=True)
    narrative = Integer(required=True)
    audio = Integer(required=True)
    replayability = Integer(required=True)
    enjoyment = Integer(required=True)

    game_id = Text(fields={'raw': Keyword()}, required=True)  # title
    user_id = Text(fields={'raw': Keyword()}, required=True)  # username

    date_posted = Date(required=True)
    last_modified = Date()

    class Index:
        name = 'reviews'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 2
        }

    def age(self):
        return datetime.now() - self.date_posted

    def total(self):
        return (self.visuals + self.gameplay + self.difficulty + self.narrative +
                self.audio + self.replayability + self.enjoyment) / 7

    def change(self, **kwargs):
        return super().update(index='reviews', last_modified=datetime.now(), **kwargs)

    def save(self, **kwargs):
        self.date_posted = datetime.now()
        return super().save(**kwargs)


class User(Document):
    username = Text(fields={'raw': Keyword()}, required=True)
    email = Text(fields={'raw': Keyword()}, required=True)
    password = Text(fields={'raw': Keyword()}, required=True)
    game_ids = Text(fields={'raw': Keyword()}, multi=True)
    registration_date = Date(required=True)

    class Index:
        name = 'users'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 2,
        }

    def change_email(self, email):
        return super().update(index='users', email=email)

    def change_password(self, password):
        return super().update(index='users', password=password)

    def save(self, **kwargs):
        self.registration_date = datetime.now()
        return super().save(**kwargs)

    def add_game(self, game):
        ubq = UpdateByQuery(index='users').query('term', username__raw=self.username)
        ubq = ubq.script(
            source='''
            if (ctx._source.game_ids == null)
            { ctx._source.game_ids = [params.game]}
            else { if (!ctx._source.game_ids.contains(params.game))
            { ctx._source.game_ids.add(params.game)}}
            ''',
            lang='painless',
            params={
                'game': game
            }
        )

        return ubq.execute()

    def delete_game(self, game):
        ubq = UpdateByQuery(index='users').query('term', username__raw=self.username)
        ubq = ubq.script(
            source='''
            if (ctx._source.game_ids.contains(params.game)) 
            { ctx._source.game_ids.remove(ctx._source.game_ids.indexOf(params.game)) }
            if (ctx._source.game_ids == []) {ctx._source.remove('game_ids')}     
            ''',
            lang='painless',
            params={
                'game': game
            }
        )

        return ubq.execute()

    def delete_reviews(self):
        ubq = UpdateByQuery(index='reviews').query('term', user_id__raw=self.username)
        ubq = ubq.script(
            source='ctx.op = "delete"',
            lang='painless'
        )

        return ubq.execute()

# Game.init()
# Review.init()
# User.init()
