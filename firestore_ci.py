from copy import deepcopy, copy
from typing import TypeVar, Optional, Set, Union, Type, List, Dict, Iterable

from google.cloud.firestore import Client, CollectionReference, Query, DocumentSnapshot

# Need environment variable GOOGLE_APPLICATION_CREDENTIALS set to path of the the service account key (json file)
_DB = Client()
# All models imported from FirestoreDocument are of type FirestoreDocChild
_FirestoreDocChild = TypeVar('_FirestoreDocChild', bound='FirestoreDocument')
# Used to map collection to model
_REFERENCE: Dict[str, callable] = dict()


class FirestoreCIError(Exception):

    def __init__(self, message):
        super().__init__(message)


class _Query:
    LESS_THAN = '<'
    LESS_THAN_OR_EQUAL = '<='
    EQUAL = '=='
    GREATER_THAN_OR_EQUAL = '>='
    GREATER_THAN = '>'
    ARRAY_CONTAINS = 'array_contains'
    IN = 'in'
    ARRAY_CONTAINS_ANY = 'array_contains_any'
    _COMPARISON_OPERATORS = {LESS_THAN, LESS_THAN_OR_EQUAL, EQUAL, GREATER_THAN_OR_EQUAL, GREATER_THAN, ARRAY_CONTAINS,
                             IN, ARRAY_CONTAINS_ANY}
    ORDER_ASCENDING = Query.ASCENDING
    ORDER_DESCENDING = Query.DESCENDING
    _DIRECTION = {ORDER_ASCENDING, ORDER_DESCENDING}

    def __init__(self):
        self._doc_class: Optional[Type[_FirestoreDocChild]] = None
        self._doc_ref: Optional[CollectionReference] = None
        self._query_ref: Optional[Union[Query, CollectionReference]] = None
        self._doc_fields: Set = set()
        self._cascade: bool = False

    def set_document(self, document_class: Type[_FirestoreDocChild]) -> None:
        self._doc_class = document_class
        self._doc_fields = set(document_class().doc_to_dict())
        self._doc_ref: CollectionReference = _DB.collection(self._doc_class.COLLECTION)
        self._cascade = False

    def _get_object_manager(self) -> '_Query':
        if self._query_ref is None:
            object_manager = copy(self)
            object_manager._query_ref = self._doc_ref
            return object_manager
        return self

    def filter_by(self, **kwargs) -> '_Query':
        object_manager = self._get_object_manager()
        for field_name, field_value in kwargs.items():
            if field_name in self._doc_fields:
                object_manager._query_ref = object_manager._query_ref.where(field_name, '==', field_value)
            else:
                raise FirestoreCIError('filter_by method has invalid field.')
        return object_manager

    def filter(self, field_name: str, condition: str, field_value: object) -> '_Query':
        object_manager = self._get_object_manager()
        if field_name not in self._doc_fields:
            raise FirestoreCIError('filter method has invalid field.')
        if condition not in self._COMPARISON_OPERATORS:
            raise FirestoreCIError('filter method has invalid condition.')
        object_manager._query_ref = object_manager._query_ref.where(field_name, condition, field_value)
        return object_manager

    def order_by(self, field_name: str, direction: str = ORDER_ASCENDING) -> '_Query':
        object_manager = self._get_object_manager()
        if field_name not in self._doc_fields:
            raise FirestoreCIError('order_by method has invalid field.')
        if direction not in self._DIRECTION:
            raise FirestoreCIError('order_by has invalid direction.')
        object_manager._query_ref = object_manager._query_ref.order_by(field_name, direction=direction)
        return object_manager

    def limit(self, count: int) -> '_Query':
        object_manager = self._get_object_manager()
        object_manager._query_ref = object_manager._query_ref.limit(count) if count > 0 \
            else object_manager._query_ref.limit(0)
        return object_manager

    @property
    def cascade(self) -> '_Query':
        object_manager = self._get_object_manager()
        object_manager._cascade = True
        return object_manager

    def get(self) -> List[_FirestoreDocChild]:
        query_ref = self._doc_ref if self._query_ref is None else self._query_ref
        docs: Iterable[DocumentSnapshot] = query_ref.stream()
        documents: List = [self._doc_class.dict_to_doc(doc.to_dict(), doc.id, cascade=self._cascade) for doc in docs]
        return documents

    def first(self) -> Optional[_FirestoreDocChild]:
        query_ref = self._doc_ref if self._query_ref is None else self._query_ref
        doc: DocumentSnapshot = next((query_ref.limit(1).stream()), None)
        document = self._doc_class.dict_to_doc(doc.to_dict(), doc.id, cascade=self._cascade) if doc else None
        return document

    def delete(self) -> str:
        query_ref = self._doc_ref if self._query_ref is None else self._query_ref
        docs: Iterable[DocumentSnapshot] = query_ref.stream()
        documents: List = [self._doc_class.dict_to_doc(doc.to_dict(), doc.id, cascade=self._cascade) for doc in docs]
        results = [document.delete(cascade=self._cascade) for document in documents]
        if results and all(result != str() for result in results):
            return results[-1]
        else:
            return str()


