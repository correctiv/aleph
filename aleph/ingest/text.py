import logging

from aleph.core import get_archive
from aleph.model import db, Document, DocumentPage
from aleph.ingest.pdf import extract_pdf
from aleph.ingest.ingestor import Ingestor

log = logging.getLogger(__name__)


class TextIngestor(Ingestor):
    DOCUMENT_TYPE = Document.TYPE_TEXT

    def create_document(self, meta, type=None):
        document = super(TextIngestor, self).create_document(meta, type=type)
        document.delete_pages()
        return document

    def create_page(self, document, text, number=1):
        page = DocumentPage()
        page.document_id = document.id
        page.text = text
        page.number = number
        db.session.add(page)
        return page

    def extract_pdf(self, meta, pdf_path):
        data = extract_pdf(pdf_path, languages=meta.languages)
        if not meta.has('author') and data.get('author'):
            meta.author = data.get('author')

        # if not meta.has('title') and data.get('title'):
        #     meta.title = data.get('title')

        document = self.create_document(meta)
        for i, page in enumerate(data['pages']):
            self.create_page(document, page, number=i + 1)
        self.emit(document)

    def store_pdf(self, meta, pdf_path):
        get_archive().archive_file(pdf_path, meta.pdf, move=False)


class PDFIngestor(TextIngestor):
    MIME_TYPES = ['application/pdf']
    EXTENSIONS = ['pdf']

    def ingest(self, meta, local_path):
        self.extract_pdf(meta, local_path)

    @classmethod
    def match(cls, meta, local_path):
        with open(local_path, 'r') as fh:
            if '%PDF-1.' in fh.read(1024):
                return 15
        return -1
