import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy, copy
from operator import itemgetter
from typing import TypeVar, Optional, Union, Type, List, Dict, Iterable, Callable

from google.cloud.firestore import Client, CollectionReference, Query, DocumentSnapshot, FieldFilter


class FirestoreCIError(Exception):

    def __init__(self, message):
        super().__init__(message)


if "FIRESTORE_EMULATOR_PROJECT_ID" in os.environ:
    _DB = Client(project=os.getenv("FIRESTORE_EMULATOR_PROJECT_ID"))    # noqa
elif "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    _DB = Client()
else:
    raise FirestoreCIError("Need either FIRESTORE_EMULATOR_PROJECT_ID or GOOGLE_APPLICATION_CREDENTIALS setup as environment variables.")

# All models imported from FirestoreDocument are of type FirestoreDocChild
# noinspection PyTypeChecker
_FirestoreDocChild = TypeVar("_FirestoreDocChild", bound="FirestoreDocument")
# Used to map a collection to model
_REFERENCE: Dict[str, callable] = dict()


class FirestoreQuery:
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "=="
    GREATER_THAN_OR_EQUAL = ">="
    GREATER_THAN = ">"
    ARRAY_CONTAINS = "array_contains"
    IN = "in"
    ARRAY_CONTAINS_ANY = "array_contains_any"
    _COMPARISON_OPERATORS = {LESS_THAN, LESS_THAN_OR_EQUAL, EQUAL, GREATER_THAN_OR_EQUAL, GREATER_THAN, ARRAY_CONTAINS,
                             IN, ARRAY_CONTAINS_ANY}
    ORDER_ASCENDING = Query.ASCENDING
    ORDER_DESCENDING = Query.DESCENDING
    _DIRECTION = {ORDER_ASCENDING, ORDER_DESCENDING}

    def __init__(self):
        self._doc_class: Optional[Type[_FirestoreDocChild]] = None
        self._doc_ref: Optional[CollectionReference] = None
        self._query_ref: Optional[Union[Query, CollectionReference]] = None
        self._doc_fields: Dict = dict()
        self._cascade: bool = False
        self._truncate: bool = False
        self._no_orm: bool = False

    def set_document(self, document_class: Type[_FirestoreDocChild]) -> None:
        self._doc_class = document_class
        self._doc_fields = deepcopy(document_class().__dict__)
        del self._doc_fields["_doc_id"]
        self._doc_ref: CollectionReference = _DB.collection(self._doc_class.COLLECTION)
        self._cascade = False
        self._truncate: bool = False
        self._no_orm: bool = False

    def _get_object_manager(self) -> "FirestoreQuery":
        if self._query_ref is None:
            object_manager = copy(self)
            object_manager._query_ref = self._doc_ref
            return object_manager
        return copy(self)

    @staticmethod
    def _ordered_thread(func_to_execute: Callable, item: Union["FirestoreDocument", dict], index: int):
        return func_to_execute(item), index

    def _ordered_threads(self, item_list: list, workers: int, func_to_execute: Callable) -> list:
        if not item_list:
            return list()
        workers = len(item_list) if workers == 0 else workers
        ordered_list = [(item, index) for index, item in enumerate(item_list)]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            threads = {executor.submit(self._ordered_thread, func_to_execute, item, index)
                       for item, index in ordered_list}
            results = [future.result() for future in as_completed(threads)]
        results.sort(key=itemgetter(1))
        results = [result for result, _ in results]
        return results

    def _sanitize_doc_dict(self, doc_dict: dict):
        filtered_dict = {field: value for field, value in doc_dict.items() if field in self._doc_fields}
        if self._truncate:
            sanitized_dict = {field: value for field, value in filtered_dict.items()
                              if value != self._doc_fields[field]}
        else:
            sanitized_dict = deepcopy(self._doc_fields)
            for field, value in filtered_dict.items():
                sanitized_dict[field] = value
        return sanitized_dict

    @property
    def cascade(self) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        object_manager._cascade = True
        return object_manager

    @property
    def truncate(self) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        object_manager._truncate = True
        return object_manager

    @property
    def no_orm(self) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        object_manager._no_orm = True
        return object_manager

    def to_dicts(self, documents: List[_FirestoreDocChild]) -> List[dict]:
        dict_list = list()
        for document in documents:
            doc_dict = deepcopy(document.__dict__)
            if self._truncate:
                doc_dict = {field: value for field, value in doc_dict.items()
                            if field in self._doc_fields and value != self._doc_fields[field]}
            doc_dict["id"] = document.id
            doc_dict.pop("_doc_id", None)
            dict_list.append(doc_dict)
        return dict_list

    def from_dicts(self, doc_dicts: List[dict]) -> List[_FirestoreDocChild]:
        doc_list = list()
        for doc_dict in doc_dicts:
            doc: _FirestoreDocChild = self._doc_class()
            for field, value in doc_dict.items():
                if field not in doc.__dict__:
                    continue
                setattr(doc, field, value)
            doc_list.append(doc)
        return doc_list

    def filter_by(self, **kwargs) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        for field_name, field_value in kwargs.items():
            if field_name in self._doc_fields:
                object_manager._query_ref = object_manager._query_ref.where(filter=FieldFilter(field_name, "==", field_value))
            else:
                raise FirestoreCIError("filter_by method has invalid field.")
        return object_manager

    def filter(self, field_name: str, condition: str, field_value: object) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        if field_name not in self._doc_fields:
            if "." not in field_name:
                raise FirestoreCIError("filter method has invalid field.")
            field = field_name.split(".")[0]
            sub_field = field_name.split(".")[1]
            if field not in self._doc_fields or not isinstance(self._doc_fields[field], dict) or sub_field not in self._doc_fields[field]:
                raise FirestoreCIError("filter method has invalid mapped field.")
        if condition not in self._COMPARISON_OPERATORS:
            raise FirestoreCIError("filter method has invalid condition.")
        object_manager._query_ref = object_manager._query_ref.where(filter=FieldFilter(field_name, condition, field_value))
        return object_manager

    def order_by(self, field_name: str, direction: str = ORDER_ASCENDING) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        if field_name not in self._doc_fields:
            raise FirestoreCIError("order_by method has invalid field.")
        if direction not in self._DIRECTION:
            raise FirestoreCIError("order_by has invalid direction.")
        object_manager._query_ref = object_manager._query_ref.order_by(field_name, direction=direction)
        return object_manager

    def limit(self, count: int) -> "FirestoreQuery":
        object_manager = self._get_object_manager()
        object_manager._query_ref = object_manager._query_ref.limit(count) if count > 0 \
            else object_manager._query_ref.limit(0)
        return object_manager

    def create(self, doc_dict: dict) -> Union[_FirestoreDocChild, dict]:
        input_dict = self._sanitize_doc_dict(doc_dict)
        _, doc_ref = self._doc_ref.add(input_dict)
        if self._no_orm:
            input_dict["id"] = doc_ref.id
            return input_dict
        created_doc: _FirestoreDocChild = self.from_dicts([input_dict])[0]
        created_doc.set_id(doc_ref.id)
        return created_doc

    def create_all(self, doc_dict_list: List[dict], workers: int = 0) -> List[Union[_FirestoreDocChild, dict]]:
        results = self._ordered_threads(doc_dict_list, workers, self.create)
        return results

    def get(self) -> List[Union[_FirestoreDocChild, dict]]:
        query_ref = self._doc_ref if self._query_ref is None else self._query_ref
        docs: Iterable[DocumentSnapshot] = query_ref.stream()
        if self._no_orm:
            documents = list()
            for doc in docs:
                doc_dict = doc.to_dict()
                doc_dict["id"] = doc.id
                documents.append(doc_dict)
        else:
            documents = [self._doc_class.dict_to_doc(doc.to_dict(), doc.id, cascade=self._cascade) for doc in docs]
        return documents

    def first(self) -> Optional[Union[_FirestoreDocChild, dict]]:
        query_ref = self._doc_ref if self._query_ref is None else self._query_ref
        doc: DocumentSnapshot = next((query_ref.limit(1).stream()), None)
        if not doc:
            return None
        if self._no_orm:
            doc_dict = doc.to_dict()
            doc_dict["id"] = doc.id
            return doc_dict
        document = self._doc_class.dict_to_doc(doc.to_dict(), doc.id, cascade=self._cascade)
        return document

    def save(self, input: Union[_FirestoreDocChild, dict]) -> Union[dict, Optional[_FirestoreDocChild]]:
        if isinstance(input, dict):
            if "id" not in input:
                return None
            doc_id = input["id"]
            doc_dict = self._sanitize_doc_dict(input)
            doc = self.from_dicts([doc_dict])[0]
        else:
            if not input.id:
                return None
            doc = input
            doc_id = doc.id
            doc_dict = self.to_dicts([doc])[0]
        doc_dict.pop("id", None)
        self._doc_ref.document(doc_id).set(doc_dict)
        doc_dict["id"] = doc_id
        return doc_dict if self._no_orm else doc

    def save_all(self, doc_list: List[Union[_FirestoreDocChild, dict]],
                 workers: int = 0) -> List[Union[dict, _FirestoreDocChild]]:
        if not all(("id" in doc and doc["id"]) if isinstance(doc, dict) else doc.id for doc in doc_list):
            return list()
        results = self._ordered_threads(doc_list, workers, self.save)
        return results

    @staticmethod
    def _delete_in_thread(document: "FirestoreDocument", cascade: bool):
        return document.delete(cascade)

    def delete(self, workers: int = 0) -> str:
        query_ref = self._doc_ref if self._query_ref is None else self._query_ref
        docs: Iterable[DocumentSnapshot] = query_ref.stream()
        documents: List = [self._doc_class.dict_to_doc(doc.to_dict(), doc.id, cascade=self._cascade) for doc in docs]
        if not documents:
            return str()
        workers = len(documents) if workers == 0 else workers
        with ThreadPoolExecutor(max_workers=workers) as executor:
            delete_threads = {executor.submit(self._delete_in_thread, document, self._cascade)
                              for document in documents}
            results = [future.result() for future in as_completed(delete_threads)]
        if results and all(result != str() for result in results):
            return results[-1]
        else:
            return str()