class FirestoreDocument:
    COLLECTION: Optional[str] = None  # Collection should be initialize by the child class call to init.
    objects: _Query = None

    @classmethod
    def init(cls, collection: Optional[str] = None):
        cls.COLLECTION = collection if collection else f"{cls.__name__.lower()}s"
        cls.objects = _Query()
        cls.objects.set_document(cls)
        _REFERENCE[cls.COLLECTION] = cls

    def __init__(self):
        self._doc_id: Optional[str] = None  # This tracks the document id of the collection.

    def __repr__(self) -> str:
        return f"/{self.COLLECTION}/{self._doc_id}"

    def __eq__(self, other) -> bool:
        return self.id == other.id

    @property
    def id(self) -> str:
        return self._doc_id

    def set_id(self, doc_id: str) -> None:
        self._doc_id = doc_id

    def doc_to_dict(self) -> dict:
        doc_dict = deepcopy(self.__dict__)
        del doc_dict['_doc_id']
        return doc_dict

    @classmethod
    def dict_to_doc(cls, doc_dict: dict, doc_id: Optional[str] = None, cascade: bool = False) -> _FirestoreDocChild:
        document = cls()
        if doc_id:
            document.set_id(doc_id)
        for field, value in doc_dict.items():
            if field not in document.__dict__:
                continue
            if not cascade or not cls._eligible_for_cascade(field, value):
                setattr(document, field, value)
                continue
            values = value if isinstance(value, list) else [value]
            if isinstance(values[0], dict):
                firestore_document_list = [_REFERENCE[field].dict_to_doc(value_dict, cascade=True)
                                           for value_dict in values]
            else:
                firestore_document_list = [_REFERENCE[field].get_by_id(nested_id, cascade=True) for nested_id in values]
            setattr(document, field, firestore_document_list)
        return document

    def cascade_to_dict(self) -> dict:
        document_copy = deepcopy(self)
        documents = document_copy._get_nested_documents()
        for field, doc_list in documents.items():
            document_list: List[dict] = [document.cascade_to_dict() for document in doc_list]
            if any(doc_dict == dict() for doc_dict in document_list):
                return dict()
            setattr(document_copy, field, document_list)
        doc_dict = document_copy.__dict__
        doc_dict['id'] = doc_dict['_doc_id']
        del doc_dict['_doc_id']
        return doc_dict

    @staticmethod
    def _eligible_for_cascade(field, value) -> bool:
        if field not in _REFERENCE:
            return False
        if isinstance(value, dict):
            return True
        if not isinstance(value, list):
            return False
        first_object = next(iter(value), None)
        if isinstance(first_object, dict) or isinstance(first_object, str):
            return True
        return False

    @classmethod
    def create_from_dict(cls, doc_dict: dict) -> _FirestoreDocChild:
        document = cls.dict_to_doc(doc_dict, cascade=True)
        document.create()
        return document

    def create(self) -> str:
        document = deepcopy(self)
        documents = self._get_nested_documents()
        for field, doc_list in documents.items():
            ids: List[str] = [document.create() for document in doc_list]
            setattr(document, field, ids)
        doc = _DB.collection(document.COLLECTION).add(document.doc_to_dict())
        self.set_id(doc[1].id)
        return doc[1].id

    def save(self, cascade: bool = False) -> bool:
        if not self._doc_id:
            return False
        document_copy = deepcopy(self)
        documents = document_copy._get_nested_documents()
        for field, doc_list in documents.items():
            if cascade:
                if any(document.save(cascade=True) is False for document in doc_list):
                    return False
            elif any(document.id is None for document in doc_list):
                return False
            ids: List[str] = [document.id for document in doc_list]
            setattr(document_copy, field, ids)
        _DB.collection(self.COLLECTION).document(self._doc_id).set(document_copy.doc_to_dict())
        return True

    def delete(self, cascade: bool = False) -> str:
        if not self._doc_id:
            return str()
        documents = self._get_nested_documents()
        if cascade:
            if any(doc.delete(cascade=True) == str() for _, doc_list in documents.items() for doc in doc_list):
                return str()
        elif documents and any(document.id is None for _, doc_list in documents.items() for document in doc_list):
            return str()
        _DB.collection(self.COLLECTION).document(self._doc_id).delete()
        doc_id = self._doc_id
        self._doc_id = None
        return doc_id

    def _get_nested_documents(self) -> Dict[str, List[_FirestoreDocChild]]:
        return {field: [doc for doc in value_list if isinstance(doc, FirestoreDocument)]
                for field, value_list in self.__dict__.items()
                if isinstance(value_list, list) and any(isinstance(doc, FirestoreDocument) for doc in value_list)}

    @classmethod
    def get_by_id(cls, doc_id: str, cascade: bool = False) -> Optional[_FirestoreDocChild]:
        doc: DocumentSnapshot = _DB.collection(cls.COLLECTION).document(doc_id).get()
        return cls.dict_to_doc(doc.to_dict(), doc.id, cascade=cascade) if doc.exists else None
