import os
import yaml
import logging
import unicodecsv
from sqlalchemy import create_engine
from sqlalchemy import MetaData, select
from sqlalchemy.schema import Table

from aleph.core import db
from aleph.model import Collection
from aleph.ingest import ingest_file
from aleph.crawlers.crawler import Crawler
from aleph.util import make_tempfile, remove_tempfile

log = logging.getLogger(__name__)


class SQLQuery(object):

    def __init__(self, engine, config):
        self.config = config
        self.meta = MetaData()
        self.meta.bind = engine

    @property
    def tables(self):
        if not hasattr(self, '_tables'):
            self._tables = []
            table_names = []
            if 'table' in self.config:
                table_names.append(self.config.get('table'))
            if 'tables' in self.config:
                table_names.extend(self.config.get('tables'))
            for table_name in table_names:
                table = Table(table_name, self.meta, autoload=True)
                self._tables.append(table)
        return self._tables

    @property
    def columns(self):
        skip = [self.column(s) for s in self.config.get('skip', [])]
        columns = [self.column(c) for c in self.config.get('columns', [])]
        if not len(columns):
            for table in self.tables:
                for column in table.columns:
                    if column in skip:
                        continue
                    columns.append(column)
        return columns

    def alias(self, col):
        if len(self.tables) > 1:
            return '%s.%s' % (col.table.name, col.name)
        return col.name

    def label(self, col):
        return col.label(self.alias(col))

    def column(self, name):
        table_name, column_name = None, name
        if '.' in name:
            table_name, column_name = name.split('.', 1)
        column = None
        for table in self.tables:
            if table_name is not None and table_name != table.name:
                continue
            for col in table.columns:
                if col.name != column_name:
                    continue
                if column is not None:
                    raise TypeError("Ambiguous column: %s" % name)
                column = col
        if column is None:
            raise AttributeError("No such column: %s" % name)
        return column

    @property
    def filters(self):
        for col, val in self.config.get('filters', {}).items():
            yield self.label(self.column(col)), val
        for join in self.config.get('joins', []):
            left = self.label(self.column(join.get('left')))
            right = self.label(self.column(join.get('right')))
            yield left, right

    @property
    def query(self):
        columns = [self.label(c) for c in self.columns]
        q = select(columns=columns, from_obj=self.tables)
        for col, val in self.filters:
            q = q.where(col == val)
        return q


class SQLCrawler(Crawler):

    name = 'sql'

    def crawl_query(self, engine, collection, meta_base, name, query):
        meta_ = meta_base.copy()
        meta_.update(query.get('meta', {}))
        meta = self.make_meta(meta_)
        meta.mime_type = 'text/csv'
        meta.foreign_id = '%s:%s' % (collection.foreign_id, name)

        query = SQLQuery(engine, query)

        file_path = make_tempfile(name=name, suffix='.csv')
        try:
            with open(file_path, 'w') as fh:
                headers = [query.alias(c) for c in query.columns]
                writer = unicodecsv.writer(fh, quoting=unicodecsv.QUOTE_ALL)
                writer.writerow(headers)
                log.info('Query: %s', query.query)
                rp = engine.execute(query.query)
                while True:
                    rows = rp.fetchmany(10000)
                    if not rows:
                        break
                    for row in rows:
                        writer.writerow(row[h] for h in headers)
            ingest_file(collection.id, meta, file_path, move=True)
        finally:
            remove_tempfile(file_path)

    def crawl_collection(self, engine, foreign_id, data):
        collection = Collection.create({
            'foreign_id': foreign_id,
            'label': data.get('label')
        })
        db.session.commit()
        meta_base = data.get('meta', {})
        for name, query in data.get('queries', {}).items():
            self.crawl_query(engine, collection, meta_base, name, query)

    def crawl(self, config=None):
        with open(config, 'rb') as fh:
            config = yaml.load(fh)
            engine_url = os.path.expandvars(config.get('url'))
            engine = create_engine(engine_url)
            for name, data in config.get('collections', {}).items():
                foreign_id = '%s:%s' % (self.name, name)
                self.crawl_collection(engine, foreign_id, data)