class FirestoreDocument:
    COLLECTION: Optional[str] = None  # Collection should be initialized by the child class call to init.
    objects: FirestoreQuery = None

    @classmethod
    def init(cls, collection: Optional[str] = None):
        cls.COLLECTION = collection if collection else f"{cls.__name__.lower()}s"
        cls.objects = FirestoreQuery()
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
        del doc_dict["_doc_id"]
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
                ordered_id_list = [(index, nested_id) for index, nested_id in enumerate(values)]
                workers = len(values) if values else None
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    get_threads = {executor.submit(_REFERENCE[field].get_by_id, nested_id, True)
                                   for nested_id in values}
                    firestore_document_list = [future.result() for future in as_completed(get_threads)]
                ordered_doc_list = [(next(ordered_id[0] for ordered_id in ordered_id_list if ordered_id[1] == doc.id),
                                     doc) for doc in firestore_document_list if doc]
                ordered_doc_list.sort(key=lambda ordered_tuple: ordered_tuple[0])
                firestore_document_list = [ordered_tuple[1] for ordered_tuple in ordered_doc_list]
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
        doc_dict["id"] = doc_dict["_doc_id"]
        del doc_dict["_doc_id"]
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

    @classmethod
    def create_from_list_of_dict(cls, doc_dict_list: List[dict], workers: int = 0) -> List[_FirestoreDocChild]:
        if not doc_dict_list:
            return list()
        workers = len(doc_dict_list) if workers == 0 else workers
        with ThreadPoolExecutor(max_workers=workers) as executor:
            created_threads = {executor.submit(cls.create_from_dict, doc_dict) for doc_dict in doc_dict_list}
            results = [future.result() for future in as_completed(created_threads)]
        return results

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

    @classmethod
    def save_all(cls, doc_list: List[_FirestoreDocChild], cascade: bool = False, workers: int = 0) -> List[bool]:
        if not doc_list:
            return list()
        workers = len(doc_list) if workers == 0 else workers
        with ThreadPoolExecutor(max_workers=workers) as executor:
            saved_threads = {executor.submit(doc.save, cascade) for doc in doc_list}
            results = [future.result() for future in as_completed(saved_threads)]
        return results

    def delete(self, cascade: bool = False) -> str:
        if not self._doc_id:
            return str()
        documents = self._get_nested_documents()
        if cascade:
            if any(doc.delete(cascade=True) == str() for _, doc_list in documents.items()
                   for doc in doc_list):
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
