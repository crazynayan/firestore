# Google Firestore ORM

This is yet another attempt to create an ORM for Google Firestore Database. 
This one is relatively simple one with not too many option to customize.
In fact the entire source code is in one file firestore-ci.py.

## Features
1) Provide multi-thread interface to simulate async interaction with firestore
2) A truncate feature to only create fields with non-default values in firestore
3) A cascade feature - This will be removed in future release

## How to use?
1. Install firestore-ci `pip install firestore-ci`
2. Save the GCP service-account json key in your project folder & give it a name. For e.g. `google-cloud.json`
3. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the json file. 
For e.g. in Linux `export GOOGLE_APPLICATION_CREDENTIALS="google-cloud.json"`
4. Import `FirestoreDocument` from `firestore_ci` 
5. Make your object model using `FirestoreDocument` For e.g. `class User(FirestoreDocument)`
6. Override the `__init__()` method to add your fields
7. Outside the model, call the `init()` method of Firestore document. For e.g. `User.init()` 
8. Here is a sample `models.py` file
```python
from firestore_ci import FirestoreDocument

class User(FirestoreDocument):
    def __init__(self):
        super().__init__()
        self.name = str()
        self.email = str()

User.init()
```

## Test
The unit test cases for this package can be found [here](https://github.com/crazynayan/firestore-test). 
The test cases are self explanatory and reviewing them will help understanding this package better.