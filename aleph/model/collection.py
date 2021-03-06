import logging
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import aliased

from aleph.core import db, url_for
from aleph.model.role import Role
from aleph.model.schema_model import SchemaModel
from aleph.model.permission import Permission
from aleph.model.common import SoftDeleteModel, IdModel, make_token

log = logging.getLogger(__name__)


class Collection(db.Model, IdModel, SoftDeleteModel, SchemaModel):
    _schema = 'collection.json#'

    CATEGORIES = {
        'news': 'News archives',
        'leak': 'Leaks',
        'gazette': 'Gazettes',
        'court': 'Court archives',
        'company': 'Company registries',
        'watchlist': 'Watchlists',
        'investigation': 'User collections',
        'sanctions': 'Sanctions lists',
        'scrape': 'Scrapes',
        'procurement': 'Procurement',
        'grey': 'Grey literature'
    }

    label = db.Column(db.Unicode)
    category = db.Column(db.Unicode, nullable=True)
    foreign_id = db.Column(db.Unicode, unique=True, nullable=False)

    # managed collections are generated by API bots and thus UI users
    # shouldn't be encouraged to add entities or documents to them.
    managed = db.Column(db.Boolean, default=False)
    # Private collections don't show up in peek queries.
    private = db.Column(db.Boolean, default=False)
    generate_entities = db.Column(db.Boolean, nullable=True, default=False)

    creator_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True)
    creator = db.relationship(Role)

    def update(self, data):
        creator_id = data.get('creator_id')
        if creator_id is not None and creator_id != self.creator_id:
            role = Role.by_id(creator_id)
            if role is not None and role.type == Role.USER:
                self.creator_id = role.id
                Permission.grant_collection(self.id, role, True, True)
        self.schema_update(data)

    def touch(self):
        self.updated_at = datetime.utcnow()
        db.session.add(self)

    def pending_entities(self):
        """Generate a ranked list of the most commonly used pending entities.

        This is used for entity review.
        """
        from aleph.model.entity import Entity, collection_entity_table
        from aleph.model.document import collection_document_table
        from aleph.model.reference import Reference
        cet = aliased(collection_entity_table)
        cdt = aliased(collection_document_table)
        q = db.session.query(Entity)
        q = q.filter(Entity.state == Entity.STATE_PENDING)
        q = q.join(Reference, Reference.entity_id == Entity.id)
        q = q.join(cet, cet.c.entity_id == Entity.id)
        q = q.join(cdt, cdt.c.document_id == Reference.document_id)
        q = q.filter(cet.c.collection_id == self.id)
        q = q.filter(cdt.c.collection_id == self.id)
        q = q.group_by(Entity)
        return q.order_by(func.count(Reference.id).desc())

    def get_document_count(self):
        from aleph.model.document import Document, collection_document_table
        q = Document.all()
        q = q.join(collection_document_table)
        q = q.filter(collection_document_table.c.collection_id == self.id)
        return q.count()

    def get_entity_count(self, state=None):
        from aleph.model.entity import Entity, collection_entity_table
        q = Entity.all()
        q = q.join(collection_entity_table)
        q = q.filter(collection_entity_table.c.collection_id == self.id)
        if state is not None:
            q = q.filter(Entity.state == state)
        return q.count()

    def content_statistics(self):
        """Query how many enitites and documents are in this collection."""
        from aleph.model.entity import Entity
        return {
            'doc_count': self.get_document_count(),
            'entity_count': self.get_entity_count(Entity.STATE_ACTIVE),
            'pending_count': self.get_entity_count(Entity.STATE_PENDING)
        }

    @classmethod
    def by_foreign_id(cls, foreign_id, deleted=False):
        if foreign_id is None:
            return
        q = cls.all(deleted=deleted)
        return q.filter(cls.foreign_id == foreign_id).first()

    @classmethod
    def create(cls, data, role=None):
        foreign_id = data.get('foreign_id') or make_token()
        collection = cls.by_foreign_id(foreign_id, deleted=True)
        if collection is None:
            collection = cls()
            collection.foreign_id = foreign_id
            collection.creator = role
            collection.update(data)
            db.session.add(collection)
            db.session.flush()

            if role is not None:
                Permission.grant_collection(collection.id,
                                            role, True, True)
        collection.deleted_at = None
        return collection

    # @classmethod
    # def category_statistics(cls, collection_ids):
    #     q = db.session.query(Collection.category, func.count(Collection.id))
    #     q = q.filter(Collection.deleted_at == None)  # noqa
    #     q = q.filter(Collection.id.in_(collection_ids))
    #     q = q.group_by(Collection.category)
    #     q = q.order_by(func.count(Collection.id).desc())
    #     results = []
    #     for category, count in q.all():
    #         results.append({'category': category, 'count': count})
    #     return results

    def __repr__(self):
        return '<Collection(%r, %r)>' % (self.id, self.label)

    def __unicode__(self):
        return self.label

    def to_dict(self):
        data = super(Collection, self).to_dict()
        try:
            from aleph.authz import collection_public
            data['public'] = collection_public(self)
        except:
            pass
        data['api_url'] = url_for('collections_api.view', id=self.id)
        data['foreign_id'] = self.foreign_id
        data['creator_id'] = self.creator_id
        return data
